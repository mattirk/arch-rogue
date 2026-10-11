#!/usr/bin/env bash
# Rebuild the pinned libwebsockets + arws shim static archives for Linux.
#
#   bash tools/multiplayer/build_libwebsockets.sh
#
# Outputs (committed, like vendor/raylib/linux/libraylib.a):
#   vendor/libwebsockets/linux/libarws_client.a  client role, OpenSSL TLS
#   vendor/libwebsockets/linux/libarws_relay.a   server role, no TLS backend
#   vendor/libwebsockets/linux/SHA256SUMS
#
# Ordinary game/relay builds never run this script or touch the network.
set -euo pipefail
cd "$(dirname "$0")/../.."
root=$PWD

# shellcheck source=/dev/null
source vendor/libwebsockets/pin.properties

work=build/deps/libwebsockets
mkdir -p "$work"
tarball="$work/libwebsockets-$LWS_VERSION.tar.gz"
if [[ ! -f $tarball ]]; then
  curl -fsSL -o "$tarball.part" "$LWS_URL"
  mv "$tarball.part" "$tarball"
fi
echo "$LWS_SHA256  $tarball" | sha256sum -c --quiet -

src="$work/src"
rm -rf "$src"
mkdir -p "$src"
tar -xzf "$tarball" -C "$src" --strip-components=1

common=(
  -DCMAKE_BUILD_TYPE=Release
  -DCMAKE_POLICY_VERSION_MINIMUM=3.5
  -DCMAKE_DISABLE_FIND_PACKAGE_Git=ON
  -DLWS_REPRODUCIBLE=ON
  "-DCMAKE_C_FLAGS=-ffile-prefix-map=$root=."
  -DCMAKE_C_COMPILER="${CC:-cc}"
  -DCMAKE_POSITION_INDEPENDENT_CODE=ON
  -DDISABLE_WERROR=ON
  -DLWS_WITH_SHARED=OFF
  -DLWS_WITH_STATIC=ON
  -DLWS_WITHOUT_TESTAPPS=ON
  -DLWS_WITH_MINIMAL_EXAMPLES=OFF
  -DLWS_WITHOUT_EXTENSIONS=ON
  -DLWS_WITH_HTTP2=OFF
  -DLWS_ROLE_RAW_FILE=OFF
  -DLWS_WITH_LEJP=OFF
  -DLWS_WITH_CUSTOM_HEADERS=OFF
  -DLWS_WITH_CONMON=OFF
  -DLWS_WITH_CACHE_NSCOOKIEJAR=OFF
  -DLWS_WITH_NETLINK=OFF
  -DLWS_WITH_SYS_SMD=OFF
  -DLWS_IPV6=ON
  -DLWS_HAVE_LIBCAP=OFF
)

build_flavor() {
  local flavor=$1 define=$2
  shift 2
  local bdir="$work/build-$flavor"
  rm -rf "$bdir"
  cmake -S "$src" -B "$bdir" -G "Unix Makefiles" "${common[@]}" "$@" >"$work/cmake-$flavor.log"
  cmake --build "$bdir" --target websockets -j"$(nproc)" >"$work/make-$flavor.log"
  "${CC:-cc}" -c -O2 -fPIC -Wall -Wextra -ffile-prefix-map="$root"=. -D"$define" \
    -I"$bdir/include" -I"$src/include" \
    vendor/libwebsockets/shim/arws.c -o "$bdir/arws.o"
  local out="vendor/libwebsockets/linux/libarws_$flavor.a"
  mkdir -p vendor/libwebsockets/linux
  rm -f "$out"
  # Merge the shim object and libwebsockets into one archive.
  local objdir="$bdir/objs"
  mkdir -p "$objdir"
  (cd "$objdir" && ar x "$root/$bdir/lib/libwebsockets.a")
  ar rcsD "$out" "$bdir/arws.o" "$objdir"/*.o
  # glibc >= 2.38 headers rename strtol & co. to C23 entry points
  # (__isoc23_*) that older runtimes such as Ubuntu 22.04 / glibc 2.35 lack.
  # Rewrite them to the classic symbols, as vendor/raylib/linux/PROVENANCE.md
  # does for raylib, and refuse to ship an archive that still imports any.
  objcopy \
    --redefine-sym __isoc23_strtol=strtol \
    --redefine-sym __isoc23_strtoul=strtoul \
    --redefine-sym __isoc23_strtoll=strtoll \
    --redefine-sym __isoc23_strtoull=strtoull \
    --redefine-sym __isoc23_strtoimax=strtoimax \
    --redefine-sym __isoc23_strtoumax=strtoumax \
    --redefine-sym __isoc23_sscanf=__isoc99_sscanf \
    --redefine-sym __isoc23_fscanf=__isoc99_fscanf \
    --redefine-sym __isoc23_scanf=__isoc99_scanf \
    --redefine-sym __isoc23_vsscanf=__isoc99_vsscanf \
    "$out"
  if nm -u "$out" | grep -q "__isoc23_"; then
    echo "error: $out still imports glibc C23-only symbols:" >&2
    nm -u "$out" | grep -o "__isoc23_[a-z0-9_]*" | sort -u >&2
    exit 1
  fi
}

# The client keeps lws's server role compiled (it never listens): async DNS
# adopts its UDP socket through the raw-socket server role.
build_flavor client ARWS_CLIENT_ONLY \
  -DLWS_WITH_SSL=ON -DLWS_WITHOUT_SERVER=OFF -DLWS_WITH_SYS_ASYNC_DNS=ON \
  -DLWS_SSL_CLIENT_USE_OS_CA_CERTS=ON
build_flavor relay ARWS_SERVER_ONLY \
  -DLWS_WITH_SSL=OFF -DLWS_WITHOUT_CLIENT=ON

(cd vendor/libwebsockets/linux && sha256sum libarws_client.a libarws_relay.a > SHA256SUMS)
cat vendor/libwebsockets/linux/SHA256SUMS
