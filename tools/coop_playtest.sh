#!/usr/bin/env bash
# Two-window local co-op playtest: builds the game and relay, starts a relay on
# loopback, and launches a host and a guest window with separate save
# directories so neither touches your normal profile or solo run.
#
#   bash tools/coop_playtest.sh            # debug builds
#   bash tools/coop_playtest.sh --release  # optimized builds
#   PORT=9000 bash tools/coop_playtest.sh
#
# In each window: Title -> Co-op. The server field is preset to the local
# relay. Host a room in one window, type its code in the other, then Accept,
# pick archetypes, and Ready. F3 toggles the co-op network overlay.
set -euo pipefail
cd "$(dirname "$0")/.."

PORT="${PORT:-8765}"
MODE=build
[[ "${1:-}" == "--release" ]] && MODE=release

./build.sh "$MODE"
./build.sh relay

STATE="build/coop-playtest"
mkdir -p "$STATE/host" "$STATE/guest"

build/archrogue_relay --port "$PORT" >"$STATE/relay.log" 2>&1 &
RELAY=$!
cleanup() {
  kill "$RELAY" "${HOST:-}" "${GUEST:-}" 2>/dev/null || true
}
trap cleanup EXIT INT TERM
sleep 0.3

launch() {
  local role=$1
  XDG_DATA_HOME="$PWD/$STATE/$role" \
  ARCH_ROGUE_COOP=1 \
  ARCH_ROGUE_RELAY_URL="ws://127.0.0.1:$PORT/mp" \
    build/archrogue >"$STATE/$role.log" 2>&1 &
}
# Launched in this shell (not a subshell) so wait/kill see the children.
launch host; HOST=$!
launch guest; GUEST=$!
echo "relay pid $RELAY, host pid $HOST, guest pid $GUEST; logs in $STATE/"
echo "Title -> Co-op in each window. Host a room in one, enter its code in the other."
echo "Close both windows (or Ctrl+C here) to stop the relay."
wait "$HOST" "$GUEST" || true
