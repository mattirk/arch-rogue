#!/usr/bin/env bash
# Build once, then record the deterministic MX.7 world-polish acceptance matrix.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$ROOT/build/mx7-captures"
BIN="$ROOT/build/archrogue"
SEED="${ARCH_ROGUE_SEED:-9707}"
SHOT_FRAME="${ARCH_ROGUE_SHOT_FRAME:-12}"

runner=()
display_ready=false
if [[ -n "${DISPLAY:-}" ]]; then
  if command -v xset >/dev/null 2>&1; then
    if xset -q >/dev/null 2>&1; then display_ready=true; fi
  else
    display_ready=true
  fi
fi
if [[ "$display_ready" != true ]]; then
  if command -v xvfb-run >/dev/null 2>&1; then
    runner=(xvfb-run -a)
  else
    printf 'capture_mx7.sh: no reachable display; install xvfb-run or run from a graphical session\n' >&2
    exit 2
  fi
fi

mkdir -p "$OUT"
rm -f "$OUT"/*.png
"$ROOT/build.sh" build
captures=()

capture() {
  local stem="$1"
  local scenario="$2"
  local theme="$3"
  local depth="$4"
  local dark="$5"
  local reveal="${6:-0}"
  local door="${7:-closed}"
  local relative="build/mx7-captures/${stem}.png"
  local reveal_env=()
  if [[ "$reveal" == 1 ]]; then reveal_env=(ARCH_ROGUE_REVEAL=1); fi
  printf 'MX.7 capture %-30s scene=%-8s theme=%s depth=%s dark=%s\n' "$stem" "$scenario" "$theme" "$depth" "$dark"
  (
    cd "$ROOT"
    env -u ARCH_ROGUE_LIGHTING -u ARCH_ROGUE_ZOOM -u ARCH_ROGUE_REVEAL -u ARCH_ROGUE_DEV -u ARCH_ROGUE_OPEN -u ARCH_ROGUE_BAG -u ARCH_ROGUE_SPAWN -u ARCH_ROGUE_MX6_CAPTURE -u ARCH_ROGUE_MX7_PERF -u ARCH_ROGUE_PERF_FRAMES -u ARCH_ROGUE_PERF_WARMUP \
      ARCH_ROGUE_SEED="$SEED" \
      ARCH_ROGUE_PLAY=1 \
      ARCH_ROGUE_ARCHETYPE=warden \
      ARCH_ROGUE_DEPTH="$depth" \
      ARCH_ROGUE_MX7_CAPTURE="$scenario" \
      ARCH_ROGUE_CAPTURE_THEME="$theme" \
      ARCH_ROGUE_CAPTURE_DARK="$dark" \
      ARCH_ROGUE_CAPTURE_DOOR="$door" \
      ARCH_ROGUE_SHOT="$relative" \
      ARCH_ROGUE_SHOT_FRAME="$SHOT_FRAME" \
      ARCH_ROGUE_MIST=0 \
      LIBGL_ALWAYS_SOFTWARE=1 \
      "${reveal_env[@]}" \
      "${runner[@]}" "$BIN"
  )
  if [[ ! -s "$ROOT/$relative" ]]; then
    printf 'capture_mx7.sh: missing or empty screenshot %s\n' "$ROOT/$relative" >&2
    exit 1
  fi
  captures+=("$ROOT/$relative")
}

# All eight themes at the literal shallow/deep × normal/dark matrix.
for theme in $(seq 0 7); do
  capture "theme_${theme}_shallow_normal" baseline "$theme" 1 0
  capture "theme_${theme}_shallow_dark" baseline "$theme" 1 1
  capture "theme_${theme}_deep_normal" baseline "$theme" 8 0
  capture "theme_${theme}_deep_dark" baseline "$theme" 8 1
done

# Focused painter/FOW/content coverage. Forced special-room staging means these
# captures do not depend on a seed happening to roll Shop/Bar/Garden.
capture door_closed door 0 4 0 0 closed
capture door_open door 0 4 0 0 open
capture stairs stairs 1 8 1
capture shop shop 2 4 0
capture bar bar 3 5 0
capture garden garden 4 6 0
capture boss boss 5 10 1
capture crowd crowd 6 8 0
capture loot loot 7 7 0
capture trap trap 0 5 0
capture shrine shrine 1 6 0
capture secret secret 2 7 0
capture fow_masked fow 3 8 1
capture fow_reveal_reference fow 3 8 1 1

if command -v montage >/dev/null 2>&1; then
  montage "${captures[@]}" -thumbnail 320x180 -tile 4x -geometry +4+4 "$OUT/mx7-montage.png"
  printf 'Montage: %s\n' "$OUT/mx7-montage.png"
fi
printf 'Captured %d images in %s\n' "${#captures[@]}" "$OUT"
