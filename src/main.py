# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Matti Rita-Kasari
#
# python-for-android's SDL2 bootstrap executes a top-level main.py from the
# private application bundle. Desktop launches continue to use the
# arch_rogue.game:main console entry point declared in pyproject.toml.

import os

# Pygame CE caches this switch while importing pygame.base. Android's SDL2
# alpha path is substantially faster than the generic pygame blitter on ARM,
# so it must be selected before arch_rogue.game imports pygame.
os.environ.setdefault("PYGAME_BLEND_ALPHA_SDL2", "1")

from arch_rogue.game import main


if __name__ == "__main__":
    main()
