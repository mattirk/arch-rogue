# Windows raylib archive

`raylib.lib` is the upstream x64 MSVC static raylib 6.0 library vendored by
odin-lang/Odin@dev-2026-07, commit
`301c287de90393608fb7c5b260210e1e67caf0fd`. Retrieved 2026-09-06 from:

https://media.githubusercontent.com/media/odin-lang/Odin/301c287de90393608fb7c5b260210e1e67caf0fd/vendor/raylib/windows/raylib.lib

The committed SHA256SUMS matches that revision's Git LFS object ID; size is
5,297,172 bytes. It contains the seven raylib/GLFW x64 COFF object modules and
an embedded Windows resource. The binding uses the same static CRT exclusion
as upstream Odin. Its COFF directives request `MSVCRT`: static raylib does
not imply a static C runtime. Windows packages therefore include required
`vcruntime140*.dll` files from the linked Visual Studio toolset's x64
redistributable directory. No raylib DLL is packaged. Runtime binaries remain
build inputs/packaged dependencies, never committed source files.

Source identity: raylib 6.0, upstream commit
`dbc56a87da87d973a9c5baa4e7438a9d20121d28` (root toolchain.properties).
License: ../LICENSE (zlib/libpng).

This is a checksum-pinned upstream binary, not a locally reproduced build.
Upstream's MSVC build environment is not independently reproducible from this
repository. CI verifies the archive checksum and the final PE imports, and
runs native headless tests plus a packaged boot with software OpenGL. Real
Windows GPU/controller/Steam-client acceptance remains a separate check.
