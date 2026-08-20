# raylib 6.0 Linux archive provenance

`libraylib.a` originates from the real Git LFS payload bundled by
`odin-lang/Odin@dev-2026-07`. The upstream payload has SHA-256
`1199fb5be52a663c099ed42eae5eabba83754ca9a8d7f82e1514ae4d6623874b`.

That upstream archive was compiled with C23-enabled glibc headers and imports
`__isoc23_sscanf`, `__isoc23_strtol`, `__isoc23_strtoul`, and
`__isoc23_strtoll`. Those entrypoints are absent from the Ubuntu 22.04 / glibc
2.35 release baseline, preventing otherwise compatible binaries from linking.
raylib 6.0 is C99 code and does not require the C23 parsing extensions.

The committed archive is the upstream payload with only those undefined symbol
names normalized using GNU `objcopy`:

```bash
objcopy \
  --redefine-sym __isoc23_sscanf=__isoc99_sscanf \
  --redefine-sym __isoc23_strtol=strtol \
  --redefine-sym __isoc23_strtoul=strtoul \
  --redefine-sym __isoc23_strtoll=strtoll \
  libraylib.upstream.a libraylib.a
```

No raylib implementation bytes or archive members are added. The resulting
archive keeps `rcore.o`, `rshapes.o`, `rtextures.o`, `rtext.o`, `rglfw.o`,
`rmodels.o`, and `raudio.o`, and its exact transformed SHA-256 is recorded in
`SHA256SUMS`. `tools/verify_linux_raylib.py` checks the digest, member set, and
absence of C23-only imports before CI links the game.
