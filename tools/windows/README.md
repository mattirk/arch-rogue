# Windows x64 builds

The public release workflow and private Steam workflow use `windows-2022`,
Odin built from the pinned source revision, VS 2022 x64 C++ tools and
Windows SDK, and the vendored static raylib 6.0 MSVC library. Compiler commit
must match root `toolchain.properties`. The pinned source includes Windows
LLVM 20.1.0 binaries, so its backend has an explicit platform pin here; Linux retains
LLVM 21.1.8. The verifier checks the native host's backend and rejects drift.
Windows downloads are locked in this directory's `toolchain.properties`.
The raylib archive's upstream provenance and reproducibility limitation are recorded under
`vendor/raylib/windows/PROVENANCE.md`.

Run from Git Bash on a Windows machine with Odin and the VS x64 tools on PATH:

```bash
./build.sh check
./build.sh test
./build.sh windows-release
./build.sh windows-package
./build.sh windows-audit --bundle build/windows/package/arch-rogue
```

The Python build helper resolves Bash from the Git for Windows installation
that supplies `git.exe`. It does not require a WSL distribution.

`test` treats allocator errors as failures on every platform. Windows tests
reserve an 8 MiB stack for nested persistence fixtures and log test state
transitions so an abrupt native exit can be traced to the active tests. This
changes only the headless test executable's stack, not the game's stack.

`windows-package` builds, stages and audits the complete assets/licenses,
boots a temporary copy for five frames, checks the completion marker, and
writes `dist/arch-rogue-v<VERSION>-<SHA12>-windows-x64.zip`. It validates the
ZIP again after extraction. The executable resolves assets beside itself,
even with an unrelated launch working directory. Smoke saves use a temporary
directory and are removed on shutdown.

CI runs `setup.ps1` to build the exact compiler revision, fetch verified Mesa
graphics, set the Visual Studio environment, and expose `ARCH_ROGUE_WINDOWS_MESA`. Mesa enables
software OpenGL 3.3 on hosted runners; its DLLs are copied only into the
temporary smoke directory. They never enter the ZIP or Steam payload. Local
smoke uses the machine's graphics driver when that variable is absent.

The vendored static raylib library uses the dynamic Visual C++ runtime.
Packaging copies required `vcruntime140.dll` / `vcruntime140_1.dll` files from
`VCToolsRedistDir/x64/Microsoft.VC*.CRT/` beside the executable. CI exports
`VCToolsRedistDir` from the same VS developer environment used for linking.
Runtime files are included only in distributions, not committed to source.
This follows Microsoft's [app-local deployment guidance](https://learn.microsoft.com/en-us/cpp/windows/determining-which-dlls-to-redistribute?view=msvc-170).

`windows-audit` also runs on Linux. It verifies the static library hash, PE32+
x64 identity, executable/DLL type, system imports plus the complete required
app-local VC runtime dependency set, exact root entries, and source-matching
assets/licenses. Missing or wrong-architecture runtime DLLs, unknown DLL
dependencies, `steam_appid.txt`, and extra Mesa files fail the audit.

For the private Steam build, place the authorized SDK redistributable
`steam_api64.dll` in `build/steam/sdk/`, then run `./build.sh steam-windows`.
The depot uses `arch-rogue.exe`; the standalone ZIP uses `archrogue.exe`.
No SDK runtime is included in GitHub release artifacts or committed to source.
The private workflow uploads Linux and Windows together, requiring both
`STEAM_LINUX_DEPOT_ID` and `STEAM_WINDOWS_DEPOT_ID` repository/environment variables in
GitHub's `steam` environment, plus its existing SDK and builder secrets.
SetLive `default` remains refused. Dry runs build both payloads and render the
combined VDF without authenticating to steamcmd or uploading.

Native CI and software graphics are automation checks. Before advertising
Windows release readiness, run the workflow and validate a real Windows
GPU/controller, Steam install/launch, live achievement unlock, and save/resume.
macOS is unsupported; there is no macOS build or depot lane.
