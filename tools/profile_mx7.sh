#!/usr/bin/env bash
# Release-build MX.7 visible-crowd benchmark. Run from a real graphical session;
# software GL/Xvfb is useful for correctness captures, not 60 FPS signoff.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$ROOT/build/mx7-perf"
BIN="$ROOT/build/archrogue"
RUNS="${ARCH_ROGUE_PERF_RUNS:-3}"
FRAMES="${ARCH_ROGUE_PERF_FRAMES:-600}"
WARMUP="${ARCH_ROGUE_PERF_WARMUP:-120}"
SEED="${ARCH_ROGUE_SEED:-9707}"

if [[ -z "${DISPLAY:-}" ]]; then
  printf 'profile_mx7.sh: a real GPU/display session is required for performance signoff\n' >&2
  exit 2
fi
if [[ "${LIBGL_ALWAYS_SOFTWARE:-0}" == 1 ]]; then
  printf 'profile_mx7.sh: refusing software GL; unset LIBGL_ALWAYS_SOFTWARE for signoff\n' >&2
  exit 2
fi
if command -v glxinfo >/dev/null 2>&1; then
  renderer="$(glxinfo -B 2>/dev/null | awk -F: '/OpenGL renderer string/ {sub(/^ /, "", $2); print tolower($2)}')"
  case "$renderer" in
    *llvmpipe*|*softpipe*|*swiftshader*)
      printf 'profile_mx7.sh: refusing software renderer: %s\n' "$renderer" >&2
      exit 2
      ;;
  esac
fi

mkdir -p "$OUT"
rm -f "$OUT"/*.txt
"$ROOT/build.sh" release

for run in $(seq 1 "$RUNS"); do
  log="$OUT/run_${run}.txt"
  printf 'MX.7 perf run %s/%s\n' "$run" "$RUNS"
  (
    cd "$ROOT"
    env -u ARCH_ROGUE_LIGHTING -u ARCH_ROGUE_MIST -u ARCH_ROGUE_ZOOM -u ARCH_ROGUE_REVEAL -u ARCH_ROGUE_DEV -u ARCH_ROGUE_OPEN -u ARCH_ROGUE_BAG -u ARCH_ROGUE_SPAWN -u ARCH_ROGUE_MX6_CAPTURE -u ARCH_ROGUE_MX7_CAPTURE -u ARCH_ROGUE_SHOT -u ARCH_ROGUE_SHOT_FRAME -u ARCH_ROGUE_CAPTURE_DOOR -u ARCH_ROGUE_CAPTURE_DIR \
      ARCH_ROGUE_SEED="$SEED" \
      ARCH_ROGUE_PLAY=1 \
      ARCH_ROGUE_ARCHETYPE=warden \
      ARCH_ROGUE_DEPTH=8 \
      ARCH_ROGUE_CAPTURE_THEME=6 \
      ARCH_ROGUE_CAPTURE_DARK=0 \
      ARCH_ROGUE_MX7_PERF=1 \
      ARCH_ROGUE_PERF_FRAMES="$FRAMES" \
      ARCH_ROGUE_PERF_WARMUP="$WARMUP" \
      "$BIN" | tee "$log"
  )
  grep -q '^MX7_PERF ' "$log"
done

python - "$OUT" <<'PY'
import json
import pathlib
import statistics
import sys

out = pathlib.Path(sys.argv[1])
rows = []
for path in sorted(out.glob("run_*.txt")):
    line = next(line for line in path.read_text().splitlines() if line.startswith("MX7_PERF "))
    rows.append(json.loads(line.removeprefix("MX7_PERF ")))
if not all(row.get("resources_ready") is True for row in rows):
    raise SystemExit("MX.7 resource fallback occurred during a measured run")
expected_layers = {"dungeon": 5, "boss": 3, "boss_battle": 3}
if not all(
    row.get("music_mix") in expected_layers
    and row.get("music_streams") == 1
    and row.get("music_layers") == expected_layers[row["music_mix"]]
    and row.get("music_callbacks", 0) > 0
    for row in rows
):
    raise SystemExit("MX.7 did not measure the complete live-stem gameplay mix")
if not all(row.get("music_recoveries") == 0 for row in rows):
    raise SystemExit("MX.7 observed an unexpected music-stream recovery")
median = {key: statistics.median(row[key] for row in rows) for key in ("mean_ms", "p95_ms", "p99_ms", "max_ms", "mean_fps")}
print("MX7_PERF_MEDIAN " + json.dumps(median, sort_keys=True))
if median["p95_ms"] > 16.67:
    raise SystemExit(f"MX.7 p95 budget missed: {median['p95_ms']:.3f} ms > 16.67 ms")
PY
