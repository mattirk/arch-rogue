#!/usr/bin/env python3
"""Native Windows release packaging shared by GitHub and private Steam CI."""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from audit import ROOT, audit_bundle, pe_imports, verify_raylib


def build() -> None:
    verify_raylib()
    subprocess.run(['bash', 'tools/verify_toolchain.sh', 'odin'], cwd=ROOT, check=True)
    output = ROOT / 'build/windows/archrogue.exe'
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(['odin', 'build', 'src', f'-out:{output}', '-target:windows_amd64', '-vet', '-o:speed'], cwd=ROOT, check=True)
    pe_imports(output)


def stage() -> Path:
    destination = ROOT / 'build/windows/package/arch-rogue'
    shutil.rmtree(destination, ignore_errors=True)
    destination.mkdir(parents=True)
    executable = 'archrogue.exe'
    shutil.copy2(ROOT / 'build/windows/archrogue.exe', destination / executable)
    shutil.copytree(ROOT / 'assets', destination / 'assets')
    (destination / 'licenses').mkdir()
    for source, name in [('LICENSE', 'LICENSE'), ('NOTICE', 'NOTICE'), ('vendor/raylib/LICENSE', 'raylib-LICENSE')]:
        shutil.copy2(ROOT / source, destination / 'licenses' / name)
    (destination / 'README.txt').write_text(
        f'Arch Rogue for Windows x64\n\nExtract the entire folder, then launch {executable}.\n'
        'Keep assets and licenses beside the executable.\n'
        'Saves are stored in your local application-data directory under arch-rogue.\n', encoding='utf-8')
    audit_bundle(destination)
    return destination


def smoke(bundle: Path, *, executable: str = 'archrogue.exe') -> None:
    # Mesa lives only in this temporary copy, never in release/depot payloads.
    with tempfile.TemporaryDirectory(prefix='arch-rogue-windows-smoke-') as temp:
        work = Path(temp)
        copy = work / 'arch-rogue'
        shutil.copytree(bundle, copy)
        env = os.environ.copy()
        mesa = env.get('ARCH_ROGUE_WINDOWS_MESA')
        if mesa:
            mesa_path = Path(mesa)
            if not (mesa_path / 'opengl32.dll').is_file():
                raise SystemExit('Mesa OpenGL runtime missing')
            for dll in mesa_path.glob('*.dll'):
                shutil.copy2(dll, copy / dll.name)
            env.update(GALLIUM_DRIVER='llvmpipe', LIBGL_ALWAYS_SOFTWARE='1')
        env.update(ARCH_ROGUE_SMOKE_TEST='1', ARCH_ROGUE_NO_STEAM='1')
        exe = copy / executable
        result = subprocess.run([str(exe)], cwd=work, env=env, capture_output=True, text=True, errors='replace', timeout=120)
        log = result.stdout + result.stderr
        log_path = ROOT / 'build/windows' / f'{executable}-smoke.log'
        log_path.write_text(log, encoding='utf-8')
        print(log)
        if result.returncode != 0 or 'ARCH_ROGUE_SMOKE_TEST ok' not in log:
            raise SystemExit(f'Windows packaged smoke failed: exit={result.returncode}; {log_path}')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['build', 'package'])
    args = parser.parse_args()
    if os.name != 'nt':
        raise SystemExit('Windows builds require native Windows, pinned Odin, and VS 2022 x64 C++ tools; see tools/windows/README.md')
    if args.command == 'build':
        build()
        return
    build()
    bundle = stage()
    smoke(bundle)
    audit_bundle(bundle)
    version = re.search(r'^VERSION :: "([^"]+)"', (ROOT / 'src/main.odin').read_text(), re.M)[1]
    sha = subprocess.check_output(['git', 'rev-parse', '--short=12', 'HEAD'], cwd=ROOT, text=True).strip()
    output = ROOT / f'dist/arch-rogue-v{version}-{sha}-windows-x64'
    output.parent.mkdir(exist_ok=True)
    archive = shutil.make_archive(str(output), 'zip', bundle.parent, bundle.name)
    # Validate the actual shipping ZIP after extraction, too.
    with tempfile.TemporaryDirectory() as temp:
        shutil.unpack_archive(archive, temp)
        audit_bundle(Path(temp) / bundle.name)
    print(f'Windows release: {archive}')


if __name__ == '__main__':
    main()
