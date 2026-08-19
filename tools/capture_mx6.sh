#!/usr/bin/env bash
# Build once, then capture a deterministic MX.6 readability matrix.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$ROOT/build/mx6-captures"
BIN="$ROOT/build/archrogue"
SEED="${ARCH_ROGUE_SEED:-9606}"
SHOT_FRAME="${ARCH_ROGUE_SHOT_FRAME:-12}"

runner=()
display_ready=false
if [[ -n "${DISPLAY:-}" ]]; then
  if command -v xset >/dev/null 2>&1; then
    if xset -q >/dev/null 2>&1; then
      display_ready=true
    fi
  else
    display_ready=true
  fi
fi
if [[ "$display_ready" != true ]]; then
  if command -v xvfb-run >/dev/null 2>&1; then
    runner=(xvfb-run -a)
  else
    printf 'capture_mx6.sh: no reachable display; install xvfb-run or run from a graphical session\n' >&2
    exit 2
  fi
fi

mkdir -p "$OUT"
rm -f "$OUT"/*.png
"$ROOT/build.sh" build

directions=(
  south south-east east north-east north north-west west south-west
)
archetypes=(warden rogue arcanist acolyte ranger)
slots=(big_hit bolt class dash)
captures=()
capture_index=0

capture() {
  local archetype="$1"
  local scenario="$2"
  local direction="${directions[$((capture_index % ${#directions[@]}))]}"
  local stem="${archetype}_${scenario}_${direction}"
  local relative="build/mx6-captures/${stem}.png"

  printf 'MX.6 capture %-9s %-18s %s\n' "$archetype" "$scenario" "$direction"
  (
    cd "$ROOT"
    env \
      ARCH_ROGUE_SEED="$SEED" \
      ARCH_ROGUE_PLAY=1 \
      ARCH_ROGUE_ARCHETYPE="$archetype" \
      ARCH_ROGUE_CAPTURE_DIR="$direction" \
      ARCH_ROGUE_MX6_CAPTURE="$scenario" \
      ARCH_ROGUE_SHOT="$relative" \
      ARCH_ROGUE_SHOT_FRAME="$SHOT_FRAME" \
      ARCH_ROGUE_REVEAL=1 \
      ARCH_ROGUE_MIST=0 \
      LIBGL_ALWAYS_SOFTWARE=1 \
      "${runner[@]}" "$BIN"
  )
  captures+=("$ROOT/$relative")
  capture_index=$((capture_index + 1))
}

# All five archetypes across the four authored action-bar slots.
for archetype in "${archetypes[@]}"; do
  for scenario in "${slots[@]}"; do
    capture "$archetype" "$scenario"
  done
done

# Base click/melee is outside the four numbered action slots.
capture warden melee

for scenario in \
  enemy_base_melee enemy_base_ranged enemy_strike \
  enemy_bolt enemy_fan enemy_nova \
  boss_attack boss_cast; do
  capture warden "$scenario"
done

capture acolyte familiar_wisp
capture acolyte familiar_crow
capture ranger familiar_beast

# FOW safety A/B: the same wide Nova beside a room wall, with lighting off.
# The normal capture must clip at live LOS; reveal intentionally shows the
# unmasked footprint for a direct visual comparison.
fow_capture() {
  local stem="$1"
  local reveal="$2"
  local relative="build/mx6-captures/${stem}.png"
  local reveal_env=()
  if [[ "$reveal" == 1 ]]; then reveal_env=(ARCH_ROGUE_REVEAL=1); fi
  printf 'MX.6 capture %-9s %-18s %s\n' arcanist fow_nova north-west
  (
    cd "$ROOT"
    env \
      ARCH_ROGUE_SEED="$SEED" \
      ARCH_ROGUE_PLAY=1 \
      ARCH_ROGUE_ARCHETYPE=arcanist \
      ARCH_ROGUE_CAPTURE_DIR=north-west \
      ARCH_ROGUE_MX6_CAPTURE=fow_nova \
      ARCH_ROGUE_LIGHTING=0 \
      ARCH_ROGUE_SHOT="$relative" \
      ARCH_ROGUE_SHOT_FRAME="$SHOT_FRAME" \
      ARCH_ROGUE_MIST=0 \
      LIBGL_ALWAYS_SOFTWARE=1 \
      "${reveal_env[@]}" \
      "${runner[@]}" "$BIN"
  )
  captures+=("$ROOT/$relative")
}
fow_capture arcanist_fow_nova_masked 0
fow_capture arcanist_fow_nova_reveal_reference 1

if command -v montage >/dev/null 2>&1; then
  montage "${captures[@]}" \
    -thumbnail 320x180 \
    -tile 4x \
    -geometry +4+4 \
    "$OUT/mx6-montage.png"
  printf 'Montage: %s\n' "$OUT/mx6-montage.png"
fi

printf 'Captured %d images in %s\n' "${#captures[@]}" "$OUT"
