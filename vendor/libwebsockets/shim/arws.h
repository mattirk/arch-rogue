/*
 * arws: Arch Rogue's narrow, poll-driven facade over libwebsockets.
 *
 * libwebsockets owns HTTP Upgrade, framing, masking, control frames, TLS and
 * certificate verification. This shim only adapts its callback model into
 * bounded owned message queues that Odin drains from one thread. It contains
 * no WebSocket protocol code and no Arch Rogue application protocol.
 *
 * Every function must be called from the thread that created the object.
 */
#ifndef ARWS_H
#define ARWS_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

enum arws_state {
	ARWS_CONNECTING = 0,
	ARWS_OPEN       = 1,
	ARWS_CLOSING    = 2,
	ARWS_CLOSED     = 3, /* orderly close, or peer close */
	ARWS_FAILED     = 4, /* connect/TLS/handshake failure or local overflow */
};

typedef struct arws_limits {
	uint32_t max_message_bytes;  /* complete application message, UTF-8 bytes */
	uint32_t max_inbound_bytes;  /* queued, not yet drained */
	uint32_t max_outbound_bytes; /* queued, not yet written */
	uint32_t max_inbound_count;
	uint32_t max_outbound_count;
} arws_limits;

/* ---------------------------------------------------------------- client -- */

typedef struct arws_client arws_client;

/* host/path are copied. use_tls verifies the chain and hostname against the OS
 * trust store (or ca_file when non-NULL). There is no option to skip checks. */
arws_client *arws_client_create(const char *host, int port, const char *path,
				int use_tls, const char *ca_file,
				const char *subprotocol, arws_limits limits);
/* Non-blocking: services pending socket work and returns immediately. */
void arws_client_service(arws_client *c);
int arws_client_state(const arws_client *c);
/* Short diagnostic for FAILED/CLOSED; static storage owned by the client. */
const char *arws_client_error(const arws_client *c);
int arws_client_close_code(const arws_client *c);
/* Copies the message. Returns 1 on success, 0 when queue limits refuse it. */
int arws_client_send(arws_client *c, const uint8_t *data, size_t len);
/* Size of the next inbound message, or -1 when none is queued. */
long arws_client_peek(const arws_client *c);
/* Copies and dequeues the next message when cap suffices; returns its length,
 * -1 when empty, -2 when cap is too small (message stays queued). */
long arws_client_recv(arws_client *c, uint8_t *out, size_t cap);
size_t arws_client_outbound_bytes(const arws_client *c);
/* Complete inbound messages not yet dequeued. */
void arws_client_pending(const arws_client *c, uint32_t *count, size_t *bytes);
/* Begin an orderly close; the socket is force-torn down after deadline_s. */
void arws_client_close(arws_client *c, int deadline_s);
/* Immediately tears down the socket and frees everything. */
void arws_client_destroy(arws_client *c);

/* ---------------------------------------------------------------- server -- */

typedef struct arws_server arws_server;

enum arws_event_kind {
	ARWS_EV_NONE    = 0,
	ARWS_EV_OPEN    = 1,
	ARWS_EV_MESSAGE = 2,
	ARWS_EV_CLOSED  = 3,
};

typedef struct arws_server_config {
	const char *bind_address;  /* e.g. "127.0.0.1"; NULL binds all interfaces */
	int port;
	const char *subprotocol;   /* required Sec-WebSocket-Protocol */
	const char *ws_path;       /* e.g. "/mp" */
	const char *health_path;   /* e.g. "/healthz" */
	/* Newline-separated exact Origin allowlist. Requests without Origin
	 * (native clients) are accepted; a present Origin must match. NULL or
	 * empty accepts any Origin (development only). */
	const char *origins;
	uint32_t max_connections;
	arws_limits limits;
} arws_server_config;

arws_server *arws_server_create(const arws_server_config *config);
/* Blocks up to roughly wait_ms for socket activity. */
void arws_server_service(arws_server *s, int wait_ms);
/* Next queued event. For MESSAGE, *data points at shim-owned bytes valid only
 * until the next arws_server_next call. Returns ARWS_EV_NONE when empty. */
int arws_server_next(arws_server *s, uint32_t *conn, const uint8_t **data, size_t *len, int *close_code);
int arws_server_send(arws_server *s, uint32_t conn, const uint8_t *data, size_t len);
size_t arws_server_outbound_bytes(const arws_server *s, uint32_t conn);
/* Orderly close with a status code; forced teardown after deadline_s. */
void arws_server_close(arws_server *s, uint32_t conn, int code, int deadline_s);
uint32_t arws_server_connection_count(const arws_server *s);
void arws_server_destroy(arws_server *s);

#ifdef __cplusplus
}
#endif
#endif
