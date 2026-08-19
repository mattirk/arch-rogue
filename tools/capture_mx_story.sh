#!/usr/bin/env bash
# Build once, then record deterministic MX-story panel captures at small, desktop, and 4K sizes.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$ROOT/build/mx-story-captures"
BIN="$ROOT/build/archrogue"
SEED="${ARCH_ROGUE_SEED:-520199}"
SHOT_FRAME="${ARCH_ROGUE_SHOT_FRAME:-2}"
SOFTWARE_GL="${ARCH_ROGUE_CAPTURE_SOFTWARE_GL:-1}"

runner=()
display_ready=false
local_xvfb_pid=""
cleanup() {
  if [[ -n "$local_xvfb_pid" ]]; then
    kill "$local_xvfb_pid" >/dev/null 2>&1 || true
    wait "$local_xvfb_pid" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT
if [[ -n "${DISPLAY:-}" ]]; then
  if command -v xset >/dev/null 2>&1; then
    if xset -q >/dev/null 2>&1; then display_ready=true; fi
  else
    display_ready=true
  fi
fi
if [[ "$display_ready" != true ]]; then
  if command -v xvfb-run >/dev/null 2>&1; then
    runner=(xvfb-run -a -s "-screen 0 3840x2160x24")
  elif [[ -x "$ROOT/build/xvfb-root/usr/bin/Xvfb" ]]; then
    export DISPLAY=:97
    "$ROOT/build/xvfb-root/usr/bin/Xvfb" "$DISPLAY" -screen 0 3840x2160x24 -nolisten tcp -noreset >"$OUT-xvfb.log" 2>&1 &
    local_xvfb_pid=$!
    for _ in {1..50}; do
      if xset -q >/dev/null 2>&1; then display_ready=true; break; fi
      sleep .1
    done
    if [[ "$display_ready" != true ]]; then
      cat "$OUT-xvfb.log" >&2
      printf 'capture_mx_story.sh: build-local Xvfb did not become ready\n' >&2
      exit 2
    fi
  else
    printf 'capture_mx_story.sh: no reachable display; install xorg-server-xvfb or run from a graphical session\n' >&2
    exit 2
  fi
fi

mkdir -p "$OUT/config"
rm -f "$OUT"/*.png
"$ROOT/build.sh" build
captures=()

verify_dimensions() {
  python - "$1" "$2" "$3" <<'PY'
from pathlib import Path
import struct
import sys

path = Path(sys.argv[1])
expected = (int(sys.argv[2]), int(sys.argv[3]))
data = path.read_bytes()
if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
    raise SystemExit(f"capture_mx_story.sh: {path} is not a canonical PNG")
actual = struct.unpack(">II", data[16:24])
if actual != expected:
    raise SystemExit(
        f"capture_mx_story.sh: {path.name} is {actual[0]}x{actual[1]}, "
        f"expected {expected[0]}x{expected[1]}"
    )
PY
}

capture() {
  local scenario="$1"
  local archetype="$2"
  local width="$3"
  local height="$4"
  local relative="build/mx-story-captures/${scenario}_${width}x${height}.png"
  local log="$OUT/${scenario}_${width}x${height}.log"
  printf 'MX-story capture %-14s archetype=%-8s %sx%s\n' "$scenario" "$archetype" "$width" "$height"
  if ! (
    cd "$ROOT"
    env -u ARCH_ROGUE_LIGHTING -u ARCH_ROGUE_ZOOM -u ARCH_ROGUE_REVEAL -u ARCH_ROGUE_DEV \
      -u ARCH_ROGUE_OPEN -u ARCH_ROGUE_BAG -u ARCH_ROGUE_SPAWN -u ARCH_ROGUE_DEPTH \
      -u ARCH_ROGUE_MX6_CAPTURE -u ARCH_ROGUE_MX7_CAPTURE -u ARCH_ROGUE_MX7_PERF \
      -u ARCH_ROGUE_CAPTURE_THEME -u ARCH_ROGUE_CAPTURE_DARK -u ARCH_ROGUE_CAPTURE_DOOR \
      XDG_CONFIG_HOME="$OUT/config" \
      ARCH_ROGUE_SEED="$SEED" \
      ARCH_ROGUE_PLAY=1 \
      ARCH_ROGUE_ARCHETYPE="$archetype" \
      ARCH_ROGUE_MX_STORY_CAPTURE="$scenario" \
      ARCH_ROGUE_CAPTURE_WIDTH="$width" \
      ARCH_ROGUE_CAPTURE_HEIGHT="$height" \
      ARCH_ROGUE_SHOT="$relative" \
      ARCH_ROGUE_SHOT_FRAME="$SHOT_FRAME" \
      ARCH_ROGUE_MIST=0 \
      LIBGL_ALWAYS_SOFTWARE="$SOFTWARE_GL" \
      "${runner[@]}" "$BIN"
  ) >"$log" 2>&1; then
    cat "$log" >&2
    exit 1
  fi
  if [[ ! -s "$ROOT/$relative" ]]; then
    printf 'capture_mx_story.sh: missing or empty screenshot %s\n' "$ROOT/$relative" >&2
    exit 1
  fi
  verify_dimensions "$ROOT/$relative" "$width" "$height"
  captures+=("$ROOT/$relative")
}

scenarios=(
  "omen_initial acolyte"
  "relic_choices acolyte"
  "guest ranger"
  "soul warden"
  "ending arcanist"
)
resolutions=(
  "640 480"
  "1280 720"
  "3840 2160"
)

for scenario_entry in "${scenarios[@]}"; do
  read -r scenario archetype <<<"$scenario_entry"
  for resolution_entry in "${resolutions[@]}"; do
    read -r width height <<<"$resolution_entry"
    capture "$scenario" "$archetype" "$width" "$height"
  done
done

if command -v montage >/dev/null 2>&1; then
  montage "${captures[@]}" -thumbnail 640x360 -tile 3x -geometry +4+4 "$OUT/mx-story-montage.png"
  printf 'Montage: %s\n' "$OUT/mx-story-montage.png"
fi
printf 'Captured %d images in %s\n' "${#captures[@]}" "$OUT"
