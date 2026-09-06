# Native Windows CI bootstrap. Downloads are hash-pinned; Mesa is smoke-only.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
Set-Location $root
$pins = @{}
Get-Content "$PSScriptRoot/toolchain.properties" | ForEach-Object {
    if ($_ -match '^([A-Z0-9_]+)=(.+)$') { $pins[$Matches[1]] = $Matches[2] }
}
$work = Join-Path $root 'build/windows/toolchain'
New-Item -ItemType Directory -Force $work | Out-Null
function Get-PinnedFile($url, $hash, $destination) {
    if (!(Test-Path $destination)) { Invoke-WebRequest $url -OutFile $destination }
    if ((Get-FileHash $destination -Algorithm SHA256).Hash.ToLowerInvariant() -ne $hash) {
        throw "Checksum mismatch: $destination"
    }
}
# Build the exact shared source revision: the official monthly Windows ZIP
# reports an earlier commit and must not silently bypass the revision check.
$shared = @{}
Get-Content "$root/toolchain.properties" | ForEach-Object {
    if ($_ -match '^([A-Z0-9_]+)=(.+)$') { $shared[$Matches[1]] = $Matches[2] }
}
$odin = Join-Path $work 'odin'
$env:GIT_LFS_SKIP_SMUDGE = '1'
if (!(Test-Path "$odin/.git")) {
    & git init $odin
    if ($LASTEXITCODE -ne 0) { throw 'Odin git init failed' }
    & git -C $odin remote add origin https://github.com/odin-lang/Odin.git
    if ($LASTEXITCODE -ne 0) { throw 'Odin remote setup failed' }
}
& git -C $odin fetch --depth 1 origin $shared.ODIN_COMMIT
if ($LASTEXITCODE -ne 0) { throw 'Odin source fetch failed' }
& git -C $odin checkout --detach FETCH_HEAD
if ($LASTEXITCODE -ne 0) { throw 'Odin source checkout failed' }
$revision = & git -C $odin rev-parse HEAD
if ($revision -ne $shared.ODIN_COMMIT) { throw 'Odin source revision mismatch' }
foreach ($entry in @(@('LLVM-C.dll', $pins.ODIN_WINDOWS_LLVM_DLL_SHA256), @('bin/llvm/windows/LLVM-C.lib', $pins.ODIN_WINDOWS_LLVM_LIB_SHA256))) {
    if ((Get-FileHash "$odin/$($entry[0])" -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry[1]) {
        throw "Odin LLVM checksum mismatch: $($entry[0])"
    }
}
Push-Location $odin
try {
    & cmd.exe /c 'build.bat release'
    if ($LASTEXITCODE -ne 0 -or !(Test-Path odin.exe)) { throw 'Odin Windows source build failed' }
} finally { Pop-Location }
$odin | Out-File $env:GITHUB_PATH -Append -Encoding utf8
"ODIN_SOURCE_DIR=$odin" | Out-File $env:GITHUB_ENV -Append -Encoding utf8

# Odin's linker needs the hosted VS 2022 x64 tools and Windows SDK.
$vswhere = "${env:ProgramFiles(x86)}/Microsoft Visual Studio/Installer/vswhere.exe"
$vs = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (!$vs) { throw 'Visual Studio x64 C++ tools missing' }
$command = "`"$vs/Common7/Tools/VsDevCmd.bat`" -no_logo -arch=x64 -host_arch=x64 && set"
$variables = & cmd.exe /c $command
if ($LASTEXITCODE -ne 0) { throw 'VsDevCmd failed' }
foreach ($line in $variables) {
    if ($line -match '^([^=]+)=(.*)$') {
        $key = $Matches[1]; $value = $Matches[2]
        if ($key -in @('INCLUDE', 'LIB', 'LIBPATH', 'VCToolsInstallDir', 'WindowsSdkDir', 'WindowsSDKVersion')) {
            "$key=$value" | Out-File $env:GITHUB_ENV -Append -Encoding utf8
        }
        if ($key -ieq 'Path') {
            $value.Split(';') | Where-Object { $_ } | Out-File $env:GITHUB_PATH -Append -Encoding utf8
        }
    }
}
Get-PinnedFile $pins.MESA_WINDOWS_URL $pins.MESA_WINDOWS_SHA256 "$work/mesa.7z"
& 7z x "$work/mesa.7z" "-o$work/mesa" -y | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Mesa extraction failed' }
$mesa = (Resolve-Path "$work/mesa/x64").Path
if (!(Test-Path "$mesa/opengl32.dll")) { throw 'Mesa x64 OpenGL runtime missing' }
"ARCH_ROGUE_WINDOWS_MESA=$mesa" | Out-File $env:GITHUB_ENV -Append -Encoding utf8
