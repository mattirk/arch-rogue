#!/usr/bin/env bash
# Run after ./build.sh release on a display (software GL is useful for CI).
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
mkdir -p build/turn-page-captures/config
for fixture in "1280 720 0" "1280 720 1" "1280 800 1"; do
  read -r width height mobile <<< "$fixture"
  for scene in turn_page turn_page_traverse turn_page_fall; do
    name="${scene}_${width}x${height}_mobile${mobile}"
    env ARCH_ROGUE_SEED=9707 ARCH_ROGUE_PLAY=1 ARCH_ROGUE_ARCHETYPE=rogue \
      ARCH_ROGUE_MX_STORY_CAPTURE="$scene" ARCH_ROGUE_CAPTURE_MOBILE="$mobile" \
      ARCH_ROGUE_CAPTURE_WIDTH="$width" ARCH_ROGUE_CAPTURE_HEIGHT="$height" \
      ARCH_ROGUE_SHOT="build/turn-page-captures/$name.png" ARCH_ROGUE_SHOT_FRAME=2 \
      XDG_CONFIG_HOME="$PWD/build/turn-page-captures/config" \
      LIBGL_ALWAYS_SOFTWARE="${LIBGL_ALWAYS_SOFTWARE:-1}" \
      ./build/archrogue > "build/turn-page-captures/$name.log" 2>&1
    test -s "build/turn-page-captures/$name.png"
    echo "Captured $name"
  done
done

if [[ "${1:-}" == "--animation" ]]; then
  mkdir -p build/turn-page-captures/animation/frames
  odin build tools/capture_turn_page_animation.odin -file -vet -o:speed \
    -out:build/turn-page-captures/animation/capture
  env LIBGL_ALWAYS_SOFTWARE="${LIBGL_ALWAYS_SOFTWARE:-1}" \
    build/turn-page-captures/animation/capture --variants \
    > build/turn-page-captures/animation/variants.log 2>&1
  env LIBGL_ALWAYS_SOFTWARE="${LIBGL_ALWAYS_SOFTWARE:-1}" \
    build/turn-page-captures/animation/capture --compare \
    > build/turn-page-captures/animation/comparison.log 2>&1
  env LIBGL_ALWAYS_SOFTWARE="${LIBGL_ALWAYS_SOFTWARE:-1}" \
    build/turn-page-captures/animation/capture --edge \
    > build/turn-page-captures/animation/edge.log 2>&1
  env LIBGL_ALWAYS_SOFTWARE="${LIBGL_ALWAYS_SOFTWARE:-1}" \
    build/turn-page-captures/animation/capture \
    > build/turn-page-captures/animation/capture.log 2>&1
  ffmpeg -hide_banner -loglevel error -framerate 120 \
    -i build/turn-page-captures/animation/frames/%04d.png -vf fps=60 \
    -c:v libx264 -crf 18 -pix_fmt yuv420p -movflags +faststart -y \
    build/turn-page-captures/animation/collapse.mp4
  echo "Captured 60 fps collapse animation (including interpolation and retry)"
fi
