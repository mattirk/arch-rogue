#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Live Android performance profiler for Arch Rogue over adb logcat.

The game already emits ``ARCH_ROGUE_PERF`` telemetry lines from
``arch_rogue.mobile.MobilePerformanceMonitor`` (enabled by default on
Android, ~4 s cadence). This script streams ``adb logcat``, parses those
lines, and renders a rolling single-screen view with FPS history, per-phase
cost bars, and GPU/upload/cache metrics so you can profile a real run on a
real device without leaving the terminal.

Run from the repository root, for example:

    .venv/bin/python tools/profile_adb_live.py --serial 61161JEBF16937

If exactly one device is attached, ``--serial`` can be omitted. Use
``--window N`` to size the rolling sample window (default 20, ~80 s at the
4 s cadence). ``--raw`` prints each parsed line as it arrives instead of the
dashboard. Ctrl-C to stop.

Requires only the Python standard library and a working ``adb`` on PATH.
"""

from __future__ import annotations

import argparse
import re
import shutil
import signal
import statistics
import subprocess
import sys
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Iterable


PERF_PREFIX = "ARCH_ROGUE_PERF"

# Phases in the order the game emits them (see arch_rogue.mobile).
PHASES = (
    "tick",
    "events",
    "update",
    "clear",
    "menu",
    "world",
    "hud",
    "overlays",
    "flip",
    "audio",
)
DETAIL_PHASES = (
    "floor",
    "objects",
    "aim",
    "guidance",
    "light_build",
    "ambient",
    "base_upload",
    "light_upload",
    "ui_upload",
    "gpu_present",
)

# key=value tokens we deliberately extract as scalars (everything else is
# captured generically by the kv parser).
KNOWN_SCALARS = (
    "state",
    "fps",
    "frame_ms",
    "logical",
    "window",
    "viewport",
    "quality",
    "renderer",
    "accelerated",
    "alpha_sdl2",
    "neon",
    "gpu_light",
    "gpu_ui",
    "gpu_upload",
    "gpu_stream",
    "gpu_error",
    "video",
    "lighting",
    "lighting_mode",
    "normals",
    "entities",
    "visible",
    "guidance_px",
    "cache",
    "aim_cache",
    "floor_cache",
)

# Strip ANSI control sequences for --no-color mode (also defensively).
_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #

# A logcat line looks like:
#   07-21 19:03:35.672 I/python  (10816): ARCH_ROGUE_PERF state=title fps=61.19 ...
# We only care about the payload after the prefix.
_LOGCAT_PREFIX_RE = re.compile(
    r"^\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+\s+\w+/[^\s(]+(?:\s*\(\s*\d+\))?:\s*(.*)$"
)

# Split a perf payload into its kv tokens. Tokens are space-separated
# ``key=value`` pairs where value never contains spaces.
_KV_TOKEN_RE = re.compile(r"(\S+?)=([^\s]+)")


@dataclass(slots=True)
class Sample:
    """One parsed ARCH_ROGUE_PERF emission."""

    ts: float
    state: str = "?"
    fps: float = 0.0
    frame_ms: float = 0.0
    phase_ms: dict[str, float] = field(default_factory=dict)
    detail_ms: dict[str, float] = field(default_factory=dict)
    other_ms: float = 0.0
    scalars: dict[str, str] = field(default_factory=dict)
    raw: str = ""

    def get(self, key: str) -> str:
        return self.scalars.get(key, "")


def parse_perf_payload(payload: str) -> dict[str, str] | None:
    """Parse the flat key=value stream after the ARCH_ROGUE_PERF prefix.

    Returns ``None`` if the line is not a perf emission.
    """
    if not payload.startswith(PERF_PREFIX):
        return None
    body = payload[len(PERF_PREFIX) :].strip()
    return dict(_KV_TOKEN_RE.findall(body))


def _ms(value: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _parse_comma_kv(value: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for chunk in value.split(","):
        if ":" in chunk:
            name, _, num = chunk.partition(":")
            out[name.strip()] = _ms(num)
    return out


def build_sample(kv: dict[str, str], raw: str) -> Sample:
    phase_ms = _parse_comma_kv(kv.get("phase_ms", ""))
    # phase_ms includes a trailing ",other:X" token; pull it out separately so
    # the per-phase bars don't draw an "other" bucket that double counts.
    other_ms = phase_ms.pop("other", 0.0)
    detail_ms = _parse_comma_kv(kv.get("render_ms", ""))
    scalars = {k: kv.get(k, "") for k in KNOWN_SCALARS if k in kv}
    # Keep any extra tokens the game may add later.
    for k, v in kv.items():
        if k not in KNOWN_SCALARS and k not in {"phase_ms", "render_ms"}:
            scalars.setdefault(k, v)
    return Sample(
        ts=time.time(),
        state=kv.get("state", "?"),
        fps=_ms(kv.get("fps", "0")),
        frame_ms=_ms(kv.get("frame_ms", "0")),
        phase_ms=phase_ms,
        detail_ms=detail_ms,
        other_ms=other_ms,
        scalars=scalars,
        raw=raw,
    )


def parse_logcat_line(line: str) -> Sample | None:
    stripped = _ANSI_RE.sub("", line).rstrip("\n")
    m = _LOGCAT_PREFIX_RE.match(stripped)
    payload = m.group(1) if m else stripped
    if PERF_PREFIX not in payload:
        return None
    kv = parse_perf_payload(payload)
    if kv is None:
        return None
    return build_sample(kv, payload)


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #

RESET = "\x1b[0m"
BOLD = "\x1b[1m"
DIM = "\x1b[2m"
RED = "\x1b[31m"
GREEN = "\x1b[32m"
YELLOW = "\x1b[33m"
BLUE = "\x1b[34m"
MAGENTA = "\x1b[35m"
CYAN = "\x1b[36m"
GREY = "\x1b[90m"

# Clear screen + home cursor. \x1b[2J\x1b[H flickers less than clearing each
# draw on most terminals; we additionally use cursor home only between frames
# to avoid scrolling.
CLEAR = "\x1b[2J\x1b[H"


def _color_for_fps(fps: float) -> str:
    if fps >= 58.0:
        return GREEN
    if fps >= 45.0:
        return YELLOW
    return RED


def _bar(value: float, total: float, width: int = 26) -> str:
    if total <= 0:
        return " " * width
    ratio = max(0.0, min(1.0, value / total))
    filled = int(round(ratio * width))
    return "#" * filled + "-" * (width - filled)


def _fmt_ms(v: float) -> str:
    return f"{v:5.1f}"


def render_dashboard(
    samples: deque[Sample],
    *,
    use_color: bool,
    game_pid: int | None,
    device_serial: str,
) -> str:
    if not samples:
        return f"{CLEAR}ARCH_ROGUE perf: waiting for first ARCH_ROGUE_PERF emission..."

    cur = samples[-1]
    c = (lambda s: s) if not use_color else (lambda s: s)

    # Rolling FPS stats over the window.
    fps_vals = [s.fps for s in samples]
    fps_min = min(fps_vals)
    fps_max = max(fps_vals)
    fps_avg = statistics.fmean(fps_vals)
    fps_stdev = statistics.pstdev(fps_vals) if len(fps_vals) > 1 else 0.0

    # Frame budget (16.67 ms @ 60 fps). Anything above is a dropped frame.
    budget_ms = 1000.0 / 60.0
    over_budget = sum(1 for v in fps_vals if v > 0.0 and 1000.0 / max(v, 1e-9) > budget_ms + 0.5)

    # phase_ms sums vary per sample; average them for a stable bar chart.
    phase_avg = {p: statistics.fmean(s.phase_ms.get(p, 0.0) for s in samples) for p in PHASES}
    detail_avg = {
        p: statistics.fmean(s.detail_ms.get(p, 0.0) for s in samples) for p in DETAIL_PHASES
    }
    other_avg = statistics.fmean(s.other_ms for s in samples)
    # Bar scale = average frame time, so the bars sum to ~frame_ms visually.
    scale = max(statistics.fmean(s.frame_ms for s in samples), budget_ms)

    # Sparkline of recent fps (normalized to 0..1 across 30..70 fps range).
    spark = _sparkline(fps_vals, lo=30.0, hi=70.0)

    lines: list[str] = []
    lines.append(
        f"{c(BOLD)}ARCH ROGUE — live Android perf{c(RESET)} "
        f"{c(DIM)}dev={device_serial} pid={game_pid or '-'} samples={len(samples)} "
        f"updated {time.strftime('%H:%M:%S')}{c(RESET)}"
    )
    lines.append("")

    fps_color = _color_for_fps(cur.fps)
    lines.append(
        f"  state     : {c(BOLD)}{cur.state:<10}{c(RESET)}    "
        f"fps now {c(fps_color)}{cur.fps:6.2f}{c(RESET)}    "
        f"frame {cur.frame_ms:5.1f} ms  ({1000.0 / max(cur.fps, 1e-9):5.1f} ms budget)"
    )
    lines.append(
        f"  fps window: avg {c(BOLD)}{fps_avg:6.2f}{c(RESET)}   "
        f"min {c(RED if fps_min < 45 else YELLOW if fps_min < 58 else GREEN)}{fps_min:5.2f}{c(RESET)}   "
        f"max {fps_max:5.2f}   stdev {fps_stdev:4.2f}   "
        f"frames>budget {c(YELLOW if over_budget else GREEN)}{over_budget}/{len(samples)}{c(RESET)}"
    )
    lines.append(f"  trend     : {spark}")
    lines.append("")

    lines.append(f"  {c(BOLD)}per-phase cost (avg ms over window){c(RESET)}")
    for p in PHASES:
        v = phase_avg.get(p, 0.0)
        lines.append(
            f"    {p:<9} {_fmt_ms(v)}ms {c(CYAN)}{_bar(v, scale)}{c(RESET)}"
        )
    lines.append(
        f"    {'other':<9} {_fmt_ms(other_avg)}ms {c(GREY)}{_bar(other_avg, scale)}{c(RESET)}"
    )
    lines.append("")

    lines.append(f"  {c(BOLD)}render detail (avg ms){c(RESET)}")
    for p in DETAIL_PHASES:
        v = detail_avg.get(p, 0.0)
        if v < 0.05 and all(s.detail_ms.get(p, 0.0) < 0.05 for s in samples):
            continue
        lines.append(
            f"    {p:<13} {_fmt_ms(v)}ms {c(MAGENTA)}{_bar(v, scale)}{c(RESET)}"
        )
    lines.append("")

    lines.append(f"  {c(BOLD)}runtime{c(RESET)}")
    lines.append(
        f"    logical={cur.get('logical')} window={cur.get('window')} "
        f"viewport={cur.get('viewport')}"
    )
    lines.append(
        f"    renderer={cur.get('renderer')} accelerated={cur.get('accelerated')} "
        f"alpha_sdl2={cur.get('alpha_sdl2')} neon={cur.get('neon')} "
        f"video={cur.get('video')}"
    )
    lines.append(
        f"    quality={cur.get('quality')} lighting={cur.get('lighting')} "
        f"lighting_mode={cur.get('lighting_mode')} normals={cur.get('normals')}"
    )
    lines.append(
        f"    gpu_light={cur.get('gpu_light')} gpu_ui={cur.get('gpu_ui')} "
        f"gpu_upload={cur.get('gpu_upload')} stream={cur.get('gpu_stream')} "
        f"error={cur.get('gpu_error')}"
    )
    lines.append(
        f"    entities={cur.get('entities')} visible={cur.get('visible')} "
        f"guidance_px={cur.get('guidance_px')}"
    )
    lines.append(
        f"    cache={cur.get('cache')} aim={cur.get('aim_cache')} "
        f"floor={cur.get('floor_cache')}"
    )
    lines.append("")
    lines.append(f"{c(DIM)}Ctrl-C to stop. New state changes are highlighted above.{c(RESET)}")
    body = "\n".join(lines)
    # Only clear-and-home when we are actually painting a TTY dashboard; in
    # --no-color / piped mode we append so the history is preserved.
    return (CLEAR + body) if use_color else body


def _sparkline(values: Iterable[float], lo: float, hi: float, width: int = 40) -> str:
    ramp = "▁▂▃▄▅▆▇█"
    vals = list(values)
    if not vals:
        return ""
    out = []
    span = max(hi - lo, 1e-9)
    for v in vals[-width:]:
        ratio = (v - lo) / span
        idx = int(round(max(0.0, min(1.0, ratio)) * (len(ramp) - 1)))
        out.append(ramp[idx])
    # Left-pad if we don't yet have a full window.
    if len(out) < width:
        out = [" "] * (width - len(out)) + out
    return "".join(out)


# --------------------------------------------------------------------------- #
# adb / logcat streaming
# --------------------------------------------------------------------------- #

def resolve_serial(arg_serial: str | None) -> tuple[str, list[str]]:
    """Resolve the adb -s argument and the adb base argv prefix."""
    adb = shutil.which("adb")
    if adb is None:
        sys.exit("adb not found on PATH; install platform-tools and retry.")
    base = [adb]
    if arg_serial:
        base += ["-s", arg_serial]
        return arg_serial, base
    # Auto-pick if exactly one device is attached.
    devices = subprocess.run(
        [adb, "devices"], capture_output=True, text=True, check=True
    ).stdout
    serials = [
        ln.split()[0]
        for ln in devices.splitlines()[1:]
        if ln.strip() and "\tdevice" in ln
    ]
    if len(serials) == 1:
        base += ["-s", serials[0]]
        return serials[0], base
    if not serials:
        sys.exit("no adb devices attached.")
    sys.exit(
        "multiple devices attached; pass --serial:\n  "
        + "\n  ".join(serials)
    )


def stream_logcat(base_argv: list[str]) -> Iterable[str]:
    """Yield raw logcat lines forever (until the adb session dies)."""
    # -v time gives a stable timestamped prefix; -T 1 starts at "now" so we
    # don't replay the whole ring buffer on connect. We filter to the python
    # tag (where p4a routes stdout) plus the SystemErr/PythonActivity tags so
    # we never miss a perf line if the routing tag changes.
    cmd = base_argv + [
        "logcat",
        "-v",
        "time",
        "-T",
        "1",
        "python:I",
        "PythonActivity:V",
        "*:S",
    ]
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1
    )
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            yield line
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            proc.kill()


def current_pid(base_argv: list[str]) -> int | None:
    """Best-effort pid of the running Arch Rogue process."""
    try:
        out = subprocess.run(
            base_argv + ["shell", "pidof", "org.archrogue.archrogue"],
            capture_output=True, text=True, check=False, timeout=4.0,
        ).stdout.strip()
    except subprocess.SubprocessError:
        return None
    if not out:
        return None
    # pidof can return multiple pids; take the first.
    return int(out.split()[0]) if out.split() else None


# --------------------------------------------------------------------------- #
# Main loop
# --------------------------------------------------------------------------- #

def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--serial", default=None,
        help="adb device serial (omitted => auto-pick the only attached device).",
    )
    parser.add_argument(
        "--window", type=int, default=20,
        help="rolling sample window size (default 20, ~80 s at the 4 s cadence).",
    )
    parser.add_argument(
        "--raw", action="store_true",
        help="print each parsed ARCH_ROGUE_PERF line as it arrives, no dashboard.",
    )
    parser.add_argument(
        "--no-color", action="store_true",
        help="disable ANSI colors / clear-screen (for piping to a file).",
    )
    args = parser.parse_args()

    serial, base_argv = resolve_serial(args.serial)
    use_color = (not args.no_color) and sys.stdout.isatty()

    window: deque[Sample] = deque(maxlen=max(1, args.window))
    pid: int | None = None
    last_pid_check = 0.0

    def _on_sigint(_signum, _frame):
        if use_color:
            sys.stdout.write(RESET)
        sys.stdout.write("\n")
        sys.exit(0)

    signal.signal(signal.SIGINT, _on_sigint)

    print(
        f"Streaming adb logcat from {serial}; waiting for ARCH_ROGUE_PERF lines..."
        + ("\n" if not use_color else CLEAR),
        file=sys.stderr,
        flush=True,
    )

    for line in stream_logcat(base_argv):
        sample = parse_logcat_line(line)
        if sample is None:
            continue

        if args.raw:
            sys.stdout.write(sample.raw + "\n")
            sys.stdout.flush()
            continue

        window.append(sample)

        # Refresh the game pid at most every ~5 s to keep the dashboard
        # accurate without spamming adb shell on every emission.
        now = time.time()
        if pid is None or now - last_pid_check > 5.0:
            pid = current_pid(base_argv)
            last_pid_check = now

        sys.stdout.write(render_dashboard(
            window, use_color=use_color, game_pid=pid, device_serial=serial,
        ))
        sys.stdout.flush()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())