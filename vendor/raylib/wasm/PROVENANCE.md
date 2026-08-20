# raylib 6.0 web (WebAssembly) archive provenance

- Upstream: `https://github.com/raysan5/raylib`
- Tag: `6.0`
- Commit: `dbc56a87da87d973a9c5baa4e7438a9d20121d28`
- Source archive: `https://github.com/raysan5/raylib/archive/refs/tags/6.0.tar.gz`
- Source archive SHA-256: `2b3ee1e2120c7a0796b33062c7e9a694dd8a8caa56a96319ac8c8ecf54a90d0b`
- Arch Rogue patch: none (the reviewed Android patch touches only `src/platforms/rcore_android.c`; the web platform builds unpatched upstream sources)
- Toolchain: Emscripten `6.0.7` (emsdk-activated, clang 24.0.0-based)
- Build: CMake + Ninja, `Release`, `-O2 -DNDEBUG`, IPO/LTO off, `-ffile-prefix-map`/`-fdebug-prefix-map` normalized to `/arch-rogue-raylib-build`
- Platform: `PLATFORM=Web` (`rcore.c` with the Emscripten/GLFW web backend)
- Graphics API: `GRAPHICS_API_OPENGL_ES3` (WebGL2-only contract; no GLES2/WebGL1 fallback archive exists)

`tools/rebuild_raylib_web.sh` is the sole refresh path. It verifies the pinned
source checksum, refuses unsafe archive paths, builds with the pinned
Emscripten toolchain, audits the produced archive (web platform objects
present, no desktop/Android/DRM platform objects, expected raylib and
Emscripten symbol surface), and then either verifies the staged output against
the committed `SHA256SUMS` (default) or refreshes the checksums as an explicit
reviewed maintainer action (`--refresh-checksums`).

The game links this archive through the Odin binding's wasm branch
(`vendor/raylib/raylib.odin`, `RAYLIB_WASM_LIB`) and the Emscripten link step
driven by `tools/web.sh`. The exported memory/heap policy lives in
`web/toolchain.properties`, not here. Ordinary game builds never download or
rebuild raylib; they verify and consume this vendored archive.
