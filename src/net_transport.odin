package archrogue

// Multiplayer transport contract shared by the native (libwebsockets) and
// browser (WebSocket API) adapters. One ordered WebSocket connection carries
// one UTF-8 JSON object per text message. Adapters own bounded queues; this
// file owns endpoint validation so every platform accepts the same URLs.

import "core:strconv"
import "core:strings"
import np "net_protocol"

Net_Transport_State :: enum u8 {
	Closed,
	Connecting,
	Open,
	Closing,
	Failed,
}

Net_Endpoint :: struct {
	secure: bool, // wss
	host:   string,
	port:   int,
	path:   string,
}

Net_Url_Error :: enum u8 {
	None,
	Empty,
	Scheme,     // only ws:// and wss:// are accepted
	Host,
	Port,
	Path,
	Credentials, // user:pass@ is never accepted
}

NET_URL_MAX_BYTES :: 200
// Public relay (human decision 2026-10-09). TLS terminates at the reverse
// proxy in front of the Odin relay. ARCH_ROGUE_RELAY_URL (desktop) or the
// ?relay= query parameter (web) supplies another endpoint, e.g. a local relay.
DEFAULT_RELAY_URL :: "wss://ar.rita-kasari.fi/mp"

// Parses ws[s]://host[:port][/path]. Hosts are DNS names, IPv4 literals, or
// bracketed IPv6 literals; no credentials, query, or fragment. The returned
// strings borrow from text.
net_url_parse :: proc(text: string) -> (endpoint: Net_Endpoint, err: Net_Url_Error) {
	url := strings.trim_space(text)
	if url == "" do return {}, .Empty
	if len(url) > NET_URL_MAX_BYTES do return {}, .Host
	rest: string
	switch {
	case strings.has_prefix(url, "wss://"):
		endpoint.secure = true
		rest = url[6:]
	case strings.has_prefix(url, "ws://"):
		rest = url[5:]
	case:
		return {}, .Scheme
	}
	authority := rest
	endpoint.path = np.WS_PATH
	if slash := strings.index_byte(rest, '/'); slash >= 0 {
		authority = rest[:slash]
		endpoint.path = rest[slash:]
	}
	if strings.index_any(endpoint.path, "?#") >= 0 do return {}, .Path
	for c in transmute([]byte)endpoint.path do if c <= ' ' || c == '\\' || c >= 0x7f do return {}, .Path
	if strings.index_byte(authority, '@') >= 0 do return {}, .Credentials
	endpoint.port = endpoint.secure ? 443 : 80
	host := authority
	if strings.has_prefix(authority, "[") {
		close := strings.index_byte(authority, ']')
		if close < 0 do return {}, .Host
		host = authority[1:close]
		tail := authority[close + 1:]
		if tail != "" {
			if !strings.has_prefix(tail, ":") do return {}, .Port
			port, ok := strconv.parse_int(tail[1:], 10)
			if !ok || port <= 0 || port > 65535 do return {}, .Port
			endpoint.port = port
		}
		for c in transmute([]byte)host do if !(('0' <= c && c <= '9') || ('a' <= c && c <= 'f') || ('A' <= c && c <= 'F') || c == ':' || c == '.') do return {}, .Host
	} else {
		if colon := strings.last_index_byte(authority, ':'); colon >= 0 {
			host = authority[:colon]
			port, ok := strconv.parse_int(authority[colon + 1:], 10)
			if !ok || port <= 0 || port > 65535 do return {}, .Port
			endpoint.port = port
		}
		for c in transmute([]byte)host do if !(('0' <= c && c <= '9') || ('a' <= c && c <= 'z') || ('A' <= c && c <= 'Z') || c == '.' || c == '-') do return {}, .Host
	}
	if host == "" || len(host) > 253 do return {}, .Host
	endpoint.host = host
	return endpoint, .None
}

net_url_error_text :: proc(err: Net_Url_Error) -> string {
	switch err {
	case .None:        return ""
	case .Empty:       return "Enter a server address"
	case .Scheme:      return "Address must start with wss:// (or ws:// for local testing)"
	case .Host:        return "Server host name is not valid"
	case .Port:        return "Server port is not valid"
	case .Path:        return "Server path is not valid"
	case .Credentials: return "Server address must not contain a user name or password"
	}
	return ""
}

// Plaintext is a development/LAN option: loopback and private addresses only
// get a quieter warning; it is never chosen silently.
net_endpoint_is_local :: proc(endpoint: Net_Endpoint) -> bool {
	host := endpoint.host
	return host == "localhost" || host == "::1" || strings.has_prefix(host, "127.") ||
		strings.has_prefix(host, "10.") || strings.has_prefix(host, "192.168.")
}

// Bounded queue limits shared by both adapters. They are ceilings, not
// preallocations: queues hold only messages actually in flight.
NET_CLIENT_MAX_INBOUND_BYTES  :: 4 * 1024 * 1024
NET_CLIENT_MAX_OUTBOUND_BYTES :: 2 * 1024 * 1024
NET_CLIENT_MAX_INBOUND_COUNT  :: 512
NET_CLIENT_MAX_OUTBOUND_COUNT :: 256

// In-process transport for headless tests and harnesses: two queues that a
// test pumps through the relay reducer. Never selected by shipping UI.
Net_Test_Pipe :: struct {
	open:     bool,
	closed:   bool,
	to_relay: [dynamic][]byte, // client -> relay
	to_client: [dynamic][]byte, // relay -> client
}

net_test_pipe_destroy :: proc(pipe: ^Net_Test_Pipe) {
	for m in pipe.to_relay do delete(m)
	for m in pipe.to_client do delete(m)
	delete(pipe.to_relay)
	delete(pipe.to_client)
	pipe^ = {}
}

// Set by a test before net_session_host/join; the next open uses it.
@(thread_local)
net_test_pipe_next: ^Net_Test_Pipe

// Services the socket until its outbound queue drains or budget_ms passes.
// Native only blocks for the budget; the browser returns at once.
net_transport_flush :: proc(t: ^Net_Transport, budget_ms: int) {
	for _ in 0 ..< max(budget_ms, 1) {
		net_transport_service(t)
		if net_transport_outbound_bytes(t) == 0 || net_transport_state(t) != .Open do return
		net_transport_sleep_ms(1)
	}
}
