# raylib 6.0 Android archive provenance

- Upstream: `https://github.com/raysan5/raylib`
- Tag: `6.0`
- Commit: `dbc56a87da87d973a9c5baa4e7438a9d20121d28`
- Source archive: `https://github.com/raysan5/raylib/archive/refs/tags/6.0.tar.gz`
- Source archive SHA-256: `2b3ee1e2120c7a0796b33062c7e9a694dd8a8caa56a96319ac8c8ecf54a90d0b`
- Arch Rogue patch: `raylib-6.0-arch-rogue.patch`
- Patch SHA-256: `e4a52aac6f37b01eb838b5495d40dd734fcf2560dbe20865b40f5df8c2ae4d5c`
- NDK: `r28c` / `28.2.13676358`
- NDK Clang recorded for the committed archives: `19.0.1`
- Android API baseline: `28`
- Build: CMake Release, static, position-independent code, `PLATFORM=Android`
- Graphics API: `GRAPHICS_API_OPENGL_ES2`
- ABIs: `arm64-v8a`, `armeabi-v7a`, `x86_64`

`tools/rebuild_raylib_android.sh` is the sole refresh path. It verifies the
pinned source archive before extraction, configures the exact NDK/API/ABI/ES2
contract, applies the checksum-pinned Arch Rogue bridge/event-pump patch,
enables `CMAKE_POSITION_INDEPENDENT_CODE`, and audits every resulting archive
before installation. The patch exposes app-private storage, lifecycle events,
safe content insets, API/focus facts, modern Android Back dispatch, and logcat
without adding a second game loop.

The upstream CMake target folds `android_native_app_glue.c.o` into the static
archive. Odin's Android subtarget compiles that same NDK glue and supplies
`ANativeActivity_onCreate`, so the refresh script removes the duplicate archive
member. The normalized archive retains raylib's `android_main`, which invokes
the Odin-exported C `main` entry point.

The exact committed archive hashes are recorded in `SHA256SUMS`. Ordinary game
builds verify all three hashes and inspect member names, ELF machine types, Android
entry symbols, and forbidden host GLIBC/X11/GLFW markers. They never download or
rebuild raylib and never select the existing desktop Linux/X11 archive.

The separate `bionic-compat/libpthread.so` file is an architecture-independent
linker script for a pinned Odin compiler defect; it is not raylib, an ELF shared
library, or an APK input. Its checksum is pinned in `android/toolchain.properties`,
and final ELF auditing forbids a `libpthread` dependency.
