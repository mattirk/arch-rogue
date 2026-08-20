# Arch Rogue — web (WebAssembly) platform

This directory owns the browser platform edge: the pinned toolchain contract
(`toolchain.properties`), the Emscripten shell page (`shell.html`), the JS
persistence/pack bridge (`library_archrogue.js`), and the C
`requestAnimationFrame` entry driver (`main_web.c`). Odin-side web code lives
in `src/main_web.odin`; build/audit/serve tooling lives in `tools/web.sh`,
`tools/web_audit.py`, `tools/web_pack_assets.py`, and `tools/web_serve.py`.

## Commands

```bash
./build.sh web-preflight   # toolchain pins, vendored archive, budget/heap declaration
./build.sh web-build       # release build: payload split, link, content addressing, Brotli, audit
./build.sh web-audit       # budget, heap pin, no ASYNCIFY, content/pack integrity, no CDN refs
./build.sh web-serve       # local server with production-shaped headers (.br, immutable caching)

node tools/web_smoke.mjs   # 15 headless smoke scenarios (Chromium-family via CDP)
node tools/web_profile.mjs # crowded-floor profiling in Chromium + Firefox; --gate to enforce
```

To validate a combined Pages staging tree rather than a dist root, run the smoke
with `--dist build/pages --entry-path /play/index.html`.

The pinned Emscripten SDK is discovered via `$EMSDK`, then `/opt/emsdk`, then
`~/emsdk`. `tools/rebuild_raylib_web.sh` is the maintainer-only refresh path
for the vendored raylib web archive (`vendor/raylib/wasm/`).

## Browser baseline

Current desktop Chromium-family and Firefox releases with WebGL2. The shell
gates on WebGL2 before downloading the runtime and shows an unsupported-browser
message otherwise; there is deliberately no WebGL1/GLES2 fallback. Safari and
mobile browsers are not yet validated and are not claimed. High-DPI rendering
is bounded by `AR_MAX_DPR` in `shell.html` (1.0 for this alpha: framebuffer ==
CSS pixels, which also guarantees correct pointer mapping).

## Persistence and durability

Saves live in IndexedDB (`arch-rogue-save` database, `kv` store) as
byte-identical copies of the desktop document formats under the same
`/save/*.json[.tmp|.bak]` keys, so the shared checksum/migration/tmp-bak
recovery/Chronicle logic runs unchanged. The wasm side mirrors the store in
memory: reads are synchronous against the mirror, writes flush to IndexedDB
asynchronously.

Durability is best-effort at the edges by design: checkpoints fire on
`visibilitychange` (hidden) and `pagehide`, and the browser may still tear the
page down before an IndexedDB transaction commits. The scheduler also writes
continuously during play (dirty-run coalescing, same policy as desktop), so
the realistic exposure is the last moments before a close. Nothing in the UI
or docs promises synchronous or guaranteed final writes. Saves are per-browser
and per-origin; clearing site data deletes them.

## Payload

`web-build` splits assets into a core Emscripten preload (~19 MB on the wire
with Brotli, enforced against `WEB_INITIAL_DOWNLOAD_BUDGET_BYTES`) and seven
content-addressed `.arpack` blobs (per-archetype clips, social actors, bosses)
fetched at run start and digest-verified. A global browser queue writes at most
one packed file into MEMFS per animation frame; Odin then adopts at most one
actor per game frame, only while no authored SFX is playing. This protects the
upstream main-thread `ScriptProcessorNode` mixer during the opening story modal,
and procedural fallbacks cover the seconds before a pack lands.
All runtime payload files are content-addressed. `web-serve` gives hashed files
immutable caching and keeps `index.html` and `packs.json` mutable; there is no
runtime CDN dependency. Those response-header rules describe self-hosting, not
GitHub Pages, which controls its own compression and cache headers.

## GitHub Pages deployment

The public release workflow builds and audits
`arch-rogue-v<version>-<sha12>-web.tar.gz`, attaches it to the prerelease, then
downloads that exact artifact in `prepare-pages`. It rejects unsafe archive
paths, links, special entries, duplicate members, and any root other than the
single `arch-rogue-web/` directory before stripping that root into
`build/pages/play`. The staged copy is audited again, combined with the download
site, bounded below the Pages 1 GB limit, and deployed at
<https://mattirk.github.io/arch-rogue/play/>. The post-deploy job retries both
the site-relative `play/` route and `play/packs.json`.

All browser network paths remain relative so the project Pages base
`/arch-rogue/` and a future custom-domain root both work. The committed
`website/` source never contains generated game files.

GitHub Pages does not promise the precompressed `.br` negotiation or the
immutable/no-cache headers supplied by `web-serve`. The existing ~19 MB Brotli
initial-download measurement remains the audited self-hosted release contract;
it must not be described as measured Pages transfer behavior. Verify Pages MIME,
compression, caching, and transfer sizes against the deployed endpoint when
recording hosting evidence.
