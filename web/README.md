# Arch Rogue — Web Build (pygame-web / pygbag)

Arch Rogue is a desktop pygame-ce game. This directory hosts it on the web using
**pygbag**, the pygame community's official browser packager, which compiles the
project via Pyodide (CPython compiled to WebAssembly) and emits a static site.

There are three pieces:

| File | Role |
| --- | --- |
| `main.py` | Async Pyodide entry point. Drives the existing `Game` frame loop and yields to the browser event loop (`await asyncio.sleep(0)`) every frame. `Game` itself is unchanged. |
| `server.py` | Static HTTP server that hosts the pygbag-built site. Sets the `COOP`/`COEP` cross-origin-isolation headers and `application/wasm` MIME type that Pyodide's threaded runtime needs. |
| `build.py` | Orchestrator: runs `pygbag --build`, rewrites the generated `index.html` to load the runtime from the local vendored `/cdn/...` path, merges the vendored runtime into `web/dist/cdn/`, and (optionally) starts the server. |
| `vendor_runtime.py` | Downloads the entire pygbag/pygame-web runtime (pythons.js, the CPython/Pyodide interpreter `main.js`+`main.data`+`main.wasm`, the vt/vtx/xterm terminals, and static assets) from the CDN once into `web/vendor/cdn/...` so the build is fully self-contained and same-origin. |

## One-time setup

```bash
# from the repository root, with the project venv active
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python -m pip install pygbag     # web packaging tool (build-time only)
```

## Build and serve

```bash
python web/build.py                 # vendors runtime (first run ~21 MB), builds into web/dist, then serves on http://127.0.0.1:8000
```

The build is **fully self-contained**: `vendor_runtime.py` downloads the whole
pygbag/pygame-web runtime (pythons.js, the CPython/Pyodide interpreter, the
vt/vtx/xterm terminals, and static assets) into `web/vendor/cdn/...` on the first
run. `build.py` then rewrites the generated `index.html` so every runtime
reference points at the local same-origin `/cdn/0.9.3/...` path (no requests to
the remote CDN), and merges the vendored tree into `web/dist/cdn/`. This is what
eliminates the cross-origin-request errors.

Build only (no serve):

```bash
python web/build.py --no-serve
```

Re-download the runtime (e.g. after a pygbag upgrade):

```bash
python web/vendor_runtime.py --force
```

Serve an existing build without rebuilding:

```bash
python web/server.py --directory web/dist --port 8000
```

Open the printed URL in a modern browser. The first load downloads Pyodide + the
build assets (tens of MB), then the game runs at 60 FPS like the desktop build.

## Troubleshooting: "cross-origin request blocked" / 404s

The original 404s (`arch_rogue/`, `browserfs.min.js`) had two causes, both now
fixed by the vendored build:

1. **Remote-CDN coupling.** The pygbag `index.html` booted the app from
   `https://pygame-web.github.io/cdn/0.9.3/`, loading `pythons.js`, the CPython
   runtime, terminals, and assets cross-origin. Under `Cross-Origin-Embedder-
   Policy: require-corp` those cross-origin fetches were blocked. `build.py`
   now rewrites `index.html` to load everything from the local same-origin
   `/cdn/0.9.3/...` and merges the vendored runtime into `web/dist/cdn/`, so
   there are **zero cross-origin requests**. The server still defaults `COEP` to
   `credentialless` (use `--coep require-corp` for strict same-origin-only).
2. **Dead template references.** pygbag's template emits `<script>` tags for
   `browserfs.min.js` and `pygbag0.9.3.js` that 404 even on the official CDN.
   BrowserFS is not used by the tarball-based app flow, so `vendor_runtime.py`
   writes empty local stubs for both so the tags resolve (200) instead of
   producing console 404s.

If you vendor every asset same-origin and want the strict policy, pass it
explicitly:

```bash
python web/server.py --coep require-corp
```

## How the loop works

`Game.run()` is a blocking `while self.running:` loop. We cannot block inside a
browser, so `web/main.py` reproduces that loop exactly but `await
asyncio.sleep(0)` after each frame so Pyodide's asyncio scheduler can pump input
and push the canvas:

```python
async def run_frame(game):
    dt = min(game.clock.tick(FPS) / 1000.0, 0.05)
    game.handle_events()
    if game.state == "playing":
        game.update(dt)
    game.draw()
    await asyncio.sleep(0)
```

`arch_rogue.game.Game`, `arch_rogue.game:main`, save schema, and keyboard/mouse
bindings are all left untouched; the web build is the same game, driven by the
same public methods.

### Why `main.py` touches `sys.path` (the grey-screen fix)

pygbag's tarball flow extracts the app to `<appdir>/assets` and runs
`assets/main.py` from there, but it does **not** put the project's `assets/src`
on `sys.path`. Arch Rogue uses a `src/`-layout, so a plain `from arch_rogue.game
import Game` would fail to find the package locally — and Pyodide's PEP-723
auto-installer would then try to fetch `arch_rogue` from PyPI
(`https://pypi.org/simple/arch_rogue/`), which 404s and leaves a grey canvas.
`web/main.py` therefore runs a small `resolve_src_paths`/`_bootstrap_arch_rogue_path`
hook *before* importing `arch_rogue`, adding `assets/src` (resolved from
`__file__`, then the cwd, then the hardcoded pygbag extraction path) to
`sys.path`. This points the import at the vendored app source on the local
filesystem, not at PyPI.

### Adaptive resolution (fills the browser window)

pygbag fits the canvas CSS to the browser window while preserving the **backing**
surface's aspect ratio (`canvas.width/canvas.height`, set by
`pygame.display.set_mode`). With a fixed 2560×1440 (16:9) backing, a non-16:9
window letterboxes. So `web/main.py` instead sizes the backing surface to the
browser viewport and re-adapts on resize:

- `browser_window_size()` reads `js.window.innerWidth/innerHeight` (Pyodide `js`
  bridge) in CSS pixels.
- `make_game()` defaults the initial display surface to that size.
- `run_frame()` calls `maybe_resize_to_browser(game)` each frame: when the
  viewport differs from the current surface (≥320×240) it calls
  `pygame.display.set_mode(size, pygame.RESIZABLE)` and re-triggers pygbag's
  CSS fitter (`js.window_resize()`) so the canvas re-fills the window.

Off-browser (no `js` module) both helpers are no-ops, so the desktop driver and
unit tests keep using the constant fallback resolution and are unaffected.

There is one caveat: pygbag warns about non-1 `devicePixelRatio`, so on HiDPI
displays the backing is sized to CSS pixels (not device pixels); the canvas is
then displayed 1:1 with CSS pixels, which is sharp and avoids the unsupported-DPR
path.

## Notes and limitations

- **The pygbag runtime is vendored locally** under `web/vendor/cdn/` (~21 MB,
  downloaded once from the official pygame-web CDN). It is *not* committed by
  default — run `python web/build.py` (or `python web/vendor_runtime.py`) to
  fetch it. To commit a fully offline-capable repo, `git add web/vendor`.
- **The app tarball excludes dev-only dirs** via the repo-root `pygbag.ini`
  (`/.venv`, `/web`, `/tests`, `__pycache__`); without it pygbag packaged the
  whole virtualenv and the vendored runtime into a 108 MB tarball. It is now
  ~220 KB of just the game source.
- **Fullscreen is disabled** in the web build (`make_game` forces it off); it is
  not meaningful inside a browser canvas.
- **Saves/options** are written to a writable path under the Pyodide in-memory
  filesystem (typically `/tmp`). They persist for the page session but do not
  survive a browser reload unless you mount an IDBFS-backed persistent store
  (future work; the `Game` save code already tolerates missing/unwritable paths).
- **Audio** is best-effort: Pyodide's audio support is limited, and `AudioSystem`
  already degrades gracefully when the mixer cannot initialize.
- pygbag is a **build-time** dependency only; it is not added to the runtime
  `pyproject.toml` dependencies (install via the optional `[web]` extra).

## Updating the build

After changing the game, re-run `python web/build.py`. The `--coep` option on
both `build.py` and `server.py` selects the Cross-Origin-Embedder-Policy
(`credentialless` by default, `require-corp` for strict same-origin-only builds,
or empty to disable COEP entirely — note that disabling it breaks Pyodide's
`SharedArrayBuffer` access).