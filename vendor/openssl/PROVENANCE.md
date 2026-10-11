# OpenSSL provenance

Source: OpenSSL 3.6.5 (Apache-2.0), pinned in `pin.properties` with the
official release checksum. Built by `tools/multiplayer/build_openssl.sh`
into static `linux/libssl.a` and `linux/libcrypto.a` (checksums in
`linux/SHA256SUMS`), linked into the Linux game client together with
`vendor/libwebsockets/linux/libarws_client.a`, whose lws objects were compiled
against OpenSSL 3.6.5 headers.

Why static: the shipped Linux binary must not depend on a `libssl`/`libcrypto`
soname — distros and the Steam Linux Runtime disagree on which exists, and a
missing one makes the game fail to start (observed on Steam Deck, 2026-10-11).
Human decision 2026-10-09: bundle statically.

Configuration: `linux-x86_64`, `no-shared no-tests no-apps no-docs no-engine
no-module no-dso no-legacy no-comp no-zlib no-ssl3 no-weak-ssl-ciphers
no-srp no-psk no-dgram no-quic no-ct no-ocsp no-ts no-cms no-rfc3779
no-gost`, `-fPIC`, `-ffile-prefix-map` for reproducibility,
`--openssldir=/etc/ssl` so default certificate verification uses the system
trust store at `/etc/ssl` (Arch, Debian/Ubuntu, the Steam Linux Runtime;
`SSL_CERT_DIR`/`SSL_CERT_FILE` still override). glibc C23-only imports
(`__isoc23_*`) are rewritten to classic symbols as for raylib and
libwebsockets, and the archives are made deterministic with `objcopy -D`.

Only the client uses TLS; the relay (`tools/relay`) has no TLS backend and
does not link OpenSSL (public TLS terminates at the reverse proxy).
