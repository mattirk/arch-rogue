/*
 * arws: see arws.h. Glue only; libwebsockets implements the transport.
 */
#include "arws.h"

#include <libwebsockets.h>
#include <stdlib.h>
#include <string.h>

#define ARWS_CLOSE_TOO_BIG     1009
#define ARWS_CLOSE_UNSUPPORTED 1003
#define ARWS_CLOSE_OVERLOAD    1013

typedef struct arws_msg {
	struct arws_msg *next;
	size_t len;
	uint8_t data[]; /* outbound messages reserve LWS_PRE bytes of headroom */
} arws_msg;

typedef struct arws_queue {
	arws_msg *head, *tail;
	size_t bytes;
	uint32_t count;
} arws_queue;

static void queue_push(arws_queue *q, arws_msg *m, size_t accounted)
{
	m->next = NULL;
	if (q->tail)
		q->tail->next = m;
	else
		q->head = m;
	q->tail = m;
	q->bytes += accounted;
	q->count++;
}

static arws_msg *queue_pop(arws_queue *q, size_t accounted_of_head)
{
	arws_msg *m = q->head;
	if (!m)
		return NULL;
	q->head = m->next;
	if (!q->head)
		q->tail = NULL;
	q->bytes -= accounted_of_head;
	q->count--;
	return m;
}

static void queue_clear(arws_queue *q)
{
	arws_msg *m = q->head;
	while (m) {
		arws_msg *next = m->next;
		free(m);
		m = next;
	}
	memset(q, 0, sizeof(*q));
}

static arws_msg *outbound_copy(const uint8_t *data, size_t len)
{
	arws_msg *m = malloc(sizeof(arws_msg) + LWS_PRE + len);
	if (!m)
		return NULL;
	m->len = len;
	memcpy(m->data + LWS_PRE, data, len);
	return m;
}

/* Reassembly shared by both roles. Returns 0 to continue, or a close code. */
typedef struct arws_rx {
	uint8_t *buf;
	size_t len, cap;
} arws_rx;

static int rx_append(arws_rx *rx, const void *in, size_t len, uint32_t max)
{
	if (rx->len + len > max)
		return ARWS_CLOSE_TOO_BIG;
	if (rx->len + len > rx->cap) {
		size_t cap = rx->cap ? rx->cap : 1024;
		while (cap < rx->len + len)
			cap *= 2;
		if (cap > max)
			cap = max;
		uint8_t *grown = realloc(rx->buf, cap);
		if (!grown)
			return ARWS_CLOSE_OVERLOAD;
		rx->buf = grown;
		rx->cap = cap;
	}
	if (len)
		memcpy(rx->buf + rx->len, in, len);
	rx->len += len;
	return 0;
}

static arws_msg *rx_take(arws_rx *rx)
{
	arws_msg *m = malloc(sizeof(arws_msg) + rx->len);
	if (!m)
		return NULL;
	m->len = rx->len;
	if (rx->len)
		memcpy(m->data, rx->buf, rx->len);
	rx->len = 0;
	if (rx->cap > 64 * 1024) { /* do not pin a peak-sized buffer forever */
		free(rx->buf);
		rx->buf = NULL;
		rx->cap = 0;
	}
	return m;
}

static int message_complete(struct lws *wsi)
{
	return lws_is_final_fragment(wsi) && !lws_remaining_packet_payload(wsi);
}

static int write_one(struct lws *wsi, arws_msg *m)
{
	int n = lws_write(wsi, m->data + LWS_PRE, m->len, LWS_WRITE_TEXT);
	return n < (int)m->len ? -1 : 0;
}

static char *dup_string(const char *s)
{
	size_t n = strlen(s);
	char *d = malloc(n + 1);
	if (d)
		memcpy(d, s, n + 1);
	return d;
}

static int log_initialized;

static void quiet_logs(void)
{
	if (!log_initialized) {
		lws_set_log_level(LLL_ERR, NULL);
		log_initialized = 1;
	}
}

#if !defined(ARWS_SERVER_ONLY)
/* ================================================================ client == */

struct arws_client {
	struct lws_context *ctx;
	struct lws *wsi;
	struct lws_protocols protocols[2];
	arws_limits lim;
	arws_queue in, out;
	arws_rx rx;
	int state;
	int close_code;
	int closing;
	int pending_close_code;
	int activity; /* callbacks seen during the current service pass */
	char error[160];
	char *host, *path, *subprotocol;
};

static void client_fail(arws_client *c, const char *why)
{
	if (c->state != ARWS_FAILED) {
		c->state = ARWS_FAILED;
		snprintf(c->error, sizeof(c->error), "%s", why ? why : "connection failed");
	}
}

static int client_callback(struct lws *wsi, enum lws_callback_reasons reason,
			   void *user, void *in, size_t len)
{
	(void)user;
	arws_client *c = lws_context_user(lws_get_context(wsi));
	if (!c)
		return 0;

	switch (reason) {
	case LWS_CALLBACK_CLIENT_CONNECTION_ERROR:
		client_fail(c, in ? (const char *)in : "connection error");
		c->wsi = NULL;
		break;

	case LWS_CALLBACK_CLIENT_ESTABLISHED:
		c->state = c->closing ? ARWS_CLOSING : ARWS_OPEN;
		if (c->out.head || c->closing)
			lws_callback_on_writable(wsi);
		break;

	case LWS_CALLBACK_CLIENT_RECEIVE: {
		c->activity++;
		if (lws_frame_is_binary(wsi)) {
			client_fail(c, "binary message refused");
			lws_close_reason(wsi, ARWS_CLOSE_UNSUPPORTED, NULL, 0);
			return -1;
		}
		int code = rx_append(&c->rx, in, len, c->lim.max_message_bytes);
		if (code) {
			client_fail(c, "inbound message too large");
			lws_close_reason(wsi, (enum lws_close_status)code, NULL, 0);
			return -1;
		}
		if (!message_complete(wsi))
			break;
		if (c->in.count >= c->lim.max_inbound_count ||
		    c->in.bytes + c->rx.len > c->lim.max_inbound_bytes) {
			client_fail(c, "inbound queue overflow");
			lws_close_reason(wsi, ARWS_CLOSE_OVERLOAD, NULL, 0);
			return -1;
		}
		arws_msg *m = rx_take(&c->rx);
		if (!m) {
			client_fail(c, "out of memory");
			return -1;
		}
		queue_push(&c->in, m, m->len);
		break;
	}

	case LWS_CALLBACK_CLIENT_WRITEABLE: {
		c->activity++;
		if (c->closing && !c->out.head) {
			lws_close_reason(wsi, (enum lws_close_status)c->pending_close_code, NULL, 0);
			return -1;
		}
		/* Drain as much as the socket takes; stop when it would block. */
		while (c->out.head) {
			arws_msg *m = c->out.head;
			queue_pop(&c->out, m->len);
			int failed = write_one(wsi, m);
			free(m);
			if (failed) {
				client_fail(c, "write failed");
				return -1;
			}
			if (lws_send_pipe_choked(wsi))
				break;
		}
		if (c->out.head || c->closing)
			lws_callback_on_writable(wsi);
		break;
	}

	case LWS_CALLBACK_WS_PEER_INITIATED_CLOSE:
		if (len >= 2) {
			const uint8_t *b = in;
			c->close_code = (b[0] << 8) | b[1];
		}
		break;

	case LWS_CALLBACK_CLIENT_CLOSED:
		if (c->state != ARWS_FAILED)
			c->state = ARWS_CLOSED;
		c->wsi = NULL;
		break;

	case LWS_CALLBACK_WSI_DESTROY:
		if (c->wsi == wsi)
			c->wsi = NULL;
		if (c->state == ARWS_CONNECTING)
			client_fail(c, "connection closed during handshake");
		else if (c->state == ARWS_OPEN || c->state == ARWS_CLOSING)
			c->state = ARWS_CLOSED;
		break;

	default:
		break;
	}
	return 0;
}

arws_client *arws_client_create(const char *host, int port, const char *path,
				int use_tls, const char *ca_file,
				const char *subprotocol, arws_limits limits)
{
	quiet_logs();
	arws_client *c = calloc(1, sizeof(*c));
	if (!c)
		return NULL;
	c->lim = limits;
	c->state = ARWS_CONNECTING;
	c->pending_close_code = LWS_CLOSE_STATUS_NORMAL;
	c->host = dup_string(host);
	c->path = dup_string(path);
	c->subprotocol = dup_string(subprotocol);
	if (!c->host || !c->path || !c->subprotocol)
		goto fail;

	c->protocols[0].name = c->subprotocol;
	c->protocols[0].callback = client_callback;
	c->protocols[0].rx_buffer_size = 16 * 1024;

	struct lws_context_creation_info info;
	memset(&info, 0, sizeof(info));
	info.port = CONTEXT_PORT_NO_LISTEN;
	info.protocols = c->protocols;
	info.user = c;
	info.options = LWS_SERVER_OPTION_VALIDATE_UTF8;
	if (use_tls) {
		info.options |= LWS_SERVER_OPTION_DO_SSL_GLOBAL_INIT;
		info.client_ssl_ca_filepath = ca_file;
	}
	info.timeout_secs = 6;
	info.connect_timeout_secs = 6;
	info.fd_limit_per_thread = 8;
	c->ctx = lws_create_context(&info);
	if (!c->ctx)
		goto fail;

	struct lws_client_connect_info cc;
	memset(&cc, 0, sizeof(cc));
	cc.context = c->ctx;
	cc.address = c->host;
	cc.port = port;
	cc.path = c->path;
	cc.host = c->host;
	cc.protocol = c->subprotocol;
	/* TLS verification is never relaxed: no ALLOW_SELFSIGNED/INSECURE flags. */
	cc.ssl_connection = use_tls ? LCCSCF_USE_SSL : 0;
	cc.pwsi = &c->wsi;
	if (!lws_client_connect_via_info(&cc) && c->state == ARWS_CONNECTING)
		client_fail(c, "connect could not start");
	return c;

fail:
	arws_client_destroy(c);
	return NULL;
}

/* One service pass handles one read/write per socket; loop until a pass sees
 * no callbacks (bounded), so a frame drains everything that has arrived. */
void arws_client_service(arws_client *c)
{
	if (!c || !c->ctx)
		return;
	/* Buffered ws frames are delivered one per pass without a fresh poll
	 * event, so always run a few passes; keep going while callbacks fire
	 * or output is still queued. */
	for (int i = 0; i < 128; i++) {
		c->activity = 0;
		lws_service(c->ctx, -1);
		if (!c->ctx)
			break;
		if (i >= 4 && !c->activity && !c->out.head)
			break;
	}
}

int arws_client_state(const arws_client *c) { return c ? c->state : ARWS_FAILED; }
const char *arws_client_error(const arws_client *c) { return c ? c->error : "no client"; }
int arws_client_close_code(const arws_client *c) { return c ? c->close_code : 0; }
size_t arws_client_outbound_bytes(const arws_client *c) { return c ? c->out.bytes : 0; }
void arws_client_pending(const arws_client *c, uint32_t *count, size_t *bytes)
{
	*count = c ? c->in.count : 0;
	*bytes = c ? c->in.bytes : 0;
}

int arws_client_send(arws_client *c, const uint8_t *data, size_t len)
{
	if (!c || c->closing || c->state >= ARWS_CLOSING)
		return 0;
	if (len > c->lim.max_message_bytes || c->out.count >= c->lim.max_outbound_count ||
	    c->out.bytes + len > c->lim.max_outbound_bytes)
		return 0;
	arws_msg *m = outbound_copy(data, len);
	if (!m)
		return 0;
	queue_push(&c->out, m, len);
	if (c->wsi && c->state == ARWS_OPEN)
		lws_callback_on_writable(c->wsi);
	return 1;
}

long arws_client_peek(const arws_client *c)
{
	return (c && c->in.head) ? (long)c->in.head->len : -1;
}

long arws_client_recv(arws_client *c, uint8_t *out, size_t cap)
{
	if (!c || !c->in.head)
		return -1;
	arws_msg *m = c->in.head;
	if (m->len > cap)
		return -2;
	queue_pop(&c->in, m->len);
	long n = (long)m->len;
	if (n)
		memcpy(out, m->data, m->len);
	free(m);
	return n;
}

void arws_client_close(arws_client *c, int deadline_s)
{
	if (!c || c->closing)
		return;
	c->closing = 1;
	/* Already-queued messages (e.g. a final bye) still flush first; the
	 * deadline force-closes the socket if the peer does not drain. */
	if (c->wsi) {
		if (c->state == ARWS_OPEN)
			c->state = ARWS_CLOSING;
		lws_set_timeout(c->wsi, PENDING_TIMEOUT_USER_OK, deadline_s > 0 ? deadline_s : 1);
		lws_callback_on_writable(c->wsi);
	} else if (c->state < ARWS_CLOSED) {
		c->state = ARWS_CLOSED;
	}
}

void arws_client_destroy(arws_client *c)
{
	if (!c)
		return;
	if (c->ctx) {
		struct lws_context *ctx = c->ctx;
		lws_context_destroy(ctx);
		c->ctx = NULL;
	}
	queue_clear(&c->in);
	queue_clear(&c->out);
	free(c->rx.buf);
	free(c->host);
	free(c->path);
	free(c->subprotocol);
	free(c);
}

#endif /* !ARWS_SERVER_ONLY */

#if !defined(ARWS_CLIENT_ONLY)
/* ================================================================ server == */

typedef struct arws_conn {
	uint32_t id;
	struct lws *wsi;
	arws_queue out;
	arws_rx rx;
	int closing;
	int close_code;
	int peer_close_code;
	int registered;
	char source[ARWS_SOURCE_MAX];
} arws_conn;

typedef struct arws_event {
	struct arws_event *next;
	int kind;
	uint32_t conn;
	int close_code;
	arws_msg *msg;
} arws_event;

struct arws_server {
	struct lws_context *ctx;
	struct lws_protocols protocols[3];
	lws_sorted_usec_list_t wake;
	arws_server_config cfg;
	char *subprotocol, *ws_path, *health_path, *origins;
	arws_conn **conns;
	uint32_t conn_count;
	uint32_t next_id;
	arws_event *ev_head, *ev_tail;
	arws_event *ev_current; /* returned by the previous next() call */
	size_t ev_bytes;
	int activity;
};

static void server_event(arws_server *s, int kind, uint32_t conn, int code, arws_msg *msg)
{
	arws_event *e = calloc(1, sizeof(*e));
	if (!e) {
		free(msg);
		return;
	}
	e->kind = kind;
	e->conn = conn;
	e->close_code = code;
	e->msg = msg;
	if (msg)
		s->ev_bytes += msg->len;
	if (s->ev_tail)
		s->ev_tail->next = e;
	else
		s->ev_head = e;
	s->ev_tail = e;
}

static arws_conn *server_find(const arws_server *s, uint32_t id)
{
	for (uint32_t i = 0; i < s->cfg.max_connections; i++)
		if (s->conns[i] && s->conns[i]->id == id)
			return s->conns[i];
	return NULL;
}

static int origin_allowed(const arws_server *s, const char *origin)
{
	if (!s->origins || !*s->origins)
		return 1;
	size_t olen = strlen(origin);
	const char *p = s->origins;
	while (*p) {
		const char *nl = strchr(p, '\n');
		size_t n = nl ? (size_t)(nl - p) : strlen(p);
		if (n == olen && !memcmp(p, origin, n))
			return 1;
		if (!nl)
			break;
		p = nl + 1;
	}
	return 0;
}

static int peer_is_loopback(const char *peer)
{
	return !strcmp(peer, "127.0.0.1") || !strcmp(peer, "::1") ||
	       !strcmp(peer, "::ffff:127.0.0.1") || !strncmp(peer, "127.", 4);
}

/* Fills out with the client's source address for per-source accounting.
 * Behind the reverse proxy the TCP peer is always loopback, so the first
 * X-Forwarded-For entry (the one nginx appended for its own peer is last;
 * nginx sets the header from its peer when the client sent none, and the
 * relay deployment only accepts loopback TCP peers from nginx) identifies the
 * client. A non-loopback peer is used as-is and its forwarded header is
 * ignored, since anyone can forge it. Never fails: unknown becomes "?". */
static void server_source(struct lws *wsi, char *out, size_t cap)
{
	char peer[ARWS_SOURCE_MAX];
	char fwd[256];
	peer[0] = 0;
	lws_get_peer_simple(wsi, peer, sizeof(peer));
	if (!peer[0]) {
		strncpy(out, "?", cap - 1);
		out[cap - 1] = 0;
		return;
	}
	if (peer_is_loopback(peer)) {
		int n = lws_hdr_total_length(wsi, WSI_TOKEN_X_FORWARDED_FOR);
		if (n > 0 && n < (int)sizeof(fwd) &&
		    lws_hdr_copy(wsi, fwd, sizeof(fwd), WSI_TOKEN_X_FORWARDED_FOR) == n) {
			char *p = fwd;
			while (*p == ' ' || *p == '\t')
				p++;
			char *end = p;
			while (*end && *end != ',' && *end != ' ' && *end != '\t')
				end++;
			*end = 0;
			if (*p) {
				strncpy(out, p, cap - 1);
				out[cap - 1] = 0;
				return;
			}
		}
	}
	strncpy(out, peer, cap - 1);
	out[cap - 1] = 0;
}

static int server_filter(arws_server *s, struct lws *wsi, arws_conn *conn)
{
	char buf[256];
	if (s->conn_count >= s->cfg.max_connections)
		return -1;
	int n = lws_hdr_copy(wsi, buf, sizeof(buf), WSI_TOKEN_GET_URI);
	if (n <= 0 || strcmp(buf, s->ws_path))
		return -1;
	n = lws_hdr_total_length(wsi, WSI_TOKEN_ORIGIN);
	if (n > 0) {
		if (n >= (int)sizeof(buf))
			return -1;
		if (lws_hdr_copy(wsi, buf, sizeof(buf), WSI_TOKEN_ORIGIN) != n)
			return -1;
		if (!origin_allowed(s, buf))
			return -1;
	}
	/* Headers are still attached here; ESTABLISHED keeps this value. */
	if (conn)
		server_source(wsi, conn->source, sizeof(conn->source));
	return 0;
}

static void server_unregister(arws_server *s, arws_conn *conn)
{
	if (!conn->registered)
		return;
	for (uint32_t i = 0; i < s->cfg.max_connections; i++) {
		if (s->conns[i] == conn) {
			s->conns[i] = NULL;
			break;
		}
	}
	conn->registered = 0;
	s->conn_count--;
	server_event(s, ARWS_EV_CLOSED, conn->id,
		     conn->peer_close_code ? conn->peer_close_code : conn->close_code, NULL);
	queue_clear(&conn->out);
	free(conn->rx.buf);
	conn->rx.buf = NULL;
	conn->wsi = NULL;
}

static int server_ws_callback(struct lws *wsi, enum lws_callback_reasons reason,
			      void *user, void *in, size_t len)
{
	arws_server *s = lws_context_user(lws_get_context(wsi));
	arws_conn *conn = user;
	if (!s)
		return 0;

	switch (reason) {
	case LWS_CALLBACK_FILTER_PROTOCOL_CONNECTION:
		return server_filter(s, wsi, conn);

	case LWS_CALLBACK_ESTABLISHED: {
		uint32_t slot = s->cfg.max_connections;
		for (uint32_t i = 0; i < s->cfg.max_connections; i++)
			if (!s->conns[i]) {
				slot = i;
				break;
			}
		if (slot == s->cfg.max_connections)
			return -1;
		char source[ARWS_SOURCE_MAX];
		memcpy(source, conn->source, sizeof(source));
		memset(conn, 0, sizeof(*conn));
		if (!source[0])
			server_source(wsi, source, sizeof(source));
		memcpy(conn->source, source, sizeof(conn->source));
		conn->id = ++s->next_id;
		if (!conn->id)
			conn->id = ++s->next_id;
		conn->wsi = wsi;
		conn->registered = 1;
		s->conns[slot] = conn;
		s->conn_count++;
		server_event(s, ARWS_EV_OPEN, conn->id, 0, NULL);
		break;
	}

	case LWS_CALLBACK_RECEIVE: {
		s->activity++;
		if (!conn || !conn->registered || conn->closing)
			break;
		if (lws_frame_is_binary(wsi)) {
			lws_close_reason(wsi, ARWS_CLOSE_UNSUPPORTED, NULL, 0);
			conn->close_code = ARWS_CLOSE_UNSUPPORTED;
			return -1;
		}
		int code = rx_append(&conn->rx, in, len, s->cfg.limits.max_message_bytes);
		if (code) {
			lws_close_reason(wsi, (enum lws_close_status)code, NULL, 0);
			conn->close_code = code;
			return -1;
		}
		if (!message_complete(wsi))
			break;
		if (s->ev_bytes + conn->rx.len > s->cfg.limits.max_inbound_bytes) {
			lws_close_reason(wsi, ARWS_CLOSE_OVERLOAD, NULL, 0);
			conn->close_code = ARWS_CLOSE_OVERLOAD;
			return -1;
		}
		arws_msg *m = rx_take(&conn->rx);
		if (!m)
			return -1;
		server_event(s, ARWS_EV_MESSAGE, conn->id, 0, m);
		break;
	}

	case LWS_CALLBACK_SERVER_WRITEABLE: {
		s->activity++;
		if (!conn || !conn->registered)
			break;
		if (conn->closing && !conn->out.head) {
			lws_close_reason(wsi, (enum lws_close_status)conn->close_code, NULL, 0);
			return -1;
		}
		while (conn->out.head) {
			arws_msg *m = conn->out.head;
			queue_pop(&conn->out, m->len);
			int failed = write_one(wsi, m);
			free(m);
			if (failed)
				return -1;
			if (lws_send_pipe_choked(wsi))
				break;
		}
		if (conn->out.head || conn->closing)
			lws_callback_on_writable(wsi);
		break;
	}

	case LWS_CALLBACK_WS_PEER_INITIATED_CLOSE:
		if (conn && len >= 2) {
			const uint8_t *b = in;
			conn->peer_close_code = (b[0] << 8) | b[1];
		}
		break;

	case LWS_CALLBACK_CLOSED:
	case LWS_CALLBACK_WSI_DESTROY:
		if (conn)
			server_unregister(s, conn);
		break;

	default:
		break;
	}
	return 0;
}

static int server_http_callback(struct lws *wsi, enum lws_callback_reasons reason,
				void *user, void *in, size_t len)
{
	arws_server *s = lws_context_user(lws_get_context(wsi));
	if (!s)
		return lws_callback_http_dummy(wsi, reason, user, in, len);

	switch (reason) {
	case LWS_CALLBACK_FILTER_PROTOCOL_CONNECTION:
		/* Upgrades without the required subprotocol land here: refuse. */
		return -1;

	case LWS_CALLBACK_HTTP: {
		const char *uri = in ? (const char *)in : "";
		if (s->health_path && !strcmp(uri, s->health_path)) {
			if (lws_return_http_status(wsi, HTTP_STATUS_OK, "ok"))
				return -1;
		} else {
			if (lws_return_http_status(wsi, HTTP_STATUS_NOT_FOUND, NULL))
				return -1;
		}
		return lws_http_transaction_completed(wsi) ? -1 : 0;
	}

	default:
		break;
	}
	return lws_callback_http_dummy(wsi, reason, user, in, len);
}

static void server_wake(lws_sorted_usec_list_t *sul) { (void)sul; }

arws_server *arws_server_create(const arws_server_config *config)
{
	quiet_logs();
	if (!config || !config->subprotocol || !config->ws_path || !config->max_connections)
		return NULL;
	arws_server *s = calloc(1, sizeof(*s));
	if (!s)
		return NULL;
	s->cfg = *config;
	s->subprotocol = dup_string(config->subprotocol);
	s->ws_path = dup_string(config->ws_path);
	s->health_path = dup_string(config->health_path ? config->health_path : "/healthz");
	s->origins = dup_string(config->origins ? config->origins : "");
	s->conns = calloc(config->max_connections, sizeof(arws_conn *));
	if (!s->subprotocol || !s->ws_path || !s->health_path || !s->origins || !s->conns)
		goto fail;
	s->cfg.subprotocol = s->subprotocol;
	s->cfg.ws_path = s->ws_path;
	s->cfg.health_path = s->health_path;
	s->cfg.origins = s->origins;

	s->protocols[0].name = "http";
	s->protocols[0].callback = server_http_callback;
	s->protocols[1].name = s->subprotocol;
	s->protocols[1].callback = server_ws_callback;
	s->protocols[1].per_session_data_size = sizeof(arws_conn);
	s->protocols[1].rx_buffer_size = 16 * 1024;

	struct lws_context_creation_info info;
	memset(&info, 0, sizeof(info));
	info.port = config->port;
	info.iface = config->bind_address;
	info.protocols = s->protocols;
	info.user = s;
	info.options = LWS_SERVER_OPTION_VALIDATE_UTF8 | LWS_SERVER_OPTION_DISABLE_IPV6;
	info.timeout_secs = 10;
	info.max_http_header_data = 4096;
	info.max_http_header_pool = 64;
	info.fd_limit_per_thread = config->max_connections + 16;
	s->ctx = lws_create_context(&info);
	if (!s->ctx)
		goto fail;
	return s;

fail:
	arws_server_destroy(s);
	return NULL;
}

void arws_server_service(arws_server *s, int wait_ms)
{
	if (!s || !s->ctx)
		return;
	/* First pass may wait up to wait_ms; further passes drain without
	 * waiting while sockets keep producing work. */
	lws_sul_schedule(s->ctx, 0, &s->wake, server_wake,
			 (lws_usec_t)(wait_ms > 0 ? wait_ms : 1) * LWS_US_PER_MS);
	s->activity = 0;
	lws_service(s->ctx, 0);
	for (int i = 0; i < 128; i++) {
		int pending = 0;
		for (uint32_t k = 0; k < s->cfg.max_connections && !pending; k++)
			if (s->conns[k] && s->conns[k]->out.head)
				pending = 1;
		if (i >= 4 && !s->activity && !pending)
			break;
		s->activity = 0;
		lws_service(s->ctx, -1);
	}
	lws_sul_cancel(&s->wake);
}

int arws_server_next(arws_server *s, uint32_t *conn, const uint8_t **data, size_t *len, int *close_code)
{
	if (!s)
		return ARWS_EV_NONE;
	if (s->ev_current) {
		if (s->ev_current->msg) {
			s->ev_bytes -= s->ev_current->msg->len;
			free(s->ev_current->msg);
		}
		free(s->ev_current);
		s->ev_current = NULL;
	}
	arws_event *e = s->ev_head;
	if (!e)
		return ARWS_EV_NONE;
	s->ev_head = e->next;
	if (!s->ev_head)
		s->ev_tail = NULL;
	s->ev_current = e;
	*conn = e->conn;
	*data = e->msg ? e->msg->data : NULL;
	*len = e->msg ? e->msg->len : 0;
	*close_code = e->close_code;
	return e->kind;
}

int arws_server_send(arws_server *s, uint32_t id, const uint8_t *data, size_t len)
{
	if (!s)
		return 0;
	arws_conn *conn = server_find(s, id);
	if (!conn || conn->closing || !conn->wsi)
		return 0;
	if (len > s->cfg.limits.max_message_bytes ||
	    conn->out.count >= s->cfg.limits.max_outbound_count ||
	    conn->out.bytes + len > s->cfg.limits.max_outbound_bytes)
		return 0;
	arws_msg *m = outbound_copy(data, len);
	if (!m)
		return 0;
	queue_push(&conn->out, m, len);
	lws_callback_on_writable(conn->wsi);
	return 1;
}

size_t arws_server_outbound_bytes(const arws_server *s, uint32_t id)
{
	arws_conn *conn = s ? server_find(s, id) : NULL;
	return conn ? conn->out.bytes : 0;
}

void arws_server_close(arws_server *s, uint32_t id, int code, int deadline_s)
{
	arws_conn *conn = s ? server_find(s, id) : NULL;
	if (!conn || conn->closing || !conn->wsi)
		return;
	conn->closing = 1;
	conn->close_code = code ? code : LWS_CLOSE_STATUS_NORMAL;
	/* Flush what is already queued only if the peer drains promptly; the
	 * timeout forcibly tears the socket down otherwise. */
	lws_set_timeout(conn->wsi, PENDING_TIMEOUT_USER_OK, deadline_s > 0 ? deadline_s : 1);
	lws_callback_on_writable(conn->wsi);
}

int arws_server_source(const arws_server *s, uint32_t conn_id, char *out, size_t cap)
{
	if (!s || !out || cap == 0)
		return -1;
	arws_conn *conn = server_find((arws_server *)s, conn_id);
	if (!conn) {
		out[0] = 0;
		return -1;
	}
	size_t n = strlen(conn->source);
	if (n >= cap)
		n = cap - 1;
	memcpy(out, conn->source, n);
	out[n] = 0;
	return (int)n;
}

uint32_t arws_server_connection_count(const arws_server *s) { return s ? s->conn_count : 0; }

void arws_server_destroy(arws_server *s)
{
	if (!s)
		return;
	if (s->ctx) {
		lws_sul_cancel(&s->wake);
		lws_context_destroy(s->ctx);
		s->ctx = NULL;
	}
	const uint8_t *d;
	size_t l;
	uint32_t c;
	int code;
	while (arws_server_next(s, &c, &d, &l, &code) != ARWS_EV_NONE)
		;
	arws_server_next(s, &c, &d, &l, &code);
	free(s->conns);
	free(s->subprotocol);
	free(s->ws_path);
	free(s->health_path);
	free(s->origins);
	free(s);
}
#endif /* !ARWS_CLIENT_ONLY */
