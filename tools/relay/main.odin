// Arch Rogue multiplayer relay: a standalone Odin executable serving private
// plaintext WebSocket on loopback by default. Public TLS terminates at the
// reverse proxy; this process has no TLS listener, certificates, or keys.
//
//   build/archrogue_relay [--bind 127.0.0.1] [--port 8765]
//                         [--origins https://a.example,https://b.example]
//                         [--max-rooms 128] [--max-connections 512]
package main

import "core:crypto"
import "core:fmt"
import "core:os"
import "core:strconv"
import "core:strings"
import "core:sys/posix"
import "core:time"
import np "../../src/net_protocol"
import "core"

foreign import arws "../../vendor/libwebsockets/linux/libarws_relay.a"

Arws_Limits :: struct {
	max_message_bytes:  u32,
	max_inbound_bytes:  u32,
	max_outbound_bytes: u32,
	max_inbound_count:  u32,
	max_outbound_count: u32,
}

Arws_Server_Config :: struct {
	bind_address:    cstring,
	port:            i32,
	subprotocol:     cstring,
	ws_path:         cstring,
	health_path:     cstring,
	origins:         cstring,
	max_connections: u32,
	limits:          Arws_Limits,
}

ARWS_EV_NONE    :: 0
ARWS_EV_OPEN    :: 1
ARWS_EV_MESSAGE :: 2
ARWS_EV_CLOSED  :: 3

@(default_calling_convention = "c")
foreign arws {
	arws_server_create :: proc(config: ^Arws_Server_Config) -> rawptr ---
	arws_server_service :: proc(s: rawptr, wait_ms: i32) ---
	arws_server_next :: proc(s: rawptr, conn: ^u32, data: ^[^]u8, len: ^uint, close_code: ^i32) -> i32 ---
	arws_server_send :: proc(s: rawptr, conn: u32, data: [^]u8, len: uint) -> i32 ---
	arws_server_outbound_bytes :: proc(s: rawptr, conn: u32) -> uint ---
	arws_server_close :: proc(s: rawptr, conn: u32, code: i32, deadline_s: i32) ---
	arws_server_source :: proc(s: rawptr, conn: u32, out: [^]u8, cap: uint) -> i32 ---
	arws_server_connection_count :: proc(s: rawptr) -> u32 ---
	arws_server_destroy :: proc(s: rawptr) ---
}

stop_requested: bool

// Test-only impairment: delay every relay->client send by latency plus a
// uniform jitter, in order per connection. Never enabled in production.
Delayed_Send :: struct {
	at:   i64,
	conn: u32,
	data: []byte,
}
test_stats:      bool
live_conns:      map[u32]bool
last_stats_ms:   i64
test_latency_ms: int
test_jitter_ms:  int
delayed:         [dynamic]Delayed_Send
delay_rng:       u32 = 0x9E3779B9
delay_last_at:   map[u32]i64

on_signal :: proc "c" (sig: posix.Signal) {
	stop_requested = true
}

crypto_random :: proc(buf: []byte) {
	crypto.rand_bytes(buf)
}

log_line :: proc(text: string) {
	fmt.eprintfln("[relay] %s", text)
}

usage :: proc() {
	fmt.eprintln("usage: archrogue_relay [--bind ADDR] [--port N] [--origins A,B] [--max-rooms N] [--max-connections N] [--max-conns-per-source N] [--max-rooms-per-source N] [--waiting-max-s N]")
}

main :: proc() {
	bind := "127.0.0.1"
	port := 8765
	origins := ""
	max_rooms := np.MAX_ROOMS
	max_connections := 512
	hub_config := core.DEFAULT_CONFIG
	args := os.args[1:]
	for i := 0; i < len(args); i += 1 {
		value :: proc(args: []string, i: ^int) -> string {
			i^ += 1
			if i^ >= len(args) {
				usage()
				os.exit(2)
			}
			return args[i^]
		}
		switch args[i] {
		case "--bind": bind = value(args, &i)
		case "--port": port = parse_int_arg(value(args, &i))
		case "--origins": origins = value(args, &i)
		case "--max-rooms": max_rooms = parse_int_arg(value(args, &i))
		case "--max-connections": max_connections = parse_int_arg(value(args, &i))
		case "--max-conns-per-source": hub_config.max_conns_per_source = parse_int_arg(value(args, &i))
		case "--max-rooms-per-source": hub_config.max_rooms_per_source = parse_int_arg(value(args, &i))
		case "--waiting-max-s": hub_config.waiting_max_ms = i64(parse_int_arg(value(args, &i))) * 1000
		case "--test-latency-ms": test_latency_ms = parse_int_arg(value(args, &i))
		case "--test-jitter-ms": test_jitter_ms = parse_int_arg(value(args, &i))
		case "--test-stats": test_stats = true
		case "-h", "--help":
			usage()
			return
		case:
			usage()
			os.exit(2)
		}
	}
	if port <= 0 || port > 65535 || max_rooms <= 0 || max_connections <= 0 {
		usage()
		os.exit(2)
	}
	origin_lines, _ := strings.replace_all(origins, ",", "\n")

	config := Arws_Server_Config{
		bind_address    = strings.clone_to_cstring(bind),
		port            = i32(port),
		subprotocol     = np.SUBPROTOCOL,
		ws_path         = np.WS_PATH,
		health_path     = np.HEALTH_PATH,
		origins         = strings.clone_to_cstring(origin_lines),
		max_connections = u32(max_connections),
		limits = {
			max_message_bytes  = np.MAX_MESSAGE_BYTES,
			// Bound across the whole relay; queues are not preallocated.
			max_inbound_bytes  = 32 * 1024 * 1024,
			max_outbound_bytes = 2 * 1024 * 1024, // per connection
			max_inbound_count  = 512,
			max_outbound_count = 256,
		},
	}
	server := arws_server_create(&config)
	if server == nil {
		fmt.eprintfln("[relay] could not listen on %s:%d", bind, port)
		os.exit(1)
	}
	defer arws_server_destroy(server)

	posix.signal(.SIGINT, on_signal)
	posix.signal(.SIGTERM, on_signal)

	hub: core.Hub
	hub_config.max_rooms = max_rooms
	core.hub_init(&hub, hub_config, crypto_random)
	hub.log = log_line
	defer core.hub_destroy(&hub)

	log_line(fmt.tprintf("listening on ws://%s:%d%s (protocol %s)", bind, port, np.WS_PATH, np.SUBPROTOCOL))
	log_line(fmt.tprintf("limits: %d rooms, %d connections, per source %d connections / %d rooms, waiting rooms expire after %d s", max_rooms, max_connections, hub_config.max_conns_per_source, hub_config.max_rooms_per_source, hub_config.waiting_max_ms / 1000))
	if test_latency_ms > 0 || test_jitter_ms > 0 do log_line(fmt.tprintf("TEST IMPAIRMENT: +%d ms latency, %d ms jitter on relay->client sends", test_latency_ms, test_jitter_ms))
	relay_start = time.tick_now()
	last_tick: i64 = 0
	for !stop_requested {
		arws_server_service(server, 20)
		now := relay_now()
		for {
			conn: u32
			data: [^]u8
			length: uint
			code: i32
			kind := arws_server_next(server, &conn, &data, &length, &code)
			if kind == ARWS_EV_NONE do break
			switch kind {
			case ARWS_EV_OPEN:
				live_conns[conn] = true
				source_buf: [64]u8
				n := arws_server_source(server, conn, raw_data(source_buf[:]), len(source_buf))
				source := n > 0 ? string(source_buf[:n]) : ""
				core.hub_open(&hub, core.Conn_Id(conn), now, source)
			case ARWS_EV_MESSAGE: core.hub_receive(&hub, core.Conn_Id(conn), data[:length], now)
			case ARWS_EV_CLOSED:
				delete_key(&live_conns, conn)
				core.hub_closed(&hub, core.Conn_Id(conn), now, int(code))
			}
			flush(server, &hub)
		}
		if now - last_tick >= 250 {
			core.hub_tick(&hub, now)
			last_tick = now
		}
		flush(server, &hub)
		release_delayed(server, now)
		if test_stats && now - last_stats_ms >= 1000 {
			last_stats_ms = now
			for conn in live_conns {
				log_line(fmt.tprintf("stats t=%d conn %d outbound %d B queued", now, conn, arws_server_outbound_bytes(server, conn)))
			}
		}
		free_all(context.temp_allocator)
	}
	log_line("shutting down")
}

flush :: proc(server: rawptr, hub: ^core.Hub) {
	for action in hub.out {
		switch action.kind {
		case .Send:
			if test_latency_ms > 0 || test_jitter_ms > 0 {
				delay_rng = delay_rng * 1664525 + 1013904223
				jitter := test_jitter_ms > 0 ? i64(delay_rng >> 8) % i64(test_jitter_ms + 1) : 0
				at := relay_now() + i64(test_latency_ms) + jitter
				if last, ok := delay_last_at[u32(action.conn)]; ok do at = max(at, last)
				delay_last_at[u32(action.conn)] = at
				copy_ := make([]byte, len(action.data))
				copy(copy_, action.data)
				append(&delayed, Delayed_Send{at, u32(action.conn), copy_})
				continue
			}
			if arws_server_send(server, u32(action.conn), raw_data(action.data), uint(len(action.data))) == 0 {
				// A slow reader that cannot take more is disconnected rather
				// than allowed to grow an unbounded backlog.
				log_line(fmt.tprintf("conn %d: outbound queue refused %d bytes (%d queued); closing 1013", action.conn, len(action.data), arws_server_outbound_bytes(server, u32(action.conn))))
				arws_server_close(server, u32(action.conn), 1013, 2)
			}
		case .Close:
			arws_server_close(server, u32(action.conn), i32(action.close_code), 2)
		}
	}
	core.hub_actions_clear(hub)
}

parse_int_arg :: proc(text: string) -> int {
	n, ok := strconv.parse_int(text, 10)
	if !ok {
		usage()
		os.exit(2)
	}
	return n
}

relay_start: time.Tick

relay_now :: proc() -> i64 {
	return i64(time.duration_milliseconds(time.tick_since(relay_start)))
}

release_delayed :: proc(server: rawptr, now: i64) {
	for len(delayed) > 0 && delayed[0].at <= now {
		d := delayed[0]
		ordered_remove(&delayed, 0)
		// A refused delayed send is either a closed connection or a full
		// queue; the live path already closes slow readers, so just drop.
		_ = arws_server_send(server, d.conn, raw_data(d.data), uint(len(d.data)))
		delete(d.data)
	}
}
