#!/usr/bin/env python3
"""Audit native Windows x64 binaries and complete, source-matching bundles."""
from __future__ import annotations

import argparse
import hashlib
import re
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SYSTEM_DLLS = {
    'kernel32.dll', 'user32.dll', 'gdi32.dll', 'shell32.dll', 'winmm.dll',
    'advapi32.dll', 'ole32.dll', 'oleaut32.dll', 'uuid.dll', 'opengl32.dll',
    'comdlg32.dll', 'ws2_32.dll', 'bcrypt.dll', 'ntdll.dll', 'shlwapi.dll',
    'imm32.dll', 'version.dll', 'setupapi.dll', 'ucrtbase.dll', 'msvcrt.dll',
    'userenv.dll', 'dbghelp.dll', 'dwmapi.dll', 'shcore.dll', 'psapi.dll',
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_raylib() -> None:
    vendor = ROOT / 'vendor/raylib/windows'
    checksum = (vendor / 'SHA256SUMS').read_text().split()
    if len(checksum) != 2 or checksum[1] != 'raylib.lib' or not re.fullmatch(r'[0-9a-f]{64}', checksum[0]):
        raise ValueError('Windows raylib checksum contract is malformed')
    if digest(vendor / 'raylib.lib') != checksum[0]:
        raise ValueError('Windows raylib checksum mismatch')
    if not (vendor / 'raylib.lib').read_bytes().startswith(b'!<arch>\n'):
        raise ValueError('Windows raylib is not a static archive')


def pe_imports(path: Path, *, dll: bool = False) -> set[str]:
    data = path.read_bytes()
    if data[:2] != b'MZ' or len(data) < 64:
        raise ValueError(f'{path}: not a PE binary')
    pe = struct.unpack_from('<I', data, 60)[0]
    if data[pe:pe + 4] != b'PE\0\0':
        raise ValueError(f'{path}: invalid PE signature')
    machine, sections, _, _, _, optional_size, flags = struct.unpack_from('<HHIIIHH', data, pe + 4)
    optional = pe + 24
    if machine != 0x8664 or struct.unpack_from('<H', data, optional)[0] != 0x20b:
        raise ValueError(f'{path}: expected Windows x64 PE32+')
    if bool(flags & 0x2000) != dll:
        raise ValueError(f'{path}: incorrect executable/DLL type')
    section_table = optional + optional_size

    def offset(rva: int) -> int:
        for i in range(sections):
            start = section_table + 40 * i
            virtual_size, virtual_address, raw_size, raw_offset = struct.unpack_from('<IIII', data, start + 8)
            if virtual_address <= rva < virtual_address + max(virtual_size, raw_size):
                result = raw_offset + rva - virtual_address
                if result >= len(data):
                    break
                return result
        raise ValueError(f'{path}: unmapped PE RVA {rva:x}')

    directories = struct.unpack_from('<I', data, optional + 108)[0]
    if directories < 2:
        return set()
    imports_rva, _ = struct.unpack_from('<II', data, optional + 120)
    if directories > 13 and any(struct.unpack_from('<II', data, optional + 112 + 13 * 8)):
        raise ValueError(f'{path}: unexpected delay-loaded DLLs need an explicit audit')
    imports: set[str] = set()
    if imports_rva:
        pos = offset(imports_rva)
        while any(data[pos:pos + 20]):
            name_rva = struct.unpack_from('<I', data, pos + 12)[0]
            name_offset = offset(name_rva)
            end = data.index(b'\0', name_offset)
            name = data[name_offset:end].decode('ascii').lower()
            imports.add(name)
            pos += 20
    unexpected = {name for name in imports if name not in SYSTEM_DLLS and not name.startswith(('api-ms-win-crt-', 'api-ms-win-core-'))}
    if unexpected:
        raise ValueError(f'{path}: non-system DLL imports: {sorted(unexpected)}')
    return imports


def tree_digests(root: Path) -> dict[str, str]:
    result = {}
    for path in root.rglob('*'):
        if path.is_symlink():
            raise ValueError(f'Bundle/source symlink is not allowed: {path}')
        if path.is_file():
            result[path.relative_to(root).as_posix()] = digest(path)
    return result


def audit_bundle(bundle: Path, *, steam: bool = False) -> None:
    executable = 'arch-rogue.exe' if steam else 'archrogue.exe'
    expected = {executable, 'assets', 'licenses', 'README.txt'}
    if steam:
        expected.add('steam_api64.dll')
    actual = {p.name for p in bundle.iterdir()}
    if actual != expected:
        raise ValueError(f'Unexpected bundle entries: missing={expected-actual}, extra={actual-expected}')
    pe_imports(bundle / executable)
    if steam:
        pe_imports(bundle / 'steam_api64.dll', dll=True)
    if tree_digests(bundle / 'assets') != tree_digests(ROOT / 'assets'):
        raise ValueError('Packaged assets differ from canonical assets')
    licenses = {'LICENSE': ROOT / 'LICENSE', 'NOTICE': ROOT / 'NOTICE', 'raylib-LICENSE': ROOT / 'vendor/raylib/LICENSE'}
    if tree_digests(bundle / 'licenses') != {name: digest(path) for name, path in licenses.items()}:
        raise ValueError('Packaged licenses differ from canonical licenses')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path)
    parser.add_argument('--dll', action='store_true')
    parser.add_argument('--bundle', type=Path)
    parser.add_argument('--steam', action='store_true')
    args = parser.parse_args()
    verify_raylib()
    if args.binary:
        print('PE imports:', ', '.join(sorted(pe_imports(args.binary, dll=args.dll))))
    if args.bundle:
        audit_bundle(args.bundle, steam=args.steam)
    print('Windows audit passed')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, struct.error) as error:
        raise SystemExit(str(error)) from error
