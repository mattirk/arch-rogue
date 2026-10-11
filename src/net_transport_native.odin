#+build !freestanding
package archrogue

// Native WebSocket transport: libwebsockets behind the vendored arws facade
// (vendor/libwebsockets/shim). Serviced non-blocking from the main thread once
// per frame; it never touches raylib or the Run. wss:// verifies the chain and
// hostname against the OS trust store, with no option to skip verification.
//
// Linux desktop links the pinned archive. Android and Windows report
// networking as unavailable until their pinned builds land (MULTIPLAYER.md M1).

import "core:crypto"
import "core:time"
import "core:strings"
import np "net_protocol"

NET_NATIVE_LWS :: ODIN_OS == .Linux && !ARCH_ROGUE_ANDROID

when NET_NATIVE_LWS {
	foreign import arws {
		"../vendor/libwebsockets/linux/libarws_client.a",
		"system:ssl",
		"system:crypto",
	}

	@(private = "file")
	Arws_Limits :: struct {
		max_message_bytes:  u32,
		max_inbound_bytes:  u32,
		max_outbound_bytes: u32,
		max_inbound_count:  u32,
		max_outbound_count: u32,
	}

	@(default_calling_convention = "c", private = "file")
	foreign arws {
		arws_client_create :: proc(host: cstring, port: i32, path: cstring, use_tls: i32, ca_file: cstring, subprotocol: cstring, limits: Arws_Limits) -> rawptr ---
		arws_client_service :: proc(c: rawptr) ---
		arws_client_state :: proc(c: rawptr) -> i32 ---
		arws_client_error :: proc(c: rawptr) -> cstring ---
		arws_client_close_code :: proc(c: rawptr) -> i32 ---
		arws_client_send :: proc(c: rawptr, data: [^]u8, len: uint) -> i32 ---
		arws_client_peek :: proc(c: rawptr) -> int ---
		arws_client_recv :: proc(c: rawptr, out: [^]u8, cap: uint) -> int ---
		arws_client_outbound_bytes :: proc(c: rawptr) -> uint ---
		arws_client_pending :: proc(c: rawptr, count: ^u32, bytes: ^uint) ---
		arws_client_close :: proc(c: rawptr, deadline_s: i32) ---
		arws_client_destroy :: proc(c: rawptr) ---
	}
}

Net_Transport :: struct {
	handle: rawptr,
	failed: bool, // creation failed before a handle existed
	pipe:   ^Net_Test_Pipe,
}

net_transport_available :: proc() -> bool {
	return NET_NATIVE_LWS
}

net_transport_open :: proc(t: ^Net_Transport, endpoint: Net_Endpoint, pipe: ^Net_Test_Pipe = nil) -> bool {
	net_transport_destroy(t)
	if pipe != nil {
		// A fresh connection never sees traffic queued for a dead one.
		for m in pipe.to_client do delete(m)
		for m in pipe.to_relay do delete(m)
		clear(&pipe.to_client)
		clear(&pipe.to_relay)
		t.pipe = pipe
		t.pipe.open = true
		t.pipe.closed = false
		return true
	}
	when NET_NATIVE_LWS {
		host := strings.clone_to_cstring(endpoint.host, context.temp_allocator)
		path := strings.clone_to_cstring(endpoint.path, context.temp_allocator)
		limits := Arws_Limits{
			max_message_bytes  = np.MAX_MESSAGE_BYTES,
			max_inbound_bytes  = NET_CLIENT_MAX_INBOUND_BYTES,
			max_outbound_bytes = NET_CLIENT_MAX_OUTBOUND_BYTES,
			max_inbound_count  = NET_CLIENT_MAX_INBOUND_COUNT,
			max_outbound_count = NET_CLIENT_MAX_OUTBOUND_COUNT,
		}
		t.handle = arws_client_create(host, i32(endpoint.port), path, endpoint.secure ? 1 : 0, nil, np.SUBPROTOCOL, limits)
		t.failed = t.handle == nil
		return !t.failed
	} else {
		t.failed = true
		return false
	}
}

net_transport_service :: proc(t: ^Net_Transport) {
	if t.pipe != nil do return
	when NET_NATIVE_LWS {
		if t.handle != nil do arws_client_service(t.handle)
	}
}

net_transport_state :: proc(t: ^Net_Transport) -> Net_Transport_State {
	if t.pipe != nil do return t.pipe.closed ? .Closed : .Open
	if t.failed do return .Failed
	when NET_NATIVE_LWS {
		if t.handle == nil do return .Closed
		switch arws_client_state(t.handle) {
		case 0: return .Connecting
		case 1: return .Open
		case 2: return .Closing
		case 3: return .Closed
		}
		return .Failed
	} else {
		return .Closed
	}
}

net_transport_error :: proc(t: ^Net_Transport) -> string {
	when NET_NATIVE_LWS {
		if t.handle != nil do return string(arws_client_error(t.handle))
		if t.failed do return "could not start the connection"
		return ""
	} else {
		return "online co-op is not available in this build yet"
	}
}

net_transport_close_code :: proc(t: ^Net_Transport) -> int {
	when NET_NATIVE_LWS {
		if t.handle != nil do return int(arws_client_close_code(t.handle))
	}
	return 0
}

net_transport_send :: proc(t: ^Net_Transport, data: []byte) -> bool {
	if t.pipe != nil {
		if t.pipe.closed || len(data) == 0 do return false
		copy_ := make([]byte, len(data))
		copy(copy_, data)
		append(&t.pipe.to_relay, copy_)
		return true
	}
	when NET_NATIVE_LWS {
		if t.handle == nil || len(data) == 0 do return false
		return arws_client_send(t.handle, raw_data(data), uint(len(data))) != 0
	} else {
		return false
	}
}

// Next complete inbound message, copied into allocator-owned bytes.
net_transport_recv :: proc(t: ^Net_Transport, allocator := context.allocator) -> (data: []byte, ok: bool) {
	if t.pipe != nil {
		if len(t.pipe.to_client) == 0 do return nil, false
		m := t.pipe.to_client[0]
		ordered_remove(&t.pipe.to_client, 0)
		data = make([]byte, len(m), allocator)
		copy(data, m)
		delete(m)
		return data, true
	}
	when NET_NATIVE_LWS {
		if t.handle == nil do return nil, false
		size := arws_client_peek(t.handle)
		if size < 0 do return nil, false
		data = make([]byte, size, allocator)
		got := arws_client_recv(t.handle, raw_data(data), uint(size))
		if got != size {
			delete(data, allocator)
			return nil, false
		}
		return data, true
	} else {
		return nil, false
	}
}

net_transport_outbound_bytes :: proc(t: ^Net_Transport) -> int {
	when NET_NATIVE_LWS {
		if t.handle != nil do return int(arws_client_outbound_bytes(t.handle))
	}
	return 0
}

// Orderly close: queued messages (such as bye) flush first, and the socket is
// forcibly torn down after the deadline if the peer does not drain.
net_transport_close :: proc(t: ^Net_Transport) {
	if t.pipe != nil {
		t.pipe.closed = true
		return
	}
	when NET_NATIVE_LWS {
		if t.handle != nil do arws_client_close(t.handle, 2)
	}
}

net_transport_destroy :: proc(t: ^Net_Transport) {
	if t.pipe != nil {
		t.pipe.closed = true
		t^ = {}
		return
	}
	when NET_NATIVE_LWS {
		if t.handle != nil do arws_client_destroy(t.handle)
	}
	t^ = {}
}

// Platform cryptographic randomness for codes, tokens, and seeds. Never the
// gameplay PCG.
net_random_bytes :: proc(buf: []byte) {
	crypto.rand_bytes(buf)
}

net_transport_sleep_ms :: proc(ms: int) {
	time.sleep(time.Duration(ms) * time.Millisecond)
}

// Diagnostics: complete inbound messages the game has not yet pulled.
net_transport_pending :: proc(t: ^Net_Transport) -> (count: int, bytes: int) {
	when NET_NATIVE_LWS {
		if t.handle != nil {
			c: u32
			b: uint
			arws_client_pending(t.handle, &c, &b)
			return int(c), int(b)
		}
	}
	if t.pipe != nil do return len(t.pipe.to_client), 0
	return 0, 0
}
