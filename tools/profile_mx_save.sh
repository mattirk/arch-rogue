#!/usr/bin/env bash
# Release-build MX-save crowded-floor frame/snapshot benchmark. The game uses a
# process-temp save directory for this hook; no real profile, options, or run
# document is read or written.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$ROOT/build/mx-save-perf"
BIN="$ROOT/build/archrogue"
RUNS="${ARCH_ROGUE_PERF_RUNS:-3}"
FRAMES="${ARCH_ROGUE_PERF_FRAMES:-600}"
WARMUP="${ARCH_ROGUE_PERF_WARMUP:-120}"
SEED="${ARCH_ROGUE_SEED:-520199}"

if [[ -z "${DISPLAY:-}" ]]; then
  printf 'profile_mx_save.sh: a real GPU/display session is required for performance signoff\n' >&2
  exit 2
fi
if [[ "${LIBGL_ALWAYS_SOFTWARE:-0}" == 1 ]]; then
  printf 'profile_mx_save.sh: refusing software GL; unset LIBGL_ALWAYS_SOFTWARE for signoff\n' >&2
  exit 2
fi
if command -v glxinfo >/dev/null 2>&1; then
  renderer="$(glxinfo -B 2>/dev/null | awk -F: '/OpenGL renderer string/ {sub(/^ /, "", $2); print tolower($2)}')"
  case "$renderer" in
    *llvmpipe*|*softpipe*|*swiftshader*)
      printf 'profile_mx_save.sh: refusing software renderer: %s\n' "$renderer" >&2
      exit 2
      ;;
  esac
fi

mkdir -p "$OUT"
rm -f "$OUT"/*.txt
"$ROOT/build.sh" release

for run in $(seq 1 "$RUNS"); do
  log="$OUT/run_${run}.txt"
  printf 'MX-save perf run %s/%s\n' "$run" "$RUNS"
  (
    cd "$ROOT"
    env -u ARCH_ROGUE_LIGHTING -u ARCH_ROGUE_MIST -u ARCH_ROGUE_ZOOM -u ARCH_ROGUE_REVEAL \
      -u ARCH_ROGUE_DEV -u ARCH_ROGUE_OPEN -u ARCH_ROGUE_BAG -u ARCH_ROGUE_SPAWN \
      -u ARCH_ROGUE_MX6_CAPTURE -u ARCH_ROGUE_MX7_CAPTURE -u ARCH_ROGUE_MX_STORY_CAPTURE \
      -u ARCH_ROGUE_MX_SAVE_CAPTURE -u ARCH_ROGUE_MX7_PERF -u ARCH_ROGUE_SHOT \
      -u ARCH_ROGUE_SHOT_FRAME -u ARCH_ROGUE_CAPTURE_DOOR -u ARCH_ROGUE_CAPTURE_DIR \
      ARCH_ROGUE_SEED="$SEED" \
      ARCH_ROGUE_PLAY=1 \
      ARCH_ROGUE_ARCHETYPE=warden \
      ARCH_ROGUE_DEPTH=8 \
      ARCH_ROGUE_CAPTURE_THEME=6 \
      ARCH_ROGUE_CAPTURE_DARK=0 \
      ARCH_ROGUE_MX_SAVE_PERF=1 \
      ARCH_ROGUE_PERF_FRAMES="$FRAMES" \
      ARCH_ROGUE_PERF_WARMUP="$WARMUP" \
      "$BIN" 2>&1 | tee "$log"
  )
  grep -q '^MX_SAVE_PERF ' "$log"
done

python - "$OUT" <<'PY'
import json
import pathlib
import statistics
import sys

out = pathlib.Path(sys.argv[1])
rows = []
for path in sorted(out.glob("run_*.txt")):
    line = next(line for line in path.read_text().splitlines() if line.startswith("MX_SAVE_PERF "))
    rows.append(json.loads(line.removeprefix("MX_SAVE_PERF ")))
if not all(row.get("resources_ready") is True for row in rows):
    raise SystemExit("MX-save resource fallback occurred during a measured run")
if not all(row.get("save_valid") is True for row in rows):
    raise SystemExit("MX-save worker did not leave a valid recoverable run document")
if not all(row.get("snapshot_count", 0) >= 1 for row in rows):
    raise SystemExit("MX-save benchmark completed without a measured routine snapshot")
keys = (
    "mean_ms", "p95_ms", "p99_ms", "max_ms", "mean_fps",
    "snapshot_count", "snapshot_mean_ms", "snapshot_max_ms",
)
median = {key: statistics.median(row[key] for row in rows) for key in keys}
print("MX_SAVE_PERF_MEDIAN " + json.dumps(median, sort_keys=True))
if median["p95_ms"] > 16.67:
    raise SystemExit(f"MX-save p95 frame budget missed: {median['p95_ms']:.3f} ms > 16.67 ms")
if median["snapshot_max_ms"] > 8.0:
    raise SystemExit(
        f"MX-save main-thread snapshot budget missed: {median['snapshot_max_ms']:.3f} ms > 8.0 ms"
    )
PY
