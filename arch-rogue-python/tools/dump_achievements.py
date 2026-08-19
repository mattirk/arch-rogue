# SPDX-License-Identifier: Apache-2.0
"""Render the achievement catalogue for Steamworks App Admin data entry.

Steamworks has no bulk achievement import on the web form -- each achievement is
typed in by hand -- so this exists to make that transcription mechanical and to
keep what was entered checkable against the catalogue afterwards.

Run from the repository root, for example:

    .venv/bin/python tools/dump_achievements.py            # aligned columns
    .venv/bin/python tools/dump_achievements.py --format tsv > ach.tsv
    .venv/bin/python tools/dump_achievements.py --format vdf > ach.vdf

Formats:

``table``  Aligned columns for reading beside the browser. The default.
``tsv``    Tab-separated, one achievement per line, safe to paste into a sheet
           and work down row by row.
``vdf``    A ``stats.vdf`` fragment in the shape Valve's own bulk-edit accepts.
           Icons are left as placeholder filenames; upload the art separately.

The ``API Name`` column is the field that must match the game exactly -- it is
the string ``arch_rogue.achievements`` passes to ``SetAchievement``. Name and
description are display text and can be edited in App Admin later without
touching the game, but keeping them in sync with the catalogue is why they are
mirrored in the JSON at all.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from arch_rogue import achievements  # noqa: E402
from arch_rogue.steam import STEAM_APP_ID  # noqa: E402


def _table(entries) -> str:
    headers = ("#", "API Name", "Hidden", "Display Name", "Description")
    rows = [
        (
            str(index),
            entry.id,
            "yes" if entry.hidden else "no",
            entry.name,
            entry.description,
        )
        for index, entry in enumerate(entries, start=1)
    ]
    widths = [
        max(len(header), *(len(row[column]) for row in rows))
        for column, header in enumerate(headers)
    ]
    lines = [
        f"App ID {STEAM_APP_ID} — {len(entries)} achievements",
        "",
        "  ".join(header.ljust(widths[column]) for column, header in enumerate(headers)),
        "  ".join("-" * width for width in widths),
    ]
    for row in rows:
        lines.append(
            "  ".join(value.ljust(widths[column]) for column, value in enumerate(row))
        )
    lines.append("")
    lines.append(
        "Hidden achievements still need a name and description; Steam shows them "
        "only once unlocked."
    )
    return "\n".join(lines)


def _tsv(entries) -> str:
    lines = ["API Name\tDisplay Name\tDescription\tHidden"]
    for entry in entries:
        lines.append(
            "\t".join(
                (
                    entry.id,
                    entry.name,
                    entry.description,
                    "1" if entry.hidden else "0",
                )
            )
        )
    return "\n".join(lines)


def _vdf(entries) -> str:
    lines = ['"stats"', "{"]
    for index, entry in enumerate(entries, start=1):
        lines += [
            f'\t"{index}"',
            "\t{",
            '\t\t"bits"',
            "\t\t{",
            '\t\t\t"0"',
            "\t\t\t{",
            f'\t\t\t\t"name"\t\t"{entry.id}"',
            f'\t\t\t\t"display"\t"{entry.name}"',
            f'\t\t\t\t"desc"\t\t"{entry.description}"',
            f'\t\t\t\t"hidden"\t"{1 if entry.hidden else 0}"',
            f'\t\t\t\t"icon"\t\t"{entry.id.lower()}.jpg"',
            f'\t\t\t\t"icon_gray"\t"{entry.id.lower()}_locked.jpg"',
            "\t\t\t}",
            "\t\t}",
            '\t\t"type"\t\t"4"',
            "\t}",
        ]
    lines.append("}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--format",
        choices=("table", "tsv", "vdf", "json"),
        default="table",
        help="output shape (default: table)",
    )
    arguments = parser.parse_args()

    entries = achievements.load_catalogue()
    if arguments.format == "table":
        print(_table(entries))
    elif arguments.format == "tsv":
        print(_tsv(entries))
    elif arguments.format == "vdf":
        print(_vdf(entries))
    else:
        print(
            json.dumps(
                [
                    {
                        "id": entry.id,
                        "name": entry.name,
                        "description": entry.description,
                        "hidden": entry.hidden,
                    }
                    for entry in entries
                ],
                indent=2,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
