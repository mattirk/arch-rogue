# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Matti Rita-Kasari
#
# python-for-android's SDL2 bootstrap executes a top-level main.py from the
# private application bundle. Desktop launches continue to use the
# arch_rogue.game:main console entry point declared in pyproject.toml.

from arch_rogue.game import main


if __name__ == "__main__":
    main()
