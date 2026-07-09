"""Pyodide/pygbag web entry point for Arch Rogue.

This module is what `pygbag` packages into the browser build. It drives the
existing `arch_rogue.game.Game` frame loop exactly like `Game.run()`, but
yields to the asyncio event loop after every frame (`await asyncio.sleep(0)`).
That yield is required so the Pyodide/browser runtime can pump its own input
and rendering between our frames; without it the page would hang.

`Game` itself is intentionally left unchanged (see AGENTS.md: keep
`arch_rogue.game.Game` and `arch_rogue.game:main` stable). The loop body here
mirrors `Game.run()` line-for-line so the desktop and web builds behave the
same.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path


def resolve_src_paths(
    file_path: Path | None,
    cwd: Path,
    extra: list[Path] | None = None,
) -> list[Path]:
    """Return existing src/ dirs to put on sys.path, in priority order.

    Pure helper so the browser path bootstrap is unit-testable without a real
    Pyodide runtime: it just resolves candidate ``src`` directories and returns
    the ones that exist.
    """
    candidates: list[Path] = []
    if file_path is not None:
        candidates.append(Path(file_path).resolve().parent / "src")
    candidates.append(Path(cwd) / "src")
    if extra:
        candidates.extend(extra)
    seen: set[str] = set()
    out: list[Path] = []
    for cand in candidates:
        resolved = Path(cand).resolve()
        key = str(resolved)
        if resolved.is_dir() and key not in seen:
            seen.add(key)
            out.append(resolved)
    return out


def _bootstrap_arch_rogue_path() -> None:
    # pygbag extracts the app source under <appdir>/assets and runs this file
    # from there. The project uses a src-layout (arch_rogue lives under
    # assets/src/), which is NOT on sys.path by default, so `import arch_rogue`
    # would fail and Pyodide's PEP-723 auto-installer would try to fetch it from
    # PyPI (https://pypi.org/simple/arch_rogue/) — which 404s and leaves a grey
    # screen. Put the src dir on the path before importing arch_rogue.
    file_path = Path(globals()["__file__"]) if "__file__" in globals() else None
    extra = [Path("/data/data/arch-rogue/assets/src")]
    for cand in resolve_src_paths(file_path, Path(os.getcwd()), extra):
        if str(cand) not in sys.path:
            sys.path.insert(0, str(cand))


_bootstrap_arch_rogue_path()

import pygame  # noqa: E402

from arch_rogue.constants import FPS, SCREEN_HEIGHT, SCREEN_WIDTH  # noqa: E402
from arch_rogue.game import Game  # noqa: E402


def _writable_home() -> Path:
    """Return a writable base directory for saves/options.

    The real user home is not always writable (or even present) in the Pyodide
    in-browser runtime, so fall back to `/tmp` (Pyodide provides it as an
    in-memory FS) and finally the current directory.
    """
    for candidate in (Path.home(), Path("/tmp")):
        try:
            candidate.mkdir(parents=True, exist_ok=True)
        except OSError:
            continue
        if os.access(candidate, os.W_OK):
            return candidate
    return Path(".")


# Cache the Pyodide JS bridge so the per-frame sizing probe stays cheap. On the
# desktop there is no `js` module, so this resolves to None and the helpers below
# become no-ops (the build then uses the constant fallback resolution).
_JS = None
_JS_CHECKED = False


def _get_js():
    global _JS, _JS_CHECKED
    if not _JS_CHECKED:
        _JS_CHECKED = True
        try:
            import js  # Pyodide JS bridge; unavailable on the desktop

            _JS = js
        except ImportError:
            _JS = None
    return _JS


def browser_window_size() -> tuple[int, int] | None:
    """Return the browser viewport size in CSS pixels, or None off-browser.

    pygbag fits the canvas to the window while preserving the *backing*
    surface's aspect ratio, so to fill the whole viewport with no letterboxing
    the backing surface (set by ``pygame.display.set_mode``) must match the
    window size. Returns None when not running under Pyodide so the desktop and
    unit tests fall back to the constant resolution.
    """
    js = _get_js()
    if js is None:
        return None
    try:
        w = int(js.window.innerWidth or 0)
        h = int(js.window.innerHeight or 0)
    except Exception:
        return None
    if w >= 320 and h >= 240:
        return (w, h)
    return None


def _notify_pygbag_refit() -> None:
    # pygbag only re-fits the canvas CSS on a *browser* resize, so after we
    # change the backing surface we re-trigger its fitter (global window_resize).
    js = _get_js()
    if js is None:
        return
    try:
        js.window_resize()
    except Exception:
        pass


# ---- Browser performance: capped internal render resolution ------------------
# Rendering at the full browser viewport (e.g. 1920x1080 / 4K) is the dominant
# per-frame cost under Pyodide (slower-than-native Python + WASM SDL). pygbag
# upscales the canvas via CSS for free, so we render at a capped internal
# resolution that preserves the window's aspect ratio (so the canvas still
# fills the window with no letterboxing) and let the browser scale it up. The
# cap can be tuned / disabled with the ?maxw= and ?maxpx= URL query params.
DEFAULT_MAX_RENDER_LONG_SIDE = 1280
DEFAULT_MAX_RENDER_PIXELS = 1_300_000
MIN_RENDER_W = 320
MIN_RENDER_H = 240

_WEB_CONFIG = None


def web_config() -> dict:
    """Return cached browser render-cap config, honoring ?maxw= / ?maxpx= URLs.

    ``maxw`` caps the longer render side; ``maxpx`` caps total render pixels.
    A very large ``maxw`` (e.g. ``?maxw=99999``) effectively disables the cap for
    users who want the full window resolution and have the CPU for it.
    """
    global _WEB_CONFIG
    if _WEB_CONFIG is None:
        cfg = {
            "maxw": DEFAULT_MAX_RENDER_LONG_SIDE,
            "maxpx": DEFAULT_MAX_RENDER_PIXELS,
        }
        js = _get_js()
        if js is not None:
            try:
                from urllib.parse import parse_qs

                search = str(getattr(js.location, "search", "") or "")
                qs = parse_qs(search.lstrip("?"))
                if "maxw" in qs:
                    cfg["maxw"] = max(0, int(qs["maxw"][0]))
                if "maxpx" in qs:
                    cfg["maxpx"] = max(0, int(qs["maxpx"][0]))
            except Exception:
                pass
        _WEB_CONFIG = cfg
    return _WEB_CONFIG


def cap_render_size(
    w: int, h: int, max_long: int | None = None, max_px: int | None = None
):
    """Cap a render size, preserving aspect ratio, to a max long side and max
    pixel area. Pure helper so the cap is unit-testable without a browser."""
    if max_long is None:
        max_long = web_config()["maxw"]
    if max_px is None:
        max_px = web_config()["maxpx"]
    if max_long and max(w, h) > max_long:
        s = max_long / max(w, h)
        w = round(w * s)
        h = round(h * s)
    if max_px and w * h > max_px:
        s = (max_px / (w * h)) ** 0.5
        w = int(w * s)
        h = int(h * s)
    return max(MIN_RENDER_W, int(w)), max(MIN_RENDER_H, int(h))


def browser_render_size():
    """Return the capped browser render size, or None off-browser."""
    win = browser_window_size()
    if win is None:
        return None
    return cap_render_size(win[0], win[1])


def maybe_resize_to_browser(
    game: Game,
    size_provider=None,
    notify: bool = True,
) -> bool:
    """Resize the display surface to the browser viewport when it changes.

    Returns True when a resize happened. ``size_provider`` (default
    :func:`browser_window_size`) is a parameter so the logic is unit-testable
    without a real Pyodide runtime.
    """
    provider = size_provider if size_provider is not None else browser_render_size
    size = provider()
    if size is None or size[0] < 320 or size[1] < 240:
        return False
    cur = game.screen.get_size()
    if (cur[0], cur[1]) == size:
        return False
    game.windowed_size = size
    game.screen = pygame.display.set_mode(size, pygame.RESIZABLE)
    if notify:
        _notify_pygbag_refit()
    return True


def make_game(
    headless: bool = False,
    screen_size: tuple[int, int] | None = None,
) -> Game:
    """Construct a `Game` configured for browser hosting.

    The display surface is sized to the browser viewport when available so the
    game fills the whole available window (no letterboxing). Saves/options are
    redirected to a writable in-browser-FS path, and fullscreen is forced off
    because fullscreen/SCALED-fullscreen is not meaningful inside a browser
    canvas and would prevent the loop from painting the surface the canvas
    expects.
    """
    if screen_size is None:
        screen_size = browser_render_size() or (SCREEN_WIDTH, SCREEN_HEIGHT)
    home = _writable_home()
    game = Game(
        screen_size=screen_size,
        headless=headless,
        save_path=home / ".arch_rogue_run.json",
    )
    game.options_path = home / ".arch_rogue_options.json"
    if game.fullscreen:
        game.fullscreen = False
        game.windowed_size = screen_size
        game.screen = game.apply_display_mode()
    # Milestone 3.16 - native-only lighting; web runs the 3.8.0 per-tile
    # alpha fallback (the web-safe default) regardless of saved prefs.
    game._lighting_enabled = False
    game._lighting_normal_maps = False
    return game


_FRAME = 0


async def run_frame(game: Game) -> None:
    """Advance one game frame and yield to the browser event loop."""
    global _FRAME
    _FRAME += 1
    # Keep the backing surface matched to the (capped) browser render size so the
    # canvas fills the window as the user resizes it. The probe crosses the
    # Pyodide<->JS bridge, so only run it every few frames (resize detection at
    # ~10 Hz is plenty); it is a no-op off-browser.
    if _FRAME == 1 or _FRAME % 10 == 0:
        maybe_resize_to_browser(game)
    dt = min(game.clock.tick(FPS) / 1000.0, 0.05)
    game.handle_events()
    if game.state == "playing":
        game.update(dt)
    game.draw()
    # Required: hand control back to Pyodide's asyncio scheduler so the
    # browser can process input and push the canvas forward.
    await asyncio.sleep(0)


async def main() -> None:
    game = make_game()
    try:
        while game.running:
            await run_frame(game)
    finally:
        pygame.quit()


if __name__ == "__main__":
    asyncio.run(main())
