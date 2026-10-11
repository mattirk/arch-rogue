#!/usr/bin/env bash
# Automated multi-process co-op soak: real relay, real libwebsockets sockets,
# one headless bot process per seat, independent real-time frame loops.
#
#   bash tools/coop_soak.sh                       # 60 fps, no impairment, 20 s
#   SECONDS_PLAY=40 FPS=30 LATENCY=80 JITTER=40 bash tools/coop_soak.sh
#   DROP_AT=6 bash tools/coop_soak.sh             # joiner force-closes once
#   SCRIPT=walk bash tools/coop_soak.sh           # idle | walk | combat
#
# Exits non-zero when either bot reports a failure (unexpected disconnect,
# rejected snapshots, fog lost on reconnect, drawn-seat jumps).
set -euo pipefail
cd "$(dirname "$0")/.."

PORT="${PORT:-18800}"
SECONDS_PLAY="${SECONDS_PLAY:-20}"
FPS="${FPS:-60}"
HOST_FPS="${HOST_FPS:-$FPS}"
JOIN_FPS="${JOIN_FPS:-$FPS}"
RELAY_STATS="${RELAY_STATS:-0}"
LATENCY="${LATENCY:-0}"
JITTER="${JITTER:-0}"
DROP_AT="${DROP_AT:--1}"
SCRIPT="${SCRIPT:-combat}"
OUT="${OUT:-build/coop-soak}"
mkdir -p "$OUT"
rm -f "$OUT/code"

if [[ "${SKIP_BUILD:-}" != "1" ]]; then
  odin build tools/relay -out:build/archrogue_relay -vet -o:speed
  odin build tools/coop_bot.odin -file -out:build/coop_bot -vet
fi

STATS_FLAG=(); [[ "$RELAY_STATS" == "1" ]] && STATS_FLAG=(--test-stats)
build/archrogue_relay --port "$PORT" --test-latency-ms "$LATENCY" --test-jitter-ms "$JITTER" "${STATS_FLAG[@]}" >"$OUT/relay.log" 2>&1 &
RELAY=$!
trap 'kill $RELAY 2>/dev/null || true' EXIT
sleep 0.3

URL="ws://127.0.0.1:$PORT/mp"
build/coop_bot --role host --url "$URL" --code-file "$OUT/code" --seconds "$SECONDS_PLAY" --fps "$HOST_FPS" --script "$SCRIPT" >"$OUT/host.out" 2>"$OUT/host.log" &
HOST=$!
build/coop_bot --role join --url "$URL" --code-file "$OUT/code" --seconds "$SECONDS_PLAY" --fps "$JOIN_FPS" --script "$SCRIPT" --drop-at "$DROP_AT" --archetype Rogue >"$OUT/join.out" 2>"$OUT/join.log" &
JOIN=$!

HS=0; JS=0
wait $HOST || HS=$?
wait $JOIN || JS=$?
echo "== host (exit $HS)"; cat "$OUT/host.out"
echo "== join (exit $JS)"; cat "$OUT/join.out"
echo "== relay log"; cat "$OUT/relay.log"
if (( HS != 0 || JS != 0 )); then
  echo "== host log (tail)"; tail -20 "$OUT/host.log"
  echo "== join log (tail)"; tail -20 "$OUT/join.log"
  exit 1
fi
echo "SOAK PASS (fps $FPS, latency $LATENCY+$JITTER ms, drop_at $DROP_AT, $SECONDS_PLAY s)"
