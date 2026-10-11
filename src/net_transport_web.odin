#+build freestanding
package archrogue

// Browser WebSocket transport over web/library_archrogue.js. The browser owns
// TLS and certificate verification; this side only moves bounded UTF-8 bytes.
// Nothing here blocks the requestAnimationFrame loop.

import "core:strings"
import np "net_protocol"

@(default_calling_convention = "c")
foreign {
	ar_js_ws_open       :: proc(url_ptr: rawptr, url_len: i32, proto_ptr: rawptr, proto_len: i32) -> i32 ---
	ar_js_ws_state      :: proc(gen: i32) -> i32 ---
	ar_js_ws_close_code :: proc(gen: i32) -> i32 ---
	ar_js_ws_error      :: proc(gen: i32, buffer: rawptr, capacity: i32) -> i32 ---
	ar_js_ws_send       :: proc(gen: i32, ptr: rawptr, length: i32) -> i32 ---
	ar_js_ws_buffered   :: proc(gen: i32) -> f64 ---
	ar_js_ws_peek       :: proc(gen: i32) -> i32 ---
	ar_js_ws_recv       :: proc(gen: i32, ptr: rawptr, capacity: i32) -> i32 ---
	ar_js_ws_close      :: proc(gen: i32) ---
	ar_js_random_bytes  :: proc(ptr: rawptr, length: i32) ---
}

Net_Transport :: struct {
	gen:       i32, // 0 = never opened
	error_buf: [160]byte,
}

net_transport_available :: proc() -> bool {
	return true
}

net_transport_open :: proc(t: ^Net_Transport, endpoint: Net_Endpoint, pipe: ^Net_Test_Pipe = nil) -> bool {
	net_transport_destroy(t)
	host := endpoint.host
	if strings.index_byte(host, ':') >= 0 do host = strings.concatenate({"[", host, "]"}, context.temp_allocator)
	url := strings.concatenate({endpoint.secure ? "wss://" : "ws://", host, ":", int_text(endpoint.port), endpoint.path}, context.temp_allocator)
	protocol := np.SUBPROTOCOL
	t.gen = ar_js_ws_open(raw_data(url), i32(len(url)), raw_data(protocol), i32(len(protocol)))
	return t.gen != 0
}

@(private = "file")
int_text :: proc(n: int) -> string {
	buf := make([]byte, 8, context.temp_allocator)
	i := len(buf)
	v := n
	if v == 0 {
		i -= 1
		buf[i] = '0'
	}
	for v > 0 && i > 0 {
		i -= 1
		buf[i] = byte('0' + v % 10)
		v /= 10
	}
	return string(buf[i:])
}

net_transport_service :: proc(t: ^Net_Transport) {}

net_transport_state :: proc(t: ^Net_Transport) -> Net_Transport_State {
	if t.gen == 0 do return .Closed
	switch ar_js_ws_state(t.gen) {
	case 0: return .Connecting
	case 1: return .Open
	case 2: return .Closing
	case 3: return .Closed
	}
	return .Failed
}

net_transport_error :: proc(t: ^Net_Transport) -> string {
	if t.gen == 0 do return ""
	n := ar_js_ws_error(t.gen, &t.error_buf[0], i32(len(t.error_buf)))
	if n <= 0 do return ""
	return string(t.error_buf[:n])
}

net_transport_close_code :: proc(t: ^Net_Transport) -> int {
	if t.gen == 0 do return 0
	return int(ar_js_ws_close_code(t.gen))
}

net_transport_send :: proc(t: ^Net_Transport, data: []byte) -> bool {
	if t.gen == 0 || len(data) == 0 do return false
	return ar_js_ws_send(t.gen, raw_data(data), i32(len(data))) != 0
}

net_transport_recv :: proc(t: ^Net_Transport, allocator := context.allocator) -> (data: []byte, ok: bool) {
	if t.gen == 0 do return nil, false
	size := ar_js_ws_peek(t.gen)
	if size < 0 do return nil, false
	data = make([]byte, int(size), allocator)
	got := ar_js_ws_recv(t.gen, raw_data(data), size)
	if got != size {
		delete(data, allocator)
		return nil, false
	}
	return data, true
}

net_transport_outbound_bytes :: proc(t: ^Net_Transport) -> int {
	if t.gen == 0 do return 0
	return int(ar_js_ws_buffered(t.gen))
}

// The browser API cannot force-abort queued sends: invalidate the logical
// generation now and let the relay's deadlines reclaim the socket.
net_transport_close :: proc(t: ^Net_Transport) {
	if t.gen != 0 do ar_js_ws_close(t.gen)
}

net_transport_destroy :: proc(t: ^Net_Transport) {
	if t.gen != 0 do ar_js_ws_close(t.gen)
	t^ = {}
}

net_random_bytes :: proc(buf: []byte) {
	if len(buf) > 0 do ar_js_random_bytes(raw_data(buf), i32(len(buf)))
}

// No blocking in the browser: the WebSocket flushes asynchronously.
net_transport_sleep_ms :: proc(ms: int) {}

net_transport_pending :: proc(t: ^Net_Transport) -> (count: int, bytes: int) {
	if t.gen == 0 do return 0, 0
	return ar_js_ws_peek(t.gen) >= 0 ? 1 : 0, 0
}
