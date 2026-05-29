#!/usr/bin/env python3
"""
================================================================================
  inspect_exe.py — FX Machine PyInstaller Bundle Inspector (PyInstaller 6.20+)
================================================================================
  Usage:
      python inspect_exe.py
      python inspect_exe.py --exe path/to/FX_Machine.exe
      python inspect_exe.py --verbose
      python inspect_exe.py --quick

  PyInstaller 6.20 onedir layout (confirmed from actual build output):
  ─────────────────────────────────────────────────────────────────────
  dist/FX_Machine/
  ├── FX_Machine.exe          ← EXE stub + EMBEDDED PYZ + PKG archives
  │                             (~2-5 MB, contains ALL .pyc modules inside)
  ├── config/                 ← manually copied by build.py
  │   ├── default.toml
  │   ├── EXAMPLES.toml
  │   └── README.md
  └── _internal/              ← DLLs, .pyd C extensions, base_library.zip only
      ├── base_library.zip    ← compressed stdlib (io, os, threading, etc.)
      ├── python312.dll
      ├── SDL2.dll
      ├── _tkinter.pyd
      ├── tcl86t.dll
      ├── tk86t.dll
      ├── pygame/             ← pygame data files
      └── ... (other DLLs and .pyd files)

  KEY DIFFERENCE from PyInstaller 5:
    PYZ-00.pyz and FX_Machine.pkg are NOT separate files in _internal/.
    They are EMBEDDED INSIDE FX_Machine.exe as appended archives.
    To read the module list we must parse the EXE's CArchive overlay.

  CArchive format (appended to end of PE binary):
    The EXE ends with a CArchive containing a TOC of all bundled files.
    Magic cookie "MEI\014\013\012\013\016" marks the archive start.
    The TOC lists entries including the PYZ archive and all module names.

  Exit codes:
      0 = all checks passed
      1 = warnings only
      2 = errors found — do not ship
================================================================================
"""

import sys
import os
import struct
import zlib
import argparse
import time
import importlib
from pathlib import Path
from typing import Optional

# ═══════════════════════════════════════════════════════════════════════════
#  ANSI COLORS
# ═══════════════════════════════════════════════════════════════════════════

try:
    import ctypes
    ctypes.windll.kernel32.SetConsoleMode(
        ctypes.windll.kernel32.GetStdHandle(-11), 7
    )
except Exception:
    pass


class C:
    OK   = "\033[92m"
    WARN = "\033[93m"
    FAIL = "\033[91m"
    INFO = "\033[96m"
    DIM  = "\033[90m"
    BOLD = "\033[1m"
    END  = "\033[0m"


# ═══════════════════════════════════════════════════════════════════════════
#  RESULTS TRACKER
# ═══════════════════════════════════════════════════════════════════════════

class Results:
    def __init__(self):
        self.checks = 0
        self.passed = 0
        self.warned = 0
        self.failed = 0
        self.errors = []
        self.warns  = []
        self._sp = self._sw = self._sf = 0

    def ok(self, label, detail=""):
        self.checks += 1
        self.passed += 1
        if VERBOSE:
            msg = f"  {C.OK}✓{C.END} {label}"
            if detail:
                msg += f"  {C.DIM}({detail}){C.END}"
            print(msg)

    def warn(self, label, detail=""):
        self.checks += 1
        self.warned += 1
        msg = f"  {C.WARN}⚠{C.END} {label}"
        if detail:
            msg += f"\n      {C.DIM}{detail}{C.END}"
        print(msg)
        self.warns.append(label)

    def fail(self, label, detail=""):
        self.checks += 1
        self.failed += 1
        msg = f"  {C.FAIL}✗{C.END} {label}"
        if detail:
            msg += f"\n      {C.DIM}{detail}{C.END}"
        print(msg)
        self.errors.append(label)

    def info(self, msg):
        print(f"  {C.INFO}ℹ{C.END} {msg}")

    def begin_section(self):
        self._sp = self.passed
        self._sw = self.warned
        self._sf = self.failed

    def end_section(self):
        if VERBOSE:
            return
        np = self.passed - self._sp
        nw = self.warned - self._sw
        nf = self.failed - self._sf
        if nw == 0 and nf == 0 and np > 0:
            print(f"  {C.OK}✓{C.END} {np} check(s) passed")


R = Results()

# ═══════════════════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════════════════

def _parse_args():
    p = argparse.ArgumentParser(
        description="FX Machine .exe bundle inspector (PyInstaller 6.20+)"
    )
    p.add_argument(
        "--exe", type=Path,
        default=Path("dist") / "FX_Machine" / "FX_Machine.exe",
        help="Path to the .exe (default: dist/FX_Machine/FX_Machine.exe)",
    )
    p.add_argument("--verbose", "-v", action="store_true",
                   help="Show all checks including passed ones")
    p.add_argument("--quick", "-q", action="store_true",
                   help="Skip EXE binary parsing (faster)")
    return p.parse_args()


args     = _parse_args()
VERBOSE  = args.verbose
QUICK    = args.quick
EXE_PATH: Path   = args.exe.resolve()
DIST_DIR: Path   = EXE_PATH.parent
INTERNAL: Path   = DIST_DIR / "_internal"
CFG_DIR:  Path   = DIST_DIR / "config"


# ═══════════════════════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def header(title: str):
    print(f"\n{C.BOLD}{C.INFO}━━━ {title} ━━━{C.END}")
    R.begin_section()


def fmt_size(n: int) -> str:
    if n >= 1024 * 1024:
        return f"{n / (1024 * 1024):.1f} MB"
    if n >= 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n} B"


def walk(folder: Path) -> list[Path]:
    return sorted(p for p in folder.rglob("*") if p.is_file())


def find_in_tree(root: Path, pattern: str) -> list[Path]:
    return list(root.rglob(pattern)) if root.exists() else []


# ═══════════════════════════════════════════════════════════════════════════
#  CARCHIVE PARSER
#
#  PyInstaller 6.20 embeds the PYZ archive and all module metadata inside
#  the EXE itself as an appended CArchive. The format:
#
#  [ Windows PE binary ]
#  [ ZlibArchive (PYZ) — compressed .pyc modules ]
#  [ CArchive TOC      — table of contents        ]
#  [ CArchive footer   — magic + offsets          ]
#
#  Footer format (at the very end of the file, 40 bytes):
#    4  bytes: cookie "MEI\014\013\012\013\016" (8 bytes actually)
#    ... then offsets and lengths
#
#  We read the footer to locate the TOC, then parse the TOC to get
#  all bundled names including Python module paths.
#
#  The TOC entry format:
#    4 bytes: entry length (including this field)
#    4 bytes: offset of data from archive start
#    4 bytes: compressed size
#    4 bytes: uncompressed size
#    1 byte:  compression flag
#    1 byte:  type code
#    N bytes: null-terminated name string
# ═══════════════════════════════════════════════════════════════════════════

# PyInstaller CArchive magic cookie (8 bytes)
CARCHIVE_MAGIC = b"MEI\014\013\012\013\016"

# Type codes for CArchive entries
CARCHIVE_TYPES = {
    b'b': 'binary',
    b'd': 'dependency',
    b'o': 'runtime-option',
    b'p': 'pyc-module',
    b'P': 'pyc-pkg',
    b's': 'script',
    b'x': 'data',
    b'z': 'pyz-archive',
    b'Z': 'splash',
    b'm': 'symlink',
}


def _find_carchive_footer(data: bytes) -> Optional[int]:
    """
    Locate the CArchive footer in the EXE binary.
    Searches backward from the end of the file for the magic cookie.
    Returns the byte offset of the magic, or None if not found.
    """
    # Search in the last 8 KB — the footer is always at the very end
    search_window = data[-8192:]
    idx = search_window.rfind(CARCHIVE_MAGIC)
    if idx == -1:
        return None
    return len(data) - len(search_window) + idx


def parse_carchive_toc(exe_data: bytes) -> tuple[list[dict], str]:
    """
    Parse the CArchive embedded in the EXE to extract the TOC.

    Returns:
        (entries, status_message)
        entries: list of dicts with keys: name, type_code, type_name,
                 offset, compressed_size, uncompressed_size, is_compressed
        status_message: human-readable description of what was found
    """
    magic_offset = _find_carchive_footer(exe_data)
    if magic_offset is None:
        return [], "CArchive magic not found in EXE"

    # CArchive footer layout after the magic (PyInstaller 6):
    #   8 bytes: magic (already found)
    #   8 bytes: archive length (total size of the CArchive overlay)
    #   8 bytes: TOC offset (from start of archive)
    #   4 bytes: TOC size (bytes)
    #   4 bytes: Python version (e.g. 312)
    #   64 bytes: application name (null-padded)
    #
    # Total footer: 8+8+8+4+4+64 = 96 bytes
    # But layouts vary — we try multiple struct formats

    footer_start = magic_offset

    # Try PyInstaller 6 footer format (96 bytes from magic)
    try:
        footer = exe_data[footer_start:]
        # Skip magic (8 bytes)
        pos = 8
        # archive_length (8 bytes, little-endian uint64)
        archive_len = struct.unpack_from("<Q", footer, pos)[0]
        pos += 8
        # toc_offset (8 bytes, little-endian uint64)
        toc_offset = struct.unpack_from("<Q", footer, pos)[0]
        pos += 8
        # toc_size (4 bytes)
        toc_size = struct.unpack_from("<I", footer, pos)[0]
        pos += 4
        # python_version (4 bytes)
        py_ver = struct.unpack_from("<I", footer, pos)[0]
        pos += 4
        # app_name (64 bytes, null-padded)
        app_name_raw = footer[pos:pos + 64]
        app_name = app_name_raw.split(b"\x00")[0].decode("utf-8", errors="replace")

        # Validate: archive_len should be reasonable
        if archive_len > len(exe_data) or archive_len == 0:
            raise ValueError(f"Implausible archive_len: {archive_len}")

        # The archive starts at: len(exe_data) - archive_len
        archive_start = len(exe_data) - archive_len

        # TOC is at archive_start + toc_offset
        toc_start = archive_start + toc_offset
        toc_data  = exe_data[toc_start: toc_start + toc_size]

        entries = _parse_toc(toc_data, archive_start)
        status = (
            f"PyInstaller 6 format — archive {fmt_size(archive_len)}, "
            f"Python {py_ver}, app '{app_name}', {len(entries)} TOC entries"
        )
        return entries, status

    except Exception as e1:
        # Fallback: try PyInstaller 5 footer format (different struct)
        try:
            footer = exe_data[footer_start:]
            pos = 8   # skip magic
            # PyInstaller 5: all fields are 4-byte ints
            pkg_len    = struct.unpack_from("<I", footer, pos)[0]; pos += 4
            toc_offset = struct.unpack_from("<I", footer, pos)[0]; pos += 4
            toc_size   = struct.unpack_from("<I", footer, pos)[0]; pos += 4
            py_ver     = struct.unpack_from("<I", footer, pos)[0]; pos += 4
            # no app_name in v5 footer

            archive_start = len(exe_data) - pkg_len
            toc_start = archive_start + toc_offset
            toc_data  = exe_data[toc_start: toc_start + toc_size]

            entries = _parse_toc(toc_data, archive_start)
            status = (
                f"PyInstaller 5 format — archive {fmt_size(pkg_len)}, "
                f"Python {py_ver}, {len(entries)} TOC entries"
            )
            return entries, status

        except Exception as e2:
            return [], f"Footer parse failed: v6={e1}  v5={e2}"


def _parse_toc(toc_data: bytes, archive_start: int) -> list[dict]:
    """
    Parse a flat sequence of CArchive TOC entries.

    Each entry:
      4 bytes: total entry length (including this field)
      4 bytes: data offset from archive_start
      4 bytes: compressed data size
      4 bytes: uncompressed data size
      1 byte:  is_compressed flag
      1 byte:  type code (ASCII)
      N bytes: null-terminated name (entry_len - 18 bytes)
    """
    entries = []
    pos = 0
    while pos < len(toc_data):
        if pos + 18 > len(toc_data):
            break
        try:
            entry_len         = struct.unpack_from("<I", toc_data, pos)[0]
            data_offset       = struct.unpack_from("<I", toc_data, pos + 4)[0]
            compressed_size   = struct.unpack_from("<I", toc_data, pos + 8)[0]
            uncompressed_size = struct.unpack_from("<I", toc_data, pos + 12)[0]
            is_compressed     = toc_data[pos + 16]
            type_code         = toc_data[pos + 17:pos + 18]

            # Name is null-terminated, starts at pos+18
            name_start = pos + 18
            name_end   = toc_data.find(b"\x00", name_start)
            if name_end == -1 or name_end > pos + entry_len:
                name_end = pos + entry_len
            name = toc_data[name_start:name_end].decode("utf-8", errors="replace")

            entries.append({
                "name":             name,
                "type_code":        type_code,
                "type_name":        CARCHIVE_TYPES.get(type_code, "unknown"),
                "offset":           archive_start + data_offset,
                "compressed_size":  compressed_size,
                "uncompressed_size": uncompressed_size,
                "is_compressed":    bool(is_compressed),
            })

            if entry_len < 19:
                # Safety: minimum possible entry is 18 header + 1 null byte
                break
            pos += entry_len

        except Exception:
            break

    return entries


def extract_pyz_from_exe(exe_data: bytes,
                          entries: list[dict]) -> Optional[bytes]:
    """
    Find the PYZ archive entry in the CArchive TOC and extract its bytes.
    The PYZ entry has type code 'z' or name ending in '.pyz'.
    """
    pyz_entry = None
    for e in entries:
        if e["type_code"] == b'z' or e["name"].endswith(".pyz"):
            pyz_entry = e
            break

    if pyz_entry is None:
        return None

    offset = pyz_entry["offset"]
    size   = pyz_entry["compressed_size"]
    chunk  = exe_data[offset: offset + size]

    if pyz_entry["is_compressed"]:
        try:
            return zlib.decompress(chunk)
        except Exception:
            return chunk   # return raw if decompress fails
    return chunk


# ═══════════════════════════════════════════════════════════════════════════
#  PYZ MODULE NAME EXTRACTOR
#
#  The PYZ archive (ZlibArchive) contains a TOC of module names + their
#  compressed .pyc bytecode. We extract the name list without decompressing
#  every module.
#
#  ZlibArchive format:
#    16 bytes: magic "ZlibArchive \x00\x00\x00\x01"
#    4 bytes:  TOC length
#    N bytes:  zlib-compressed TOC (marshal'd list of tuples)
#    ... compressed module bytecodes ...
# ═══════════════════════════════════════════════════════════════════════════

ZLIB_ARCHIVE_MAGIC = b"ZlibArchive \x00\x00\x00\x01"


def _read_pyz_names_from_bytes(pyz_data: bytes) -> Optional[set[str]]:
    """
    Extract module names from raw PYZ (ZlibArchive) bytes.
    Returns set of module name strings, or None on failure.
    """
    if not pyz_data.startswith(ZLIB_ARCHIVE_MAGIC):
        return None

    try:
        import marshal
        pos = len(ZLIB_ARCHIVE_MAGIC)
        toc_len = struct.unpack(">I", pyz_data[pos:pos + 4])[0]
        pos += 4
        toc_compressed = pyz_data[pos:pos + toc_len]
        toc_raw = zlib.decompress(toc_compressed)
        toc = marshal.loads(toc_raw)

        names = set()
        for entry in toc:
            if isinstance(entry, (list, tuple)) and len(entry) >= 1:
                name = entry[0]
                if isinstance(name, str):
                    names.add(name)
        return names if names else None
    except Exception:
        return None


def _read_pyz_names_string_search(pyz_data: bytes) -> set[str]:
    """
    Fallback: scan PYZ bytes for dotted module name patterns.
    Catches cases where marshal format changes between Python versions.
    """
    import re
    names = set()

    # Search for null-terminated strings matching module name patterns
    matches = re.findall(rb'([a-zA-Z_][a-zA-Z0-9_.]{2,80})\x00', pyz_data)
    for m in matches:
        try:
            s = m.decode("ascii")
            # Accept dotted module paths and known package roots
            if ("." in s and not s.startswith(".") and not s.endswith(".")) or \
               s in ("pygame", "pythonosc", "tkinter", "tomllib"):
                names.add(s)
        except Exception:
            pass

    return names


def get_all_module_names_from_exe(exe_data: bytes) -> tuple[set[str], list[dict], str]:
    """
    Extract the complete list of bundled Python module names from the EXE.

    Strategy:
      1. Parse the CArchive TOC from the EXE footer
      2. Find the PYZ entry in the TOC
      3. Read the PYZ TOC to get all module names
      4. Fall back to string search if structured reads fail

    Returns:
        (module_names, carchive_entries, status_message)
    """
    entries, status = parse_carchive_toc(exe_data)

    if not entries:
        # Last resort: raw byte search for module names in the whole EXE
        names = _read_pyz_names_string_search(exe_data)
        return names, [], f"CArchive parse failed — used raw byte search. {status}"

    # Try to get PYZ data and read its TOC
    pyz_data = extract_pyz_from_exe(exe_data, entries)
    if pyz_data:
        names = _read_pyz_names_from_bytes(pyz_data)
        if names:
            return names, entries, status + " (PYZ TOC parsed)"

        # Structured PYZ read failed — try string search on the PYZ bytes
        names = _read_pyz_names_string_search(pyz_data)
        if names:
            return names, entries, status + " (PYZ string search)"

    # PYZ extraction failed — try string search on whole EXE
    names = _read_pyz_names_string_search(exe_data)
    return names, entries, status + " (whole-EXE string search fallback)"


# ═══════════════════════════════════════════════════════════════════════════
#  CHECK 1 — EXE FILE + BASIC SANITY
# ═══════════════════════════════════════════════════════════════════════════

def check_exe_file() -> bool:
    header("EXE File Existence + Sanity")

    if not EXE_PATH.exists():
        R.fail(
            f"EXE not found: {EXE_PATH}",
            "Run 'python build.py' first."
        )
        R.end_section()
        return False

    stat  = EXE_PATH.stat()
    size  = stat.st_size
    mtime = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_mtime))
    R.ok(f"EXE found: {EXE_PATH.name}", f"{fmt_size(size)}, built {mtime}")

    # PyInstaller 6.20 onedir with embedded PYZ:
    # The stub + embedded PYZ + PKG is 2-8 MB. This is CORRECT.
    # The total app size (stub + _internal/) is 30-120 MB.
    if size < 1_000_000:
        R.fail(
            f"EXE is suspiciously small: {fmt_size(size)}",
            "Expected 2-8 MB for PyInstaller 6.20 onedir EXE with embedded PYZ. "
            "Build may not have completed."
        )
    elif size <= 8_000_000:
        R.ok(
            f"EXE size correct for PyInstaller 6.20 onedir: {fmt_size(size)}",
            "PYZ + PKG archives are embedded inside the EXE stub — this is normal."
        )
    elif size <= 30_000_000:
        R.warn(
            f"EXE is larger than typical: {fmt_size(size)}",
            "PyInstaller 6.20 onedir EXE stubs are usually 2-8 MB. "
            "Large EXE may indicate accidental --onefile mode or extra embedded data."
        )
    else:
        R.warn(
            f"EXE is very large: {fmt_size(size)}",
            "This looks like a --onefile build (all payload in the EXE). "
            "FX Machine is configured for --onedir. Check FX_Machine.spec."
        )

    # Windows PE header
    try:
        first_two = EXE_PATH.read_bytes()[:2]
        if first_two == b"MZ":
            R.ok("Valid Windows PE header (MZ magic bytes)")
        else:
            R.fail(
                "Invalid PE header",
                f"First 2 bytes: {first_two!r}, expected b'MZ'."
            )
    except Exception as e:
        R.warn("Could not read EXE header", str(e))

    R.end_section()
    return True


# ═══════════════════════════════════════════════════════════════════════════
#  CHECK 2 — _internal/ FOLDER
# ═══════════════════════════════════════════════════════════════════════════

def check_internal_folder() -> bool:
    header("_internal/ Folder (DLLs + C extensions)")

    if not INTERNAL.exists():
        R.fail(
            "_internal/ folder not found",
            f"Expected at: {INTERNAL}\n"
            "      This folder contains all DLLs and .pyd C extensions.\n"
            "      Python modules (.pyc) are embedded in the EXE itself in PyInstaller 6.20."
        )
        R.end_section()
        return False

    all_files   = walk(INTERNAL)
    total_bytes = sum(f.stat().st_size for f in all_files)
    dll_count   = sum(1 for f in all_files if f.suffix.lower() in (".dll", ".pyd"))

    R.ok(
        f"_internal/ exists",
        f"{len(all_files)} files, {fmt_size(total_bytes)}, {dll_count} DLL/PYD"
    )

    # In PyInstaller 6.20 onedir with embedded PYZ:
    # _internal/ contains ONLY DLLs, .pyd files, and base_library.zip
    # It does NOT contain PYZ-00.pyz or FX_Machine.pkg (those are in the EXE)
    # Expected size: 20-60 MB (mostly SDL2, pygame DLLs, Python DLL)
    if total_bytes < 5 * 1024 * 1024:
        R.fail(
            f"_internal/ is suspiciously small: {fmt_size(total_bytes)}",
            "Expected 20-60 MB of DLLs and C extensions."
        )
    elif total_bytes < 15 * 1024 * 1024:
        R.warn(
            f"_internal/ is smaller than expected: {fmt_size(total_bytes)}",
            "Expected 20-60 MB. Some DLLs may be missing."
        )
    else:
        R.ok(
            f"_internal/ size is plausible: {fmt_size(total_bytes)}",
            "Contains DLLs and C extensions (Python modules are in the EXE)"
        )

    # base_library.zip must exist — contains compressed stdlib
    blz = INTERNAL / "base_library.zip"
    if blz.exists():
        R.ok(f"base_library.zip  ({fmt_size(blz.stat().st_size)})",
             "Compressed stdlib (io, os, threading, etc.)")
    else:
        R.fail(
            "base_library.zip missing from _internal/",
            "stdlib modules (io, os, threading) won't be available at runtime."
        )

    # Note: PYZ and PKG are NOT expected here in PyInstaller 6.20
    R.info(
        "Note: PYZ-00.pyz and FX_Machine.pkg are embedded in the EXE stub "
        "in PyInstaller 6.20 — they are NOT separate files in _internal/. "
        "This is correct."
    )

    R.end_section()
    return True


# ═══════════════════════════════════════════════════════════════════════════
#  CHECK 3 — FOLDER STRUCTURE OVERVIEW
# ═══════════════════════════════════════════════════════════════════════════

def check_folder_structure():
    header("Output Folder Structure")

    all_files   = walk(DIST_DIR)
    total_bytes = sum(f.stat().st_size for f in all_files)
    R.info(
        f"Total dist folder: {fmt_size(total_bytes)} "
        f"across {len(all_files)} files"
    )

    required = [
        (DIST_DIR / EXE_PATH.name, "EXE launcher + embedded PYZ archive"),
        (DIST_DIR / "_internal",   "DLLs and C extension folder"),
        (DIST_DIR / "config",      "Config files (default.toml, EXAMPLES, README)"),
    ]

    for path, desc in required:
        if path.exists():
            if path.is_dir():
                fc = sum(1 for _ in path.rglob("*") if _.is_file())
                R.ok(f"{path.name}/  ({fc} files)", desc)
            else:
                R.ok(f"{path.name}  ({fmt_size(path.stat().st_size)})", desc)
        else:
            R.fail(f"Missing: {path.name}", desc)

    R.end_section()


# ═══════════════════════════════════════════════════════════════════════════
#  CHECK 4 — CONFIG FILES
# ═══════════════════════════════════════════════════════════════════════════

def check_config_files():
    header("Config Files in Output Folder")

    required = [
        ("default.toml",  1_000, "Factory template — needed for first-run seeding"),
        ("EXAMPLES.toml", 500,   "Preset snippets for end users"),
        ("README.md",     200,   "Config explainer for end users"),
    ]

    for fname, min_bytes, desc in required:
        p = CFG_DIR / fname
        if not p.exists():
            R.fail(f"config/{fname} missing", desc)
        else:
            size = p.stat().st_size
            if size < min_bytes:
                R.warn(
                    f"config/{fname} very small ({size} bytes)",
                    f"Expected at least {min_bytes} bytes. May be truncated."
                )
            else:
                R.ok(f"config/{fname}  ({fmt_size(size)})", desc)

    active = CFG_DIR / "active.toml"
    if active.exists():
        R.warn(
            "config/active.toml present in output folder",
            "User-specific file. It is regenerated on first launch. "
            "Safe to ship but not intended — consider removing before zipping."
        )
    else:
        R.ok("config/active.toml absent (correct — auto-created on first launch)")

    R.end_section()


# ═══════════════════════════════════════════════════════════════════════════
#  CHECK 5 — CONFIG FILE CONTENT SIGNATURES
# ═══════════════════════════════════════════════════════════════════════════

def check_config_content():
    header("Config File Content Signatures")

    checks = [
        ("default.toml",  "[eq.encoder]",      "EQ encoder section"),
        ("default.toml",  "[eq.flick]",         "EQ flick gesture section"),
        ("default.toml",  "[trim]",             "TRIM section (Build B)"),
        ("default.toml",  "[fx]",               "FX section"),
        ("default.toml",  "[meter]",            "Meter section"),
        ("default.toml",  "[network]",          "Network section"),
        ("default.toml",  "sweep_seconds",      "Encoder sweep key"),
        ("EXAMPLES.toml", "PUNCHY CLUB",        "Punchy Club preset"),
        ("EXAMPLES.toml", "STUDIO PRECISE",     "Studio Precise preset"),
        ("EXAMPLES.toml", "BEGINNER FORGIVING", "Beginner preset"),
        ("README.md",     "active.toml",        "active.toml reference"),
        ("README.md",     "FX Machine",         "Project name in README"),
    ]

    for fname, needle, desc in checks:
        p = CFG_DIR / fname
        if not p.exists():
            R.fail(f"Cannot check config/{fname} — file missing", "")
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
            if needle in text:
                R.ok(f"config/{fname} ← '{needle}'", desc)
            else:
                R.fail(
                    f"config/{fname} missing expected text: '{needle}'",
                    f"{desc}. File may be the wrong version or corrupted."
                )
        except Exception as e:
            R.fail(f"Cannot read config/{fname}", str(e))

    R.end_section()


# ═══════════════════════════════════════════════════════════════════════════
#  CHECK 6 — EXE EMBEDDED ARCHIVE (CArchive + PYZ module inventory)
#
#  This is the correct check for PyInstaller 6.20 onedir.
#  The modules are embedded in the EXE, not in separate files.
# ═══════════════════════════════════════════════════════════════════════════

# Shared cache so we only read + parse the EXE once
_exe_data:       Optional[bytes]     = None
_carchive_toc:   Optional[list]      = None
_module_names:   Optional[set[str]]  = None
_archive_status: str                 = ""


def _load_exe_archives():
    """Read the EXE and parse its embedded archives (cached)."""
    global _exe_data, _carchive_toc, _module_names, _archive_status

    if _exe_data is not None:
        return  # already loaded

    try:
        _exe_data = EXE_PATH.read_bytes()
    except Exception as e:
        _archive_status = f"Cannot read EXE: {e}"
        _exe_data = b""
        _carchive_toc = []
        _module_names = set()
        return

    _module_names, _carchive_toc, _archive_status = \
        get_all_module_names_from_exe(_exe_data)


def check_embedded_archive():
    header("EXE Embedded Archive (CArchive + PYZ Module Inventory)")

    if QUICK:
        R.info("Skipped (--quick mode)")
        R.end_section()
        return

    _load_exe_archives()

    if not _exe_data:
        R.fail("Could not read EXE binary", _archive_status)
        R.end_section()
        return

    R.info(f"Archive parse: {_archive_status}")

    # ── CArchive TOC entries ─────────────────────────────────────────────
    if _carchive_toc:
        type_counts: dict[str, int] = {}
        for e in _carchive_toc:
            tn = e["type_name"]
            type_counts[tn] = type_counts.get(tn, 0) + 1

        R.ok(
            f"CArchive TOC: {len(_carchive_toc)} entries",
            ", ".join(f"{v} {k}" for k, v in sorted(type_counts.items()))
        )

        # Check that a PYZ entry exists in the CArchive
        pyz_entries = [e for e in _carchive_toc
                       if e["type_code"] == b'z' or e["name"].endswith(".pyz")]
        if pyz_entries:
            pyz = pyz_entries[0]
            R.ok(
                f"PYZ archive entry found in CArchive: '{pyz['name']}'",
                f"{fmt_size(pyz['compressed_size'])} compressed"
            )
        else:
            R.warn(
                "No PYZ entry found in CArchive TOC",
                "Module bytecodes may be stored differently. "
                "Check if the app launches correctly."
            )

        if VERBOSE:
            print(f"\n  {C.DIM}CArchive TOC entries:{C.END}")
            for e in _carchive_toc:
                print(
                    f"    {C.DIM}{e['type_name']:15} "
                    f"{fmt_size(e['compressed_size']):>10}  "
                    f"{e['name']}{C.END}"
                )
    else:
        R.warn(
            "CArchive TOC could not be parsed",
            "May be a different PyInstaller version. "
            "Module check will use string search instead."
        )

    # ── Module inventory ─────────────────────────────────────────────────
    if not _module_names:
        R.fail(
            "No module names could be extracted from EXE",
            "Cannot verify bundled modules. "
            "If the app launches and runs, this check may be overly strict."
        )
        R.end_section()
        return

    total_mods = len(_module_names)
    src_mods   = sorted(n for n in _module_names if n.startswith("src."))
    R.ok(
        f"Module name list extracted: {total_mods} total",
        f"{len(src_mods)} src.* modules"
    )

    if VERBOSE and src_mods:
        R.info(f"src.* modules found ({len(src_mods)}):")
        for name in src_mods:
            print(f"    {C.DIM}{name}{C.END}")

    # ── FX Machine modules ───────────────────────────────────────────────
    fx_modules = [
        ("src.config",              "Architectural constants"),
        ("src.config_loader",       "TOML loader + cfg singleton"),
        ("src.state",               "Shared state + thread locks"),
        ("src.helpers",             "Utility functions"),
        ("src.main",                "Application entry point"),
        ("src.log_setup",           "Logging configuration"),
        ("src.osc.client",          "OSC send functions"),
        ("src.osc.server",          "OSC receive handlers"),
        ("src.osc.discovery",       "Session discovery"),
        ("src.engine.eq",           "EQ mode engine"),
        ("src.engine.fx",           "FX macro driver"),
        ("src.engine.polling",      "Polling + EQ ramp"),
        ("src.engine.navigation",   "Navigation"),
        ("src.engine.actions",      "Discrete actions"),
        ("src.engine.momentary",    "Momentary FX"),
        ("src.controller.loop",     "Controller thread"),
        ("src.controller.buttons",  "Button handlers"),
        ("src.controller.axes",     "Axis handlers"),
        ("src.controller.watchdog", "Watchdog"),
        ("src.ui.palette",          "Colors + fonts"),
        ("src.ui.widgets",          "Canvas renderers"),
        ("src.ui.builder",          "Tkinter UI construction"),
        ("src.ui.updater",          "UI update loop"),
    ]

    missing_fx = []
    for mod, desc in fx_modules:
        if mod in _module_names:
            R.ok(f"{mod}", desc)
        else:
            # Fuzzy match: PYZ may store with different separators
            if any(mod.replace(".", "/") in n or mod in n
                   for n in _module_names):
                R.ok(f"{mod} (fuzzy match)", desc)
            else:
                R.fail(f"NOT bundled: {mod}", desc)
                missing_fx.append(mod)

    if missing_fx:
        R.fail(
            f"{len(missing_fx)} FX Machine module(s) missing from bundle",
            "Ensure run.py imports src.main so PyInstaller can trace all deps.\n"
            "      Also check for 'excludes' in FX_Machine.spec."
        )
    else:
        R.ok(f"All {len(fx_modules)} FX Machine modules confirmed in bundle")

    # ── Third-party packages ─────────────────────────────────────────────
    packages = [
        ("pygame",    "Gamepad input"),
        ("pythonosc", "OSC communication"),
        ("tkinter",   "UI toolkit"),
        ("tomllib",   "TOML parser (stdlib 3.11+)"),
    ]

    for pkg, desc in packages:
        in_pyz = any(
            n == pkg or n.startswith(pkg + ".") or n.startswith(pkg + "/")
            for n in _module_names
        )
        if in_pyz:
            count = sum(
                1 for n in _module_names
                if n == pkg or n.startswith(pkg + ".") or n.startswith(pkg + "/")
            )
            R.ok(f"{pkg}  ({count} sub-modules)", desc)
        else:
            # pygame ships as C extensions (.pyd) in _internal/ — not as .pyc in PYZ
            pyd_found = find_in_tree(INTERNAL, f"{pkg}*")
            dir_found = (INTERNAL / pkg).is_dir()
            if pyd_found or dir_found:
                R.ok(
                    f"{pkg} found as C extension in _internal/ "
                    f"(not in PYZ — correct for C extensions)",
                    desc
                )
            else:
                R.fail(
                    f"{pkg} not found anywhere in bundle",
                    f"{desc}. Not in PYZ and not in _internal/ as a .pyd or folder."
                )

    R.end_section()


# ═══════════════════════════════════════════════════════════════════════════
#  CHECK 7 — REQUIRED DLLs + SHARED LIBRARIES
# ═══════════════════════════════════════════════════════════════════════════

def check_dlls():
    header("Required DLLs + Shared Libraries in _internal/")

    dll_checks = [
        # (pattern, required, description)
        ("python3*.dll",    True,  "Python runtime DLL"),
        ("SDL2.dll",        True,  "pygame SDL2 core"),
        ("_tkinter*.pyd",   True,  "Tkinter C extension"),
        ("tcl*.dll",        True,  "Tcl runtime (required by Tkinter)"),
        ("tk*.dll",         True,  "Tk runtime (required by Tkinter)"),
        ("base_library.zip",True,  "Compressed stdlib archive"),
        ("SDL2_mixer.dll",  False, "pygame audio (optional)"),
        ("SDL2_image.dll",  False, "pygame image loading (optional)"),
        ("freetype.dll",    False, "Font rendering (optional)"),
        ("VCRUNTIME*.dll",  False, "Visual C++ runtime"),
        ("libffi*.dll",     False, "ctypes FFI"),
    ]

    for pattern, required, desc in dll_checks:
        found = find_in_tree(INTERNAL, pattern) + find_in_tree(DIST_DIR, pattern)
        # Deduplicate by filename
        seen: dict[str, Path] = {}
        for f in found:
            seen[f.name] = f
        unique = list(seen.values())

        if unique:
            names = [f.name for f in unique]
            detail = names[0]
            if len(names) > 1:
                detail += f" (+{len(names)-1} more)"
            R.ok(f"{pattern} → {detail}", desc)
        else:
            if required:
                R.fail(f"Required DLL/PYD missing: {pattern}", desc)
            else:
                if VERBOSE:
                    R.info(f"Optional not found: {pattern} ({desc})")

    R.end_section()


# ═══════════════════════════════════════════════════════════════════════════
#  CHECK 8 — EXE STUB BINARY MARKERS
# ═══════════════════════════════════════════════════════════════════════════

def check_binary_markers():
    """
    Verify key binary markers in the EXE stub.
    Unlike the previous inspector, we now know the correct expectations:
      - MEI magic: YES (CArchive marker)
      - _internal: YES (the EXE references its sibling folder)
      - src.config: YES (module names are in the embedded CArchive TOC)
      - PYZ-00.pyz: MAYBE (may be stored as a different internal name)
      - sweep_seconds: NO (config content is in config/ folder, not EXE)
    """
    if QUICK:
        return

    header("EXE Stub Binary Markers")

    _load_exe_archives()

    if not _exe_data:
        R.fail("Cannot read EXE binary", "")
        R.end_section()
        return

    data = _exe_data

    checks = [
        # (needle, expected_present, description)
        (b"MZ",                      True,  "Windows PE header"),
        (CARCHIVE_MAGIC,             True,  "PyInstaller CArchive magic (MEI marker)"),
        (b"_internal",               True,  "Reference to _internal/ sibling folder"),
        (b"python3",                 True,  "Python version reference"),
        (b"src.config",              True,  "src.config in embedded module table"),
        (b"src.engine",              True,  "src.engine in embedded module table"),
        (b"pygame",                  True,  "pygame reference in module table"),
        # These should NOT be in the EXE (they live in config/ folder)
        (b"sweep_seconds",           False, "Config key (should be in config/ not EXE)"),
        (b"PUNCHY CLUB",             False, "EXAMPLES.toml content (should be in config/)"),
    ]

    for needle, expected, desc in checks:
        found = needle in data
        if found and expected:
            R.ok(f"Found: {needle!r}", desc)
        elif not found and not expected:
            R.ok(f"Absent (correct): {needle!r}", desc)
        elif found and not expected:
            R.info(
                f"{needle!r} found in EXE (unexpected — {desc})"
            )
        else:
            # not found but expected
            R.fail(
                f"NOT found in EXE: {needle!r}",
                f"{desc}. EXE may be incomplete or wrong format."
            )

    R.end_section()


# ═══════════════════════════════════════════════════════════════════════════
#  CHECK 9 — TOML VALIDITY
# ═══════════════════════════════════════════════════════════════════════════

def check_toml_validity():
    header("Shipped TOML File Validity")

    try:
        import tomllib
    except ImportError:
        R.warn(
            "tomllib not available (need Python 3.11+)",
            "Cannot parse-validate the shipped TOML files."
        )
        R.end_section()
        return

    for fname in ["default.toml", "EXAMPLES.toml"]:
        p = CFG_DIR / fname
        if not p.exists():
            R.fail(f"config/{fname} missing", "")
            continue
        try:
            with open(p, "rb") as f:
                data = tomllib.load(f)

            key_count = 0
            def _count(d):
                nonlocal key_count
                for v in d.values():
                    key_count += 1
                    if isinstance(v, dict):
                        _count(v)
            _count(data)
            R.ok(f"config/{fname} — valid TOML", f"{key_count} keys parsed")
        except Exception as e:
            R.fail(
                f"config/{fname} — TOML parse error",
                f"{type(e).__name__}: {e}"
            )

    R.end_section()


# ═══════════════════════════════════════════════════════════════════════════
#  CHECK 10 — RUNTIME IMPORT SIMULATION
# ═══════════════════════════════════════════════════════════════════════════

def check_runtime_simulation():
    header("Runtime Import Simulation (project source as bundle proxy)")

    R.info(
        "Imports from project source. Failures here indicate the same "
        "modules will fail inside the bundle."
    )

    modules = [
        "src.config",
        "src.config_loader",
        "src.state",
        "src.helpers",
        "src.osc.server",
        "src.engine.eq",
        "src.engine.fx",
        "src.engine.polling",
        "src.ui.palette",
        "src.ui.widgets",
    ]

    passed = 0
    for mod_name in modules:
        try:
            if mod_name in sys.modules:
                del sys.modules[mod_name]
            importlib.import_module(mod_name)
            R.ok(f"import {mod_name}")
            passed += 1
        except ImportError as e:
            err = str(e).lower()
            if any(kw in err for kw in ("display", "tkinter", "_tkinter")):
                R.warn(
                    f"import {mod_name} — headless environment",
                    "Normal on CI/SSH without DISPLAY. Not a bundle problem."
                )
            else:
                R.fail(f"import {mod_name}", f"{type(e).__name__}: {e}")
        except Exception as e:
            R.fail(f"import {mod_name}", f"{type(e).__name__}: {e}")

    R.end_section()


# ═══════════════════════════════════════════════════════════════════════════
#  CHECK 11 — FULL MANIFEST (verbose only)
# ═══════════════════════════════════════════════════════════════════════════

def print_full_manifest():
    if not VERBOSE:
        return

    header("Full File Manifest")

    all_files   = walk(DIST_DIR)
    total_bytes = sum(f.stat().st_size for f in all_files)

    groups: dict[str, list[Path]] = {}
    for f in all_files:
        rel = f.relative_to(DIST_DIR)
        top = rel.parts[0] if len(rel.parts) > 1 else "(root)"
        groups.setdefault(top, []).append(f)

    for gname in sorted(groups):
        files      = groups[gname]
        gsize      = sum(f.stat().st_size for f in files)
        print(
            f"\n  {C.BOLD}{gname}/{C.END}  "
            f"{C.DIM}({len(files)} files, {fmt_size(gsize)}){C.END}"
        )
        for f in sorted(files, key=lambda x: -x.stat().st_size)[:20]:
            rel = f.relative_to(DIST_DIR)
            print(f"    {C.DIM}{fmt_size(f.stat().st_size):>10}{C.END}  {rel}")
        if len(files) > 20:
            print(f"    {C.DIM}... and {len(files) - 20} more{C.END}")

    print(f"\n  {C.BOLD}Grand total: {fmt_size(total_bytes)} "
          f"in {len(all_files)} files{C.END}")

    R.end_section()


# ═══════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main():
    start = time.time()

    print(f"\n{C.BOLD}{C.INFO}╔{'═' * 62}╗{C.END}")
    print(f"{C.BOLD}{C.INFO}║{' ' * 6}FX MACHINE — EXE BUNDLE INSPECTOR (v3){' ' * 17}║{C.END}")
    print(f"{C.BOLD}{C.INFO}╚{'═' * 62}╝{C.END}")
    print(f"\n  {C.DIM}Target  : {EXE_PATH}{C.END}")
    print(f"  {C.DIM}Layout  : PyInstaller 6.20 onedir "
          f"(PYZ embedded in EXE, DLLs in _internal/){C.END}")

    if QUICK:
        print(f"  {C.DIM}Mode    : Quick (archive parsing skipped){C.END}")
    if VERBOSE:
        print(f"  {C.DIM}Mode    : Verbose (all checks + full manifest){C.END}")

    # EXE must exist
    if not check_exe_file():
        print(f"\n{C.FAIL}{C.BOLD}❌  EXE NOT FOUND — run: python build.py{C.END}\n")
        sys.exit(2)

    internal_ok = check_internal_folder()
    check_folder_structure()
    check_config_files()
    check_config_content()
    check_embedded_archive()   # skipped with --quick
    if internal_ok:
        check_dlls()
    check_binary_markers()     # skipped with --quick
    check_toml_validity()
    check_runtime_simulation()
    print_full_manifest()      # verbose only

    elapsed = time.time() - start

    print(f"\n{C.BOLD}{'━' * 64}{C.END}")
    print(f"{C.BOLD}SUMMARY{C.END}  ({elapsed:.1f}s)")
    print(f"  Total checks : {R.checks}")
    print(f"  {C.OK}Passed{C.END}       : {R.passed}")
    print(f"  {C.WARN}Warnings{C.END}     : {R.warned}")
    print(f"  {C.FAIL}Failed{C.END}       : {R.failed}")
    print(f"{C.BOLD}{'━' * 64}{C.END}")

    if R.failed > 0:
        print(
            f"\n{C.FAIL}{C.BOLD}"
            f"❌  {R.failed} ERROR(S) — DO NOT SHIP THIS BUILD"
            f"{C.END}"
        )
        print(f"\n{C.FAIL}Failing checks:{C.END}")
        for e in R.errors:
            print(f"  • {e}")
        print(
            f"\n{C.DIM}Fix the issues above, then: "
            f"python build.py && python inspect_exe.py{C.END}\n"
        )
        sys.exit(2)

    elif R.warned > 0:
        print(
            f"\n{C.WARN}⚠   {R.warned} WARNING(S) — review before shipping{C.END}"
        )
        for w in R.warns:
            print(f"  • {w}")
        sys.exit(1)

    else:
        print(
            f"\n{C.OK}{C.BOLD}✅  ALL CHECKS PASSED — BUILD IS GOOD TO SHIP{C.END}"
        )
        print(
            f"\n{C.DIM}  Next: launch {EXE_PATH.name} and verify "
            f"the UI opens and Ableton connects.{C.END}\n"
        )
        sys.exit(0)


if __name__ == "__main__":
    main()