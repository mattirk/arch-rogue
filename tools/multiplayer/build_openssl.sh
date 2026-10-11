#!/usr/bin/env bash
# Build the pinned OpenSSL as static libraries for the Linux game client, so
# the shipped binary has no libssl/libcrypto runtime dependency (human
# decision 2026-10-09: bundle statically; Steam runtime containers and
# players' distros differ in OpenSSL sonames).
#
#   bash tools/multiplayer/build_openssl.sh
#
# Outputs (committed, like vendor/raylib/linux/libraylib.a):
#   vendor/openssl/linux/libssl.a
#   vendor/openssl/linux/libcrypto.a
#   vendor/openssl/linux/SHA256SUMS
#   vendor/openssl/LICENSE.txt (from the tarball)
#
# Needs perl, make, and a C compiler; no cmake. Ordinary game builds never
# run this script.
set -euo pipefail
cd "$(dirname "$0")/../.."
root=$PWD

# shellcheck source=/dev/null
source vendor/openssl/pin.properties

work=build/deps/openssl
mkdir -p "$work"
tarball="$work/openssl-$OPENSSL_VERSION.tar.gz"
if [[ ! -f $tarball ]]; then
  curl -fsSL -o "$tarball.part" "$OPENSSL_URL"
  mv "$tarball.part" "$tarball"
fi
echo "$OPENSSL_SHA256  $tarball" | sha256sum -c --quiet -

src="$work/src"
rm -rf "$src"
mkdir -p "$src"
tar -xzf "$tarball" -C "$src" --strip-components=1

# Trust store: OPENSSLDIR is where SSL_CTX_set_default_verify_paths looks when
# SSL_CERT_DIR/SSL_CERT_FILE are unset. /etc/ssl holds the system bundle on
# Arch/Debian/Ubuntu and inside the Steam Linux Runtime; Fedora-family hosts
# symlink it there too.
(
  cd "$src"
  ./Configure linux-x86_64 \
    --prefix=/usr --openssldir=/etc/ssl --libdir=lib \
    no-shared no-tests no-apps no-docs no-engine no-module no-dso \
    no-legacy no-comp no-zlib no-ssl3 no-weak-ssl-ciphers no-srp no-psk \
    no-dgram no-quic no-ct no-ocsp no-ts no-cms no-rfc3779 no-gost \
    -fPIC -ffile-prefix-map="$root=." >"$root/$work/configure.log"
  make -j"$(nproc)" build_libs >"$root/$work/make.log"
)

out=vendor/openssl/linux
mkdir -p "$out"
cp "$src/libssl.a" "$src/libcrypto.a" "$out/"
cp "$src/LICENSE.txt" vendor/openssl/LICENSE.txt

# glibc >= 2.38 headers rename strtol & co. to C23 entry points absent from
# older runtimes (Ubuntu 22.04 / glibc 2.35); rewrite to the classic symbols
# and refuse any archive that still imports one (vendor/raylib treatment).
for lib in "$out/libssl.a" "$out/libcrypto.a"; do
  objcopy \
    --redefine-sym __isoc23_strtol=strtol \
    --redefine-sym __isoc23_strtoul=strtoul \
    --redefine-sym __isoc23_strtoll=strtoll \
    --redefine-sym __isoc23_strtoull=strtoull \
    --redefine-sym __isoc23_sscanf=__isoc99_sscanf \
    --redefine-sym __isoc23_fscanf=__isoc99_fscanf \
    --redefine-sym __isoc23_scanf=__isoc99_scanf \
    "$lib"
  if nm -u "$lib" | grep -q "__isoc23_"; then
    echo "error: $lib still imports glibc C23-only symbols" >&2
    exit 1
  fi
done
# Static archives from `ar` carry no timestamps only when built with -D; make
# them deterministic for the checksum.
for lib in "$out/libssl.a" "$out/libcrypto.a"; do objcopy -D "$lib"; done
(cd "$out" && sha256sum libssl.a libcrypto.a > SHA256SUMS)
cat "$out/SHA256SUMS"
