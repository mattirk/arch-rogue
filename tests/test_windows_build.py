from __future__ import annotations

import os
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.windows import audit
from tools.windows import build as windows_build

ROOT = Path(__file__).resolve().parents[1]


def fixture_pe(*, machine=0x8664, dll=False, dependency='KERNEL32.dll') -> bytes:
    data = bytearray(1024)
    data[:2] = b'MZ'
    struct.pack_into('<I', data, 60, 0x80)
    data[0x80:0x84] = b'PE\0\0'
    struct.pack_into('<HHIIIHH', data, 0x84, machine, 1, 0, 0, 0, 240, 0x2022 if dll else 0x22)
    optional = 0x98
    struct.pack_into('<H', data, optional, 0x20b)
    struct.pack_into('<I', data, optional + 108, 16)
    struct.pack_into('<II', data, optional + 120, 0x1000, 40)
    section = optional + 240
    struct.pack_into('<IIII', data, section + 8, 512, 0x1000, 512, 512)
    struct.pack_into('<I', data, 512 + 12, 0x1050)
    name = dependency.encode() + b'\0'
    data[592:592+len(name)] = name
    return bytes(data)


class WindowsAuditTests(unittest.TestCase):
    def test_package_includes_and_audits_required_x64_vc_runtime_closure(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            binary = root / 'build/windows/archrogue.exe'
            binary.parent.mkdir(parents=True)
            binary.write_bytes(fixture_pe(dependency='VCRUNTIME140.dll'))
            (root / 'assets').mkdir()
            (root / 'assets/tile.png').write_bytes(b'asset')
            (root / 'vendor/raylib').mkdir(parents=True)
            for name in ('LICENSE', 'NOTICE', 'vendor/raylib/LICENSE'):
                (root / name).write_text(name)
            redist = root / 'redist'
            crt = redist / 'x64/Microsoft.VC143.CRT'
            crt.mkdir(parents=True)
            (crt / 'vcruntime140.dll').write_bytes(fixture_pe(dll=True, dependency='vcruntime140_1.dll'))
            (crt / 'vcruntime140_1.dll').write_bytes(fixture_pe(dll=True))
            (crt / 'msvcp140.dll').write_bytes(b'not needed')
            with patch.object(windows_build, 'ROOT', root), patch.object(audit, 'ROOT', root), \
                 patch.dict(os.environ, {'VCToolsRedistDir': str(redist)}):
                bundle = windows_build.stage()
                self.assertEqual({p.name for p in bundle.glob('*.dll')}, audit.VC_RUNTIME_DLLS)
                self.assertEqual(audit.digest(bundle / 'vcruntime140.dll'), audit.digest(crt / 'vcruntime140.dll'))
                audit.audit_bundle(bundle)
                (bundle / 'vcruntime140_1.dll').unlink()
                with self.assertRaisesRegex(ValueError, 'missing app-local runtime'):
                    audit.audit_bundle(bundle)
                (bundle / 'vcruntime140_1.dll').write_bytes(fixture_pe(dll=True, machine=0x14c))
                with self.assertRaisesRegex(ValueError, 'expected Windows x64'):
                    audit.audit_bundle(bundle)
                (bundle / 'vcruntime140_1.dll').write_bytes(fixture_pe(dll=True, dependency='unshipped.dll'))
                with self.assertRaisesRegex(ValueError, 'non-system DLL imports'):
                    audit.audit_bundle(bundle)
                (crt / 'vcruntime140_1.dll').unlink()
                with self.assertRaisesRegex(SystemExit, 'Expected one x64 redistributable'):
                    windows_build.stage()

    def test_build_uses_git_bash_when_wsl_bash_is_first_on_path(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            wsl = root / 'Windows/System32/bash.exe'
            wsl.parent.mkdir(parents=True)
            wsl.touch()
            installation = root / 'Program Files/Git'
            git = installation / 'cmd/git.exe'
            git.parent.mkdir(parents=True)
            git.touch()
            bash = installation / 'bin/bash.exe'
            bash.parent.mkdir(parents=True)
            bash.touch()
            with patch.object(windows_build.shutil, 'which', side_effect=lambda name: str(git if name == 'git' else wsl)), \
                 patch.object(windows_build, 'ROOT', root), \
                 patch.object(windows_build, 'verify_raylib'), \
                 patch.object(windows_build, 'pe_imports'), \
                 patch.object(windows_build.subprocess, 'run') as run:
                windows_build.build()
                verification_command = run.call_args_list[0].args[0]
                # resolve() expands Windows 8.3 paths such as RUNNER~1.
                # Check the selected file, not its short/long path spelling.
                self.assertTrue(Path(verification_command[0]).samefile(bash))
                self.assertFalse(Path(verification_command[0]).samefile(wsl))
                self.assertEqual(verification_command[1:], ['tools/verify_toolchain.sh', 'odin'])
                self.assertEqual(run.call_args_list[1].args[0][0:3], ['odin', 'build', 'src'])
                bash.unlink()
                with self.assertRaisesRegex(SystemExit, 'Git for Windows Bash was not found'):
                    windows_build.git_bash()

    @unittest.skipIf(os.name == 'nt', 'fake POSIX executables model Git Bash output')
    def test_wrapper_uses_native_test_extension_and_preserves_arguments(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            odin = root / 'odin'
            odin.write_text(
                '#!/bin/sh\ncase "$1" in\n'
                'version) printf "odin version dev-2026-07:301c287\\r\\n" ;;\n'
                'report) printf "Backend: LLVM %s\\r\\n" "$FAKE_ODIN_BACKEND" ;;\n'
                '*) printf "%s\\n" "$@" > "$FAKE_ODIN_ARGS" ;;\nesac\n'
            )
            odin.chmod(0o755)
            uname = root / 'uname'
            uname.write_text('#!/bin/sh\nprintf "%s\\n" "$FAKE_HOST"\n')
            uname.chmod(0o755)
            arguments = root / 'arguments.txt'
            env = dict(os.environ, PATH=str(root) + os.pathsep + os.environ['PATH'],
                       ODIN_SOURCE_DIR=str(root / 'no-checkout'), FAKE_ODIN_ARGS=str(arguments))
            for host in ('Linux', 'MINGW64_NT-10.0', 'MSYS_NT-10.0', 'CYGWIN_NT-10.0'):
                with self.subTest(host=host):
                    windows = host != 'Linux'
                    env.update(FAKE_HOST=host, FAKE_ODIN_BACKEND='20.1.0' if windows else '21.1.8')
                    result = subprocess.run(
                        ['bash', str(ROOT / 'build.sh'), 'test', '-define:ODIN_TEST_THREADS=1'],
                        cwd=root, env=env, capture_output=True, text=True,
                    )
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    suffix = '.exe' if windows else ''
                    expected = [
                        'test', 'tests', f'-out:build/archrogue_tests{suffix}',
                        '-vet', '-define:ODIN_TEST_FAIL_ON_BAD_MEMORY=true',
                    ]
                    if windows:
                        expected += ['-extra-linker-flags:/STACK:8388608', '-define:ODIN_TEST_LOG_STATE_CHANGES=true']
                    self.assertEqual(arguments.read_text().splitlines(), expected + ['-define:ODIN_TEST_THREADS=1'])

    @unittest.skipIf(os.name == 'nt', 'fake POSIX executables model Git Bash output')
    def test_windows_compiler_pin_accepts_crlf_and_rejects_revision_or_backend_drift(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            odin = root / 'odin'
            uname = root / 'uname'
            uname.write_text('#!/bin/sh\nprintf "MINGW64_NT-10.0\\n"\n')
            uname.chmod(0o755)
            env = dict(os.environ, PATH=str(root) + os.pathsep + os.environ['PATH'], ODIN_SOURCE_DIR=str(root / 'no-checkout'))
            odin.write_text('#!/bin/sh\nif [ "$1" = version ]; then printf "%s\\r\\n" "$FAKE_ODIN_BANNER"; else printf "Backend: LLVM %s\\r\\n" "$FAKE_ODIN_BACKEND"; fi\n')
            odin.chmod(0o755)
            executables = [
                'odin', 'odin.exe', '/opt/odin/odin',
                r'D:\a\arch-rogue-master\arch-rogue-master\build\windows\toolchain\odin\odin.exe',
                r'C:\Program Files\Odin\odin.exe',
                'D:/a/arch-rogue-master/build/windows/toolchain/odin/odin.exe',
            ]
            for executable in executables:
                for version, revision, backend, succeeds in [
                    ('dev-2026-07', '301c287', '20.1.0', True),
                    ('dev-2026-07', '301c287de', '20.1.0', True),
                    ('dev-2026-07', 'ab0131c', '20.1.0', False),
                    ('dev-2026-07', '301c287de', '21.1.8', False),
                    ('dev-2026-06', '301c287de', '20.1.0', False),
                    ('dev-2026-07', '301c287 extra', '20.1.0', False),
                ]:
                    banner = f'{executable} version {version}:{revision}'
                    with self.subTest(banner=banner, backend=backend):
                        env.update(FAKE_ODIN_BANNER=banner, FAKE_ODIN_BACKEND=backend)
                        result = subprocess.run(['bash', str(ROOT / 'tools/verify_toolchain.sh'), 'odin'], env=env, capture_output=True, text=True)
                        self.assertEqual(result.returncode == 0, succeeds, result.stdout + result.stderr)

    def test_pinned_archive(self):
        audit.verify_raylib()

    def test_pe_rejects_wrong_architecture_type_and_runtime_dependencies(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'test.exe'
            path.write_bytes(fixture_pe())
            self.assertEqual(audit.pe_imports(path), {'kernel32.dll'})
            for options in ({'machine': 0x14c}, {'dll': True}, {'dependency': 'VCRUNTIME140.dll'}, {'dependency': 'libwinpthread-1.dll'}):
                with self.subTest(options=options):
                    path.write_bytes(fixture_pe(**options))
                    with self.assertRaises(ValueError):
                        audit.pe_imports(path)
            path.write_bytes(fixture_pe(dll=True))
            self.assertEqual(audit.pe_imports(path, dll=True), {'kernel32.dll'})

    def test_bundle_rejects_stale_assets_sdk_omission_and_smoke_dlls(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'assets').mkdir()
            (root / 'assets/tile.png').write_bytes(b'asset')
            (root / 'vendor/raylib').mkdir(parents=True)
            for file in ('LICENSE', 'NOTICE', 'vendor/raylib/LICENSE'):
                (root / file).write_text(file)
            bundle = root / 'bundle'
            (bundle / 'assets').mkdir(parents=True)
            (bundle / 'assets/tile.png').write_bytes(b'asset')
            (bundle / 'licenses').mkdir()
            for file, source in [('LICENSE', 'LICENSE'), ('NOTICE', 'NOTICE'), ('raylib-LICENSE', 'vendor/raylib/LICENSE')]:
                (bundle / 'licenses' / file).write_text(source)
            (bundle / 'README.txt').write_text('launch')
            (bundle / 'archrogue.exe').write_bytes(fixture_pe())
            with patch.object(audit, 'ROOT', root):
                audit.audit_bundle(bundle)
                (bundle / 'assets/tile.png').write_bytes(b'stale')
                with self.assertRaisesRegex(ValueError, 'assets differ'):
                    audit.audit_bundle(bundle)
                (bundle / 'assets/tile.png').write_bytes(b'asset')
                for name in ('steam_appid.txt', 'opengl32.dll', 'steam_api64.dll'):
                    (bundle / name).write_bytes(b'unexpected')
                    with self.assertRaisesRegex(ValueError, 'Unexpected bundle'):
                        audit.audit_bundle(bundle)
                    (bundle / name).unlink()
                (bundle / 'archrogue.exe').rename(bundle / 'arch-rogue.exe')
                with self.assertRaisesRegex(ValueError, 'steam_api64.dll'):
                    audit.audit_bundle(bundle, steam=True)
                (bundle / 'steam_api64.dll').write_bytes(fixture_pe(dll=True))
                audit.audit_bundle(bundle, steam=True)

    @unittest.skipUnless((ROOT / 'tools/steam/render_build_scripts.py').exists(), 'private Steam renderer')
    def test_steam_combines_depots_and_refuses_default(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for platform, exe in [('linux', 'arch-rogue'), ('windows', 'arch-rogue.exe')]:
                (root / 'content' / platform / 'assets').mkdir(parents=True)
                (root / 'content' / platform / exe).write_bytes(b'fixture')
            command = [sys.executable, str(ROOT / 'tools/steam/render_build_scripts.py'), '--description', 'test', '--content-root', str(root / 'content'), '--output', str(root / 'scripts'), '--linux-depot', '100', '--windows-depot', '200']
            subprocess.run(command + ['--branch', 'prerelease'], check=True, capture_output=True)
            vdf = (root / 'scripts/app_build.vdf').read_text()
            for token in ('"100"', '"200"', '"5031380"', '"prerelease"'):
                self.assertIn(token, vdf)
            result = subprocess.run(command + ['--branch', 'default'], capture_output=True)
            self.assertNotEqual(result.returncode, 0)


if __name__ == '__main__':
    unittest.main()
