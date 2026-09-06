#!/usr/bin/env bash
# Human review: original-speed board motion, sparse void details, and tilt extremes.
# Requires a desktop display, the pinned Odin toolchain, and ffmpeg.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
out=build/turn-page-captures/motion
stills=false
while (($#)); do
  case "$1" in
    --stills) stills=true; shift ;;
    --output-dir)
      if (($# < 2)) || [[ -z "$2" ]]; then
        echo "--output-dir requires a directory" >&2
        exit 2
      fi
      out=$2
      shift 2
      ;;
    *)
      echo "usage: $0 [--stills] [--output-dir DIR]" >&2
      exit 2
      ;;
  esac
done
mkdir -p "$out"
odin build tools/capture_turn_page_animation.odin -file -vet -o:speed \
  -out:"$out/capture"

if "$stills"; then
  env LIBGL_ALWAYS_SOFTWARE="${LIBGL_ALWAYS_SOFTWARE:-1}" \
    "$out/capture" --motion-stills --output-dir "$out" > "$out/capture.log" 2>&1
else
  pipe_dir=$(mktemp -d "$out/pipe.XXXXXX")
  encoder_pid=""
  cleanup() {
    if [[ -n "$encoder_pid" ]]; then
      kill "$encoder_pid" 2>/dev/null || true
      wait "$encoder_pid" 2>/dev/null || true
    fi
    rm -rf -- "$pipe_dir"
  }
  trap cleanup EXIT
  mkfifo "$pipe_dir/rgba"
  ffmpeg -hide_banner -loglevel error -f rawvideo -pixel_format rgba \
    -video_size 1280x720 -framerate 30 -i "$pipe_dir/rgba" \
    -an -c:v libx264 -preset fast -crf 18 -pix_fmt yuv420p \
    -movflags +faststart -y "$out/turn-page-motion-60s.mp4" \
    > "$out/encode.log" 2>&1 &
  encoder_pid=$!
  env LIBGL_ALWAYS_SOFTWARE="${LIBGL_ALWAYS_SOFTWARE:-1}" \
    "$out/capture" --motion "$pipe_dir/rgba" --output-dir "$out" > "$out/capture.log" 2>&1
  wait "$encoder_pid"
  encoder_pid=""
  test -s "$out/turn-page-motion-60s.mp4"
  echo "Captured 60-second motion cycle at original speed (30 fps)"
fi

for fixture in "720 0" "800 1"; do
  read -r height mobile <<< "$fixture"
  for age in 00 09 15 23 30 37 45 60 65; do
    test -s "$out/turn_page_motion_${age}_1280x${height}_mobile${mobile}.png"
  done
  test -s "$out/turn_page_motion_fall_1280x${height}_mobile${mobile}.png"
done
echo "Captured desktop/mobile motion, glyph peak/blank interval, and tilted falls in $out"
