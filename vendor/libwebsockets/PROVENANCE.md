# libwebsockets provenance

Source: libwebsockets v4.3.5 (MIT), pinned in `pin.properties` (URL and
SHA-256 of the GitHub tag tarball). Built by
`tools/multiplayer/build_libwebsockets.sh` (`./build.sh net-deps`) into two
reproducible static archives under `linux/` with `SHA256SUMS`:

- `libarws_client.a` — client role with OpenSSL TLS (system OpenSSL at link
  time), async DNS, and the `arws` facade from `shim/` compiled with
  `ARWS_CLIENT_ONLY`. Linked by the game (`src/net_transport_native.odin`).
  The server role stays compiled in because lws adopts the async-DNS UDP
  socket through its raw-socket server role; the game never listens.
- `libarws_relay.a` — server role, no TLS backend, facade compiled with
  `ARWS_SERVER_ONLY`. Linked by `tools/relay`.

Build flags: Release, position independent, no shared library, no test apps,
no extensions, HTTP/2 off, LEJP/custom headers/conmon/cookie jar/netlink/SMD
off, IPv6 on, libcap off, `LWS_REPRODUCIBLE` with `-ffile-prefix-map`.

glibc compatibility: archives built on glibc >= 2.38 hosts reference the C23
entry points `__isoc23_strtol`/`__isoc23_strtoll` and friends, which Ubuntu
22.04 (glibc 2.35) lacks. The build script rewrites them to the classic
symbols with `objcopy --redefine-sym` (the same treatment as
`vendor/raylib/linux/PROVENANCE.md`) and fails if any `__isoc23_` import
remains; `.github/workflows/server-deploy.yml` re-checks this before linking.

The facade in `shim/arws.c` is project code (not upstream): bounded owned
message queues, drain loops, multi-write per writeable callback, Origin/path/
subprotocol filtering, and a `/healthz` route. It contains no WebSocket
protocol implementation.
