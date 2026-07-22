# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Matti Rita-Kasari
#
# Buildozer spec for the Arch Rogue Android beta APK (milestone 4.3.x).
#
# Reproducible landscape pygame-ce build.  Version and app id are sourced from
# pyproject.toml by tools/build_android.sh before invoking buildozer, so this
# file keeps stable defaults and only overrides the fields buildozer requires.

[app]
title = Arch Rogue
package.name = archrogue

# `tools/build_android.sh` rewrites these from pyproject.toml at build time.
package.domain = org.archrogue
package.version = 4.5.5

source.dir = src
source.include_exts = py,png,json,txt
# Never package host-generated metadata/bytecode from an editable install.
source.exclude_dirs = __pycache__,arch_rogue.egg-info

version = 4.5.5

# Landscape-only: the manifest locks orientation so the safe-area layout is the
# only one the runtime sees.
orientation = landscape

# App/launcher icon. Uses the largest bundled crest; p4a copies this into the
# Android resources and references it from the manifest's android:icon, so the
# game icon shows as the installed app icon on the launcher/home screen.
icon.filename = src/arch_rogue/assets/icons/icon_512.png

# Loading screen shown while the Python interpreter bootstraps. Uses the
# authored ARCH <diamond> ROGUE title lockup so the APK opens with the branded
# logo instead of python-for-android's default SDL splash. The dark presplash
# color fills the screen behind the centered transparent logo.
presplash.filename = src/arch_rogue/assets/sprites/menus/title_logo.png
presplash.color = #0a0a0f

# The local recipe named `pygame` cross-compiles pygame-ce 2.5.7. Do not put
# `pygame-ce` here: p4a has no recipe by that name and would bundle a host wheel.
# PyJNIus is required by the safe-area DisplayCutout bridge.
requirements = python3,pygame==2.5.7,pyjnius
p4a.bootstrap = sdl2
p4a.local_recipes = android/recipes
# python-for-android release 2026.05.09. Pinning the commit keeps recipe, Python,
# Gradle, and NDK expectations stable across local and CI builds.
p4a.commit = 58d21141f17c889bf8585f5665921d72028f8831

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
android.ndk = 28c
android.archs = arm64-v8a,armeabi-v7a
android.display_cutout = shortEdges

# Debug build by default.  `tools/build_android.sh release` switches signing on.
android.debug = 1
android.release_artifact = apk

# No Android permissions are requested. Saves/options use app-private storage,
# which requires no storage permission.


# Keep the Python bootstrap quiet; Arch Rogue logs its own lifecycle transitions.
log_level = 2

[buildozer]
log_level = 2
warn_on_root = 1