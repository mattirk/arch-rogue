# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Matti Rita-Kasari
#
# Buildozer spec for the Arch Rogue Android beta APK (milestone 4.3.0).
#
# Reproducible landscape pygame-ce build.  Version and app id are sourced from
# pyproject.toml by tools/build_android.sh before invoking buildozer, so this
# file keeps stable defaults and only overrides the fields buildozer requires.

[app]
title = Arch Rogue
package.name = archrogue

# `tools/build_android.sh` rewrites these from pyproject.toml at build time.
package.domain = org.archrogue
package.version = 4.3.0

source.dir = src
source.include_exts = py,png,json

version = 4.3.0

# Landscape-only: the manifest locks orientation so the safe-area layout is the
# only one the runtime sees.
orientation = landscape

# pygame-ce is the runtime; the Python activity boots SDL2 + the game.
requirements = python3,pygame-ce==2.5.7

# Bundle every packaged asset directory.  `source.include_exts` above already
# keeps .png/.json; these ensure the deep sprite/animation trees are not pruned
# by buildozer's default include filters.
assets = src/arch_rogue/assets

# Fullscreen SDL surface; Android owns the window insets, which the game reads
# through the PyJNIus bridge in src/arch_rogue/mobile.py.
fullscreen = 1

# Android 9+ exposes DisplayCutout; older devices safely fall back to zero
# insets.  Keep the minimum API at 28 so the cutout-aware safe-area path works.
android.api = 34
android.minapi = 28
android.target_api = 34
android.arch = arm64-v8a,armeabi-v7a

# Debug build by default.  `tools/build_android.sh release` switches signing on.
android.debug = 1
android.release_artifact = _apk

# Permit writing saves/options to the app's private storage; the runtime maps
# this through pygame.system.get_pref_path.
android.permissions = 

# Keep the Python bootstrap quiet; Arch Rogue logs its own lifecycle transitions.
log_level = 2

[buildozer]
log_level = 2
warn_on_root = 1