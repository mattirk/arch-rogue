# Bionic pthread linker compatibility

Odin `dev-2026-07:301c287de` emits a desktop-style `-lpthread` argument while
linking `-target:linux_arm64 -subtarget:android`. Android pthread symbols are
provided by Bionic `libc`; NDK r28c intentionally has no standalone
`libpthread`.

`libpthread.so` is therefore an architecture-independent **linker script**, not
an ELF library. It redirects only the compiler-added lookup to `-lc`. The build
passes this directory to the linker but never stages or packages it. Its exact
checksum is pinned in `android/toolchain.properties`.

No Android raylib binding or archive declares a pthread library. Final native
and APK audits require an exact Android `DT_NEEDED` set and reject any
`libpthread`, host GLIBC, X11, GLX, or GLFW dependency/marker.
