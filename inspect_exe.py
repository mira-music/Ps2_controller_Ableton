#!/usr/bin/env python3
"""
================================================================================
  inspect_exe.py — FX Machine Build Inspector
================================================================================
  Verifies that a built FX Machine bundle is complete and correct.
  Detects which build profile was used and verifies all expected components.

  Designed for PyInstaller 6.x onedir layout (the PYZ archive is embedded
  inside the EXE stub itself, not a separate file in _internal/).

  Usage:
      python inspect_exe.py                       # full check, with pause
      python inspect_exe.py --exe PATH            # inspect a specific .exe
      python inspect_exe.py --no-pause            # skip "press key" at end
      python inspect_exe.py --quiet               # suppress passed checks
      python inspect_exe.py --strict              # treat warnings as errors
      python inspect_exe.py --json                # machine-readable output

  Critical fix in this version:
      CArchive footer parsing was using little-endian uint64 fields.
      The actual PyInstaller format uses big-endian uint32 fields.
      Previously this caused garbage values (e.g. "archive 1697 MB,
      Python 939589632") and false-negative module checks reporting
      all bundled src.* modules as missing.

  Exit codes:
      0 = all checks passed
      1 = warnings only (still safe to ship)
      2 = errors found (DO NOT SHIP)

  PyInstaller 6.20 onedir layout (verified):
      dist/FX_Machine/
      ├── FX_Machine.exe          ← stub + embedded PYZ + PKG (~3-5 MB)
      ├── Analyze_Session.exe     ← optional (STANDARD/FULL profile)
      ├── _internal/              ← DLLs and C extensions only
      │   ├── base_library.zip    ← compressed stdlib
      │   ├── python312.dll
      │   ├── SDL2.dll
      │   ├── _tkinter.pyd
      │   ├── tcl86t.dll
      │   ├── tk86t.dll
      │   └── ... (other support files)
      ├── config/                 ← always present
      │   ├── default.toml
      │   ├── EXAMPLES.toml
      │   ├── README.md
      │   └── presets/            ← optional
      ├── docs/                   ← optional (FULL/CUSTOM)
      └── README.md               ← optional (FULL/CUSTOM)

  CArchive footer format (88 bytes, big-endian):
      offset 0:  8 bytes  MEI magic (4d 45 49 0c 0b 0a 0b 0e)
      offset 8:  4 bytes  archive total length (uint32 BE)
      offset 12: 4 bytes  TOC offset within archive (uint32 BE)
      offset 16: 4 bytes  TOC size in bytes (uint32 BE)
      offset 20: 4 bytes  Python version (e.g. 312 = 3.12) (uint32 BE)
      offset 24: 64 bytes Python library DLL name, null-padded ASCII

  TOC entry format (variable length, big-endian):
      offset 0:  4 bytes  entry length including this field (uint32 BE)
      offset 4:  4 bytes  data offset from archive start (uint32 BE)
      offset 8:  4 bytes  compressed data size (uint32 BE)
      offset 12: 4 bytes  uncompressed data size (uint32 BE)
      offset 16: 1 byte   is_compressed flag
      offset 17: 1 byte   type code (ASCII)
      offset 18+:         null-terminated name string
================================================================================
"""

import sys
import os
import struct
import zlib
import json
import argparse
import time
import marshal
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
#  RESULTS TRACKING
# ═══════════════════════════════════════════════════════════════════════════

class Results:
    """Tracks all check results with section grouping."""

    def __init__(self, quiet: bool = False):
        self.checks = 0
        self.passed = 0
        self.warned = 0
        self.failed = 0
        self.errors: list[str] = []
        self.warns: list[str] = []
        self._section_p = 0
        self._section_w = 0
        self._section_f = 0
        self.quiet = quiet
        self.detected_profile = "UNKNOWN"

    def ok(self, label: str, detail: str = ""):
        self.checks += 1
        self.passed += 1
        if not self.quiet:
            msg = f"  {C.OK}✓{C.END} {label}"
            if detail:
                msg += f"  {C.DIM}({detail}){C.END}"
            print(msg)

    def warn(self, label: str, detail: str = ""):
        self.checks += 1
        self.warned += 1
        msg = f"  {C.WARN}⚠{C.END} {label}"
        if detail:
            msg += f"\n      {C.DIM}{detail}{C.END}"
        print(msg)
        self.warns.append(label)

    def fail(self, label: str, detail: str = ""):
        self.checks += 1
        self.failed += 1
        msg = f"  {C.FAIL}✗{C.END} {label}"
        if detail:
            msg += f"\n      {C.DIM}{detail}{C.END}"
        print(msg)
        self.errors.append(label)

    def info(self, msg: str):
        print(f"  {C.INFO}ℹ{C.END} {msg}")

    def begin_section(self, title: str):
        print(f"\n{C.BOLD}{C.INFO}━━━ {title} ━━━{C.END}")
        self._section_p = self.passed
        self._section_w = self.warned
        self._section_f = self.failed

    def end_section(self):
        if self.quiet:
            return
        np = self.passed - self._section_p
        nw = self.warned - self._section_w
        nf = self.failed - self._section_f
        if nw == 0 and nf == 0 and np > 0:
            print(f"  {C.OK}✓{C.END} {np} check(s) passed")


# ═══════════════════════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════════════════════

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
#  PyInstaller embeds a CArchive at the end of the EXE binary. The footer
#  identifies its location and structure. The TOC inside the archive lists
#  every bundled file, including the PYZ (Python module archive).
#
#  CRITICAL: All multi-byte integer fields are BIG-ENDIAN (network byte
#  order), and 4 bytes wide. NOT little-endian and NOT 8 bytes. This was
#  the source of the inspector's previous false-negative reports.
# ═══════════════════════════════════════════════════════════════════════════

CARCHIVE_MAGIC = b"MEI\014\013\012\013\016"

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


def find_carchive_footer(data: bytes) -> Optional[int]:
    """Search backward for CARCHIVE_MAGIC. Returns offset or None."""
    # Search in the last 8 KB — the footer is always at the very end of the EXE
    search_window = data[-8192:]
    idx = search_window.rfind(CARCHIVE_MAGIC)
    if idx == -1:
        return None
    return len(data) - len(search_window) + idx


def parse_carchive_toc(exe_data: bytes) -> tuple[list[dict], str]:
    """
    Parse the CArchive footer + TOC from the EXE.
    Returns (entries, status_message).

    The footer is 88 bytes total:
      8  bytes  MEI magic
      4  bytes  archive_len (uint32 big-endian)
      4  bytes  toc_offset within archive (uint32 big-endian)
      4  bytes  toc_size (uint32 big-endian)
      4  bytes  python_version (uint32 big-endian, e.g. 312 = 3.12)
      64 bytes  python lib DLL name (null-padded ASCII)
    """
    magic_offset = find_carchive_footer(exe_data)
    if magic_offset is None:
        return [], "CArchive magic not found (not a PyInstaller binary?)"

    try:
        footer = exe_data[magic_offset:]
        pos = 8   # skip magic

        # All fields are uint32 BIG-ENDIAN
        archive_len = struct.unpack_from(">I", footer, pos)[0]
        pos += 4
        toc_offset = struct.unpack_from(">I", footer, pos)[0]
        pos += 4
        toc_size = struct.unpack_from(">I", footer, pos)[0]
        pos += 4
        py_ver = struct.unpack_from(">I", footer, pos)[0]
        pos += 4

        # Remainder is the Python library name (null-padded to 64 bytes)
        pylib_raw = footer[pos:pos + 64]
        pylib_name = pylib_raw.split(b"\x00")[0].decode("utf-8", errors="replace")

        # Sanity check the archive length
        if archive_len == 0 or archive_len > len(exe_data):
            raise ValueError(
                f"Implausible archive_len: {archive_len} "
                f"(EXE size: {len(exe_data)})"
            )

        # Archive starts at: total_size - archive_len
        archive_start = len(exe_data) - archive_len

        # TOC starts at: archive_start + toc_offset
        toc_start = archive_start + toc_offset
        toc_end = toc_start + toc_size

        if toc_end > len(exe_data):
            raise ValueError(
                f"TOC end ({toc_end}) exceeds EXE size ({len(exe_data)})"
            )

        toc_data = exe_data[toc_start:toc_end]

        entries = parse_toc_entries(toc_data, archive_start)

        # Format Python version for display (312 -> 3.12)
        if 300 <= py_ver <= 399:
            py_ver_str = f"{py_ver // 100}.{py_ver % 100}"
        else:
            py_ver_str = str(py_ver)

        status = (
            f"CArchive parsed — archive {fmt_size(archive_len)}, "
            f"Python {py_ver_str}, lib '{pylib_name}', "
            f"{len(entries)} TOC entries"
        )
        return entries, status

    except Exception as e:
        return [], f"Footer parse failed: {type(e).__name__}: {e}"


def parse_toc_entries(toc_data: bytes, archive_start: int) -> list[dict]:
    """
    Parse the TOC body. Each entry is variable-length, structured as:
      4 bytes  entry_length including this field (uint32 BIG-ENDIAN)
      4 bytes  data_offset from archive start (uint32 BIG-ENDIAN)
      4 bytes  compressed_size (uint32 BIG-ENDIAN)
      4 bytes  uncompressed_size (uint32 BIG-ENDIAN)
      1 byte   is_compressed flag
      1 byte   type code (ASCII)
      N bytes  null-terminated name string

    All multi-byte integers are big-endian.
    """
    entries = []
    pos = 0

    while pos < len(toc_data):
        # Need at least 18 bytes for the fixed-size header
        if pos + 18 > len(toc_data):
            break

        try:
            entry_len = struct.unpack_from(">I", toc_data, pos)[0]
            data_offset = struct.unpack_from(">I", toc_data, pos + 4)[0]
            compressed_size = struct.unpack_from(">I", toc_data, pos + 8)[0]
            uncompressed_size = struct.unpack_from(">I", toc_data, pos + 12)[0]
            is_compressed = toc_data[pos + 16]
            type_code = toc_data[pos + 17:pos + 18]

            # Name is null-terminated, starting at pos+18
            name_start = pos + 18
            name_end = toc_data.find(b"\x00", name_start)
            if name_end == -1 or name_end > pos + entry_len:
                name_end = pos + entry_len
            name = toc_data[name_start:name_end].decode("utf-8", errors="replace")

            entries.append({
                "name": name,
                "type_code": type_code,
                "type_name": CARCHIVE_TYPES.get(type_code, "unknown"),
                "offset": archive_start + data_offset,
                "compressed_size": compressed_size,
                "uncompressed_size": uncompressed_size,
                "is_compressed": bool(is_compressed),
            })

            # Sanity check — minimum entry size is 19 (18 header + 1 null)
            if entry_len < 19:
                break

            pos += entry_len

        except Exception:
            # Stop on first malformed entry
            break

    return entries


def extract_pyz_from_exe(exe_data: bytes, entries: list[dict]) -> Optional[bytes]:
    """Find the PYZ entry in the TOC and extract/decompress its bytes."""
    pyz_entry = None
    for e in entries:
        if e["type_code"] == b'z' or e["name"].endswith(".pyz"):
            pyz_entry = e
            break

    if pyz_entry is None:
        return None

    offset = pyz_entry["offset"]
    size = pyz_entry["compressed_size"]
    chunk = exe_data[offset:offset + size]

    if pyz_entry["is_compressed"]:
        try:
            return zlib.decompress(chunk)
        except Exception:
            # If decompression fails, return raw bytes — string-search may still work
            return chunk
    return chunk


# ═══════════════════════════════════════════════════════════════════════════
#  PYZ MODULE LIST EXTRACTOR
#
#  The PYZ archive is a ZlibArchive — magic + toc_length + zlib-compressed
#  marshal'd TOC + compressed module bytecode bodies.
# ═══════════════════════════════════════════════════════════════════════════

ZLIB_ARCHIVE_MAGIC = b"ZlibArchive \x00\x00\x00\x01"


def read_pyz_names_structured(pyz_data: bytes) -> Optional[set[str]]:
    """
    Read PYZ TOC for PyInstaller 6.20+ format.

    Format:
      Bytes 0-3:    "PYZ\x00" magic
      Bytes 4-7:    Python .pyc magic number
      Bytes 8-11:   TOC offset from PYZ start (uint32 big-endian)
      Bytes 12-15:  Reserved (zeros)
      Bytes 16...:  Compressed module .pyc blobs (individual zlib streams)
      Bytes TOC...: Raw marshal'd list of (name, (typ, offset, size)) tuples

    Also supports legacy ZlibArchive format (older PyInstaller versions)
    where the TOC is at the HEAD of the PYZ after a 16-byte magic header.
    """
    names = set()

    # ── Try new format: "PYZ\x00" magic ─────────────────────────────
    if pyz_data[:4] == b"PYZ\x00":
        try:
            # TOC offset is at bytes 8-11, uint32 big-endian
            toc_offset = struct.unpack_from(">I", pyz_data, 8)[0]

            if toc_offset >= len(pyz_data):
                return None

            # TOC is raw marshal data at the tail of the PYZ
            toc_blob = pyz_data[toc_offset:]
            toc = marshal.loads(toc_blob)

            if isinstance(toc, (list, tuple)):
                for entry in toc:
                    if isinstance(entry, (list, tuple)) and len(entry) >= 1:
                        name = entry[0]
                        if isinstance(name, str):
                            names.add(name)
            elif isinstance(toc, dict):
                for key in toc:
                    if isinstance(key, str):
                        names.add(key)

            return names if names else None
        except Exception:
            return None

    # ── Try legacy format: "ZlibArchive " magic ─────────────────────
    zlib_magic = b"ZlibArchive \x00\x00\x00\x01"
    if pyz_data[:16] == zlib_magic:
        try:
            pos = len(zlib_magic)
            toc_len = struct.unpack(">I", pyz_data[pos:pos + 4])[0]
            pos += 4
            toc_compressed = pyz_data[pos:pos + toc_len]
            toc_raw = zlib.decompress(toc_compressed)
            toc = marshal.loads(toc_raw)

            if isinstance(toc, (list, tuple)):
                for entry in toc:
                    if isinstance(entry, (list, tuple)) and len(entry) >= 1:
                        name = entry[0]
                        if isinstance(name, str):
                            names.add(name)
            elif isinstance(toc, dict):
                for key in toc:
                    if isinstance(key, str):
                        names.add(key)

            return names if names else None
        except Exception:
            return None

    return None
    """Read PYZ TOC using the ZlibArchive format. Returns module name set."""
    if not pyz_data.startswith(ZLIB_ARCHIVE_MAGIC):
        return None

    try:
        pos = len(ZLIB_ARCHIVE_MAGIC)
        # TOC length is uint32 BIG-ENDIAN (consistent with rest of PyInstaller format)
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


def read_pyz_names_string_search(pyz_data: bytes) -> set[str]:
    """
    Fallback: scan PYZ bytes for module name patterns.
    Used only if the structured marshal format can't be parsed
    (e.g. format changed in a future PyInstaller version).
    """
    import re
    names = set()
    matches = re.findall(rb'([a-zA-Z_][a-zA-Z0-9_.]{2,80})\x00', pyz_data)
    for m in matches:
        try:
            s = m.decode("ascii")
            if ("." in s and not s.startswith(".") and not s.endswith(".")) or \
               s in ("pygame", "pythonosc", "tkinter", "tomllib", "psutil"):
                names.add(s)
        except Exception:
            pass
    return names


def get_all_module_names_from_exe(exe_data: bytes) -> tuple[set[str], list[dict], str]:
    """
    Master function: extract all bundled module names from an EXE.
    Returns (module_names, carchive_entries, status_message).
    """
    entries, status = parse_carchive_toc(exe_data)

    if not entries:
        # CArchive parse failed entirely — fall back to whole-EXE string search
        names = read_pyz_names_string_search(exe_data)
        return names, [], f"CArchive parse failed — raw byte search. {status}"

    pyz_data = extract_pyz_from_exe(exe_data, entries)
    if pyz_data:
        names = read_pyz_names_structured(pyz_data)
        if names:
            return names, entries, status + " (PYZ TOC parsed)"
        names = read_pyz_names_string_search(pyz_data)
        if names:
            return names, entries, status + " (PYZ string search)"

    # No PYZ found or PYZ unreadable — string-search the whole exe
    names = read_pyz_names_string_search(exe_data)
    return names, entries, status + " (whole-EXE string search fallback)"


# ═══════════════════════════════════════════════════════════════════════════
#  EXE-SPECIFIC VERIFICATION
# ═══════════════════════════════════════════════════════════════════════════

def check_exe_file_basics(R: Results, exe_path: Path, label: str,
                           min_size: int = 1_000_000,
                           max_size: int = 30_000_000) -> bool:
    """Check that an .exe exists with reasonable size and valid PE header."""
    if not exe_path.exists():
        R.fail(f"{label} not found at {exe_path}",
               f"Run 'python build.py' first.")
        return False

    stat = exe_path.stat()
    size = stat.st_size
    mtime = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_mtime))
    R.ok(f"{label} found", f"{fmt_size(size)}, built {mtime}")

    if size < min_size:
        R.fail(f"{label} is suspiciously small ({fmt_size(size)})",
               f"Expected at least {fmt_size(min_size)} for PyInstaller 6 onedir stub.")
        return False
    elif size > max_size:
        R.warn(f"{label} is larger than expected ({fmt_size(size)})",
               f"Expected at most {fmt_size(max_size)}. May indicate accidental --onefile mode.")
    else:
        R.ok(f"{label} size is plausible for PyInstaller 6 onedir stub")

    # Windows PE header check
    try:
        first_two = exe_path.read_bytes()[:2]
        if first_two == b"MZ":
            R.ok(f"{label} has valid Windows PE header (MZ magic)")
        else:
            R.fail(f"{label} missing PE header",
                   f"First 2 bytes: {first_two!r}, expected b'MZ'.")
            return False
    except Exception as e:
        R.warn(f"Could not read {label} header", str(e))

    return True


def check_exe_embedded_archive(R: Results, exe_path: Path, label: str,
                                required_modules: list[str],
                                expected_packages: list[tuple[str, str]],
                                internal_dir: Optional[Path] = None) -> bool:
    """
    Deep verification of an EXE's embedded CArchive and PYZ.
    Verifies that all required Python modules are bundled inside the EXE.

    Args:
        internal_dir: if provided, packages not found in PYZ will also be
                      searched in _internal/ as C extensions / data files.
    """
    try:
        exe_data = exe_path.read_bytes()
    except Exception as e:
        R.fail(f"Cannot read {label} bytes", str(e))
        return False

    R.info(f"Parsing embedded archive in {label} ({fmt_size(len(exe_data))})...")

    module_names, entries, status = get_all_module_names_from_exe(exe_data)

    R.info(f"Archive parse: {status}")

    if entries:
        type_counts: dict[str, int] = {}
        for e in entries:
            tn = e["type_name"]
            type_counts[tn] = type_counts.get(tn, 0) + 1
        R.ok(f"{label} CArchive: {len(entries)} TOC entries",
             ", ".join(f"{v} {k}" for k, v in sorted(type_counts.items())))
    else:
        R.warn(f"{label} CArchive TOC could not be parsed",
               "Module checks will rely on byte-string search fallback.")

    if not module_names:
        R.fail(f"No module names extractable from {label}",
               "Cannot verify bundled modules.")
        return False

    src_mods = sorted(n for n in module_names if n.startswith("src."))
    R.ok(f"{label} module list extracted: {len(module_names)} total",
         f"{len(src_mods)} src.* modules")

    # Verify required modules
    missing = []
    for mod in required_modules:
        if mod in module_names:
            R.ok(f"  {mod}")
        else:
            # Fuzzy fallback — PYZ sometimes stores with different separators
            if any(mod.replace(".", "/") in n or mod in n for n in module_names):
                R.ok(f"  {mod} (fuzzy match)")
            else:
                R.fail(f"  NOT in {label}: {mod}")
                missing.append(mod)

    if missing:
        R.fail(f"{len(missing)} required module(s) missing from {label}",
               "Check the spec file's hiddenimports list.")
        all_required_ok = False
    else:
        R.ok(f"All {len(required_modules)} required modules confirmed in {label}")
        all_required_ok = True

    # Verify packages — some live in PYZ as Python modules, some in _internal/
    # as C extensions (e.g. pygame's .pyd files, tkinter's _tkinter.pyd)
    for pkg, desc in expected_packages:
        in_pyz = any(
            n == pkg or n.startswith(pkg + ".") or n.startswith(pkg + "/")
            for n in module_names
        )
        if in_pyz:
            count = sum(
                1 for n in module_names
                if n == pkg or n.startswith(pkg + ".") or n.startswith(pkg + "/")
            )
            R.ok(f"  {pkg} ({count} sub-modules in PYZ)", desc)
        elif internal_dir is not None:
            # Look for it as a C extension or folder in _internal/
            folder_match = (internal_dir / pkg).is_dir()
            pyd_matches = list(internal_dir.rglob(f"{pkg}*.pyd"))
            dll_matches = list(internal_dir.rglob(f"{pkg}*.dll"))
            if folder_match or pyd_matches or dll_matches:
                R.ok(f"  {pkg} (in _internal/ as native extension)", desc)
            else:
                # Optional packages aren't reported as failures
                R.info(f"  {pkg} not bundled — {desc} (optional)")
        else:
            R.info(f"  {pkg} not in PYZ — {desc} (may be a C extension)")

    return all_required_ok


# ═══════════════════════════════════════════════════════════════════════════
#  STRUCTURE CHECKS
# ═══════════════════════════════════════════════════════════════════════════

def check_internal_folder(R: Results, internal: Path) -> bool:
    """Verify _internal/ folder with required DLLs."""
    if not internal.exists():
        R.fail("_internal/ folder not found",
               f"Expected at: {internal}\n"
               "Required for PyInstaller 6 onedir builds.")
        return False

    all_files = walk(internal)
    total_bytes = sum(f.stat().st_size for f in all_files)
    dll_count = sum(1 for f in all_files if f.suffix.lower() in (".dll", ".pyd"))

    R.ok(f"_internal/ exists",
         f"{len(all_files)} files, {fmt_size(total_bytes)}, {dll_count} DLL/PYD")

    if total_bytes < 5 * 1024 * 1024:
        R.fail(f"_internal/ suspiciously small ({fmt_size(total_bytes)})",
               "Expected 20-60 MB of DLLs and C extensions.")
        return False
    elif total_bytes < 15 * 1024 * 1024:
        R.warn(f"_internal/ smaller than expected ({fmt_size(total_bytes)})",
               "Some DLLs may be missing.")
    else:
        R.ok(f"_internal/ size is plausible ({fmt_size(total_bytes)})")

    # base_library.zip is critical for stdlib
    blz = internal / "base_library.zip"
    if blz.exists():
        R.ok(f"base_library.zip ({fmt_size(blz.stat().st_size)})",
             "Compressed Python stdlib")
    else:
        R.fail("base_library.zip missing",
               "Python stdlib modules will be unavailable at runtime.")
        return False

    return True


def check_required_dlls(R: Results, internal: Path, dist_dir: Path) -> bool:
    """Verify required DLLs are present in _internal/ or dist root."""
    dll_checks = [
        ("python3*.dll", True, "Python runtime DLL"),
        ("SDL2.dll", True, "pygame SDL2 core"),
        ("_tkinter*.pyd", True, "Tkinter C extension"),
        ("tcl*.dll", True, "Tcl runtime"),
        ("tk*.dll", True, "Tk runtime"),
    ]

    all_present = True
    for pattern, required, desc in dll_checks:
        found = find_in_tree(internal, pattern) + find_in_tree(dist_dir, pattern)
        # Deduplicate by filename
        seen = {}
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
                all_present = False

    return all_present


def check_dist_structure(R: Results, dist_dir: Path) -> dict:
    """
    Verify the dist folder structure. Returns a dict describing what's present.
    """
    structure = {
        "fx_machine_exe": False,
        "analyze_session_exe": False,
        "internal": False,
        "config": False,
        "config_presets": False,
        "docs": False,
        "readme": False,
    }

    all_files = walk(dist_dir)
    total_bytes = sum(f.stat().st_size for f in all_files)
    R.info(f"Total dist folder: {fmt_size(total_bytes)} across {len(all_files)} files")

    # Required components
    fx_exe = dist_dir / "FX_Machine.exe"
    if fx_exe.is_file():
        structure["fx_machine_exe"] = True
        R.ok("FX_Machine.exe", f"{fmt_size(fx_exe.stat().st_size)}")
    else:
        R.fail("FX_Machine.exe NOT FOUND",
               "This is required for every build profile.")

    internal = dist_dir / "_internal"
    if internal.is_dir():
        structure["internal"] = True
        fc = sum(1 for _ in internal.rglob("*") if _.is_file())
        R.ok(f"_internal/  ({fc} files)")
    else:
        R.fail("_internal/ folder NOT FOUND",
               "Required by all PyInstaller 6 onedir builds.")

    config = dist_dir / "config"
    if config.is_dir():
        structure["config"] = True
        fc = sum(1 for _ in config.rglob("*") if _.is_file())
        R.ok(f"config/  ({fc} files)")
    else:
        R.fail("config/ folder NOT FOUND",
               "Required for first-launch configuration seeding.")

    # Optional components — depend on build profile
    as_exe = dist_dir / "Analyze_Session.exe"
    if as_exe.is_file():
        structure["analyze_session_exe"] = True
        R.ok("Analyze_Session.exe", f"{fmt_size(as_exe.stat().st_size)}")

    presets = config / "presets" if config.is_dir() else None
    if presets and presets.is_dir():
        pc = sum(1 for _ in presets.iterdir() if _.is_file())
        if pc > 0:
            structure["config_presets"] = True
            R.ok(f"config/presets/  ({pc} files)")

    docs = dist_dir / "docs"
    if docs.is_dir():
        structure["docs"] = True
        dc = sum(1 for _ in docs.rglob("*") if _.is_file())
        R.ok(f"docs/  ({dc} files)")

    readme = dist_dir / "README.md"
    if readme.is_file():
        structure["readme"] = True
        R.ok(f"README.md", f"{fmt_size(readme.stat().st_size)}")

    return structure


def detect_profile(structure: dict) -> str:
    """Detect which build profile was used based on what's present."""
    has_analyze = structure["analyze_session_exe"]
    has_docs = structure["docs"]
    has_readme = structure["readme"]

    if has_analyze and has_docs and has_readme:
        return "FULL"
    elif has_analyze and not has_docs and not has_readme:
        return "STANDARD"
    elif not has_analyze and not has_docs and not has_readme:
        return "MINIMAL"
    else:
        return "CUSTOM"


# ═══════════════════════════════════════════════════════════════════════════
#  CONFIG FILE CHECKS
# ═══════════════════════════════════════════════════════════════════════════

def check_config_files(R: Results, config_dir: Path) -> bool:
    """Verify config files exist with reasonable sizes."""
    required = [
        ("default.toml", 1_000, "Factory template — required for first-run seeding"),
        ("EXAMPLES.toml", 500, "Preset snippets"),
        ("README.md", 200, "Config folder explainer"),
    ]

    all_ok = True
    for fname, min_bytes, desc in required:
        path = config_dir / fname
        if not path.is_file():
            R.fail(f"config/{fname} missing", desc)
            all_ok = False
        else:
            size = path.stat().st_size
            if size < min_bytes:
                R.warn(f"config/{fname} unusually small ({size} bytes)",
                       f"Expected at least {min_bytes} bytes. May be empty or truncated.")
            else:
                R.ok(f"config/{fname}  ({fmt_size(size)})", desc)

    # active.toml should NOT be in a fresh build
    active = config_dir / "active.toml"
    if active.exists():
        R.warn("config/active.toml is present in build output",
               "User-specific. Will be regenerated on first launch. Not intended to ship.")
    else:
        R.ok("config/active.toml absent", "Will be auto-created on first launch")

    return all_ok


def check_config_content(R: Results, config_dir: Path) -> bool:
    """Verify shipped config files contain expected key strings."""
    checks = [
        ("default.toml", "[eq.encoder]", "EQ encoder section"),
        ("default.toml", "[eq.flick]", "EQ flick gesture section"),
        ("default.toml", "[trim]", "TRIM section"),
        ("default.toml", "[fx]", "FX section"),
        ("default.toml", "[meter]", "Meter section"),
        ("default.toml", "[network]", "Network section"),
        ("default.toml", "[diagnostics]", "Diagnostics section"),
        ("default.toml", "sweep_seconds", "Encoder sweep key"),
        ("EXAMPLES.toml", "PUNCHY CLUB", "Punchy Club preset"),
        ("EXAMPLES.toml", "STUDIO PRECISE", "Studio Precise preset"),
        ("EXAMPLES.toml", "BEGINNER FORGIVING", "Beginner preset"),
        ("README.md", "active.toml", "active.toml reference"),
        ("README.md", "FX Machine", "Project name"),
    ]

    all_ok = True
    for fname, needle, desc in checks:
        path = config_dir / fname
        if not path.is_file():
            R.fail(f"Cannot check config/{fname} — file missing")
            all_ok = False
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            if needle in text:
                R.ok(f"config/{fname} contains '{needle}'", desc)
            else:
                R.fail(f"config/{fname} missing expected text: '{needle}'",
                       f"{desc}. May be the wrong version or corrupted.")
                all_ok = False
        except Exception as e:
            R.fail(f"Cannot read config/{fname}", str(e))
            all_ok = False

    return all_ok


def check_diagnostics_flag(R: Results, config_dir: Path) -> Optional[bool]:
    """
    Detect the diagnostics enabled flag in shipped default.toml.
    Returns True/False/None.
    """
    default_toml = config_dir / "default.toml"
    if not default_toml.is_file():
        return None

    try:
        with open(default_toml, "r", encoding="utf-8") as f:
            in_diagnostics = False
            for line in f:
                stripped = line.strip()
                if stripped == "[diagnostics]":
                    in_diagnostics = True
                    continue
                if in_diagnostics and stripped.startswith("[") and not stripped.startswith("[diagnostics"):
                    break
                if in_diagnostics and stripped.startswith("enabled"):
                    if "=" in stripped:
                        value = stripped.split("=", 1)[1].strip().lower()
                        if value == "true":
                            R.info(f"Diagnostics in shipped config: {C.OK}ENABLED{C.END}")
                            return True
                        elif value == "false":
                            R.info(f"Diagnostics in shipped config: {C.WARN}DISABLED{C.END}")
                            return False
        R.warn("Could not detect diagnostics flag in default.toml")
        return None
    except Exception as e:
        R.warn(f"Error reading default.toml diagnostics flag: {e}")
        return None


def check_toml_validity(R: Results, config_dir: Path) -> bool:
    """Verify TOML files parse correctly with tomllib."""
    try:
        import tomllib
    except ImportError:
        R.warn("tomllib not available (need Python 3.11+)",
               "Cannot parse-validate shipped TOML files.")
        return True

    all_ok = True
    for fname in ["default.toml", "EXAMPLES.toml"]:
        path = config_dir / fname
        if not path.is_file():
            continue
        try:
            with open(path, "rb") as f:
                data = tomllib.load(f)

            key_count = 0

            def count_keys(d):
                nonlocal key_count
                for v in d.values():
                    key_count += 1
                    if isinstance(v, dict):
                        count_keys(v)

            count_keys(data)
            R.ok(f"config/{fname} parses correctly", f"{key_count} keys")
        except Exception as e:
            R.fail(f"config/{fname} parse error", f"{type(e).__name__}: {e}")
            all_ok = False

    return all_ok


# ═══════════════════════════════════════════════════════════════════════════
#  DOCS CHECK
# ═══════════════════════════════════════════════════════════════════════════

EXPECTED_DOCS = [
    "ARCHITECTURE.md",
    "BUILDING.md",
    "CONFIG_REFERENCE.md",
    "DIAGNOSTICS_GUIDE.md",
    "FOR_MUSICIANS.md",
    "GESTURE_ENGINE.md",
    "SETUP_ABLETON.md",
    "SIGNAL_CHAIN.md",
    "TROUBLESHOOTING.md",
]


def check_docs_folder(R: Results, docs_dir: Path) -> bool:
    """Verify docs/ folder contents."""
    if not docs_dir.is_dir():
        R.info("docs/ folder not present (optional, only in FULL/CUSTOM builds)")
        return True

    found_docs = set(f.name for f in docs_dir.iterdir() if f.is_file())
    missing_docs = [d for d in EXPECTED_DOCS if d not in found_docs]
    extra_docs = [f for f in found_docs if f not in EXPECTED_DOCS]

    if missing_docs:
        for d in missing_docs:
            R.warn(f"Missing expected doc: docs/{d}")
    else:
        R.ok(f"All {len(EXPECTED_DOCS)} expected docs present")

    if extra_docs:
        R.info(f"Extra docs found: {', '.join(extra_docs)}")

    # Verify each doc has substantial content
    short_docs = []
    for doc in EXPECTED_DOCS:
        path = docs_dir / doc
        if path.is_file():
            size = path.stat().st_size
            if size < 1024:
                short_docs.append((doc, size))

    if short_docs:
        for doc, size in short_docs:
            R.warn(f"docs/{doc} is suspiciously short ({size} bytes)")

    return len(missing_docs) == 0


# ═══════════════════════════════════════════════════════════════════════════
#  MAIN INSPECTION ROUTINE
# ═══════════════════════════════════════════════════════════════════════════

# What modules must be in FX_Machine.exe's embedded PYZ
FX_MACHINE_REQUIRED_MODULES = [
    "src.config",
    "src.config_loader",
    "src.state",
    "src.helpers",
    "src.main",
    "src.log_setup",
    "src.osc.client",
    "src.osc.server",
    "src.osc.discovery",
    "src.engine.eq",
    "src.engine.fx",
    "src.engine.polling",
    "src.engine.navigation",
    "src.engine.actions",
    "src.engine.momentary",
    "src.controller.loop",
    "src.controller.buttons",
    "src.controller.axes",
    "src.controller.watchdog",
    "src.ui.palette",
    "src.ui.widgets",
    "src.ui.builder",
    "src.ui.updater",
]

# Optional packages bundled with FX_Machine
FX_MACHINE_OPTIONAL_PACKAGES = [
    ("pygame", "Gamepad input"),
    ("pythonosc", "OSC communication"),
    ("tkinter", "UI toolkit"),
    ("tomllib", "TOML parser"),
    ("psutil", "System monitoring (optional)"),
    ("src.diagnostics", "Diagnostics layer"),
]


# What modules must be in Analyze_Session.exe's embedded PYZ
ANALYZE_SESSION_REQUIRED_MODULES = [
    "src.diagnostics",
    "src.diagnostics.analyzer",
]

ANALYZE_SESSION_OPTIONAL_PACKAGES = [
    ("tomllib", "TOML parser"),
]


def inspect_bundle(dist_dir: Path, R: Results, strict: bool = False) -> dict:
    """
    Main inspection routine. Returns a result dict.
    """
    result = {
        "structure": {},
        "profile": "UNKNOWN",
        "fx_machine_ok": False,
        "analyze_session_ok": False,
        "config_ok": False,
        "docs_ok": True,
        "diag_enabled": None,
    }

    # ─── Section 1: Dist folder structure ───────────────────────────────
    R.begin_section("Output Folder Structure")
    result["structure"] = check_dist_structure(R, dist_dir)
    R.end_section()

    result["profile"] = detect_profile(result["structure"])
    R.detected_profile = result["profile"]

    profile_color = {
        "MINIMAL": C.DIM,
        "STANDARD": C.OK,
        "FULL": C.OK,
        "CUSTOM": C.WARN,
    }.get(result["profile"], C.DIM)
    print(f"\n  {C.BOLD}Detected profile:{C.END} {profile_color}{result['profile']}{C.END}")

    # ─── Section 2: FX_Machine.exe basics ───────────────────────────────
    fx_exe = dist_dir / "FX_Machine.exe"
    if result["structure"]["fx_machine_exe"]:
        R.begin_section("FX_Machine.exe — Basic Verification")
        result["fx_machine_ok"] = check_exe_file_basics(
            R, fx_exe, "FX_Machine.exe",
            min_size=1_000_000, max_size=30_000_000
        )
        R.end_section()
    else:
        return result

    # ─── Section 3: _internal/ folder ───────────────────────────────────
    internal = dist_dir / "_internal"
    R.begin_section("_internal/ Folder")
    internal_ok = check_internal_folder(R, internal)
    R.end_section()

    if not internal_ok:
        return result

    # ─── Section 4: Required DLLs ───────────────────────────────────────
    R.begin_section("Required DLLs and C Extensions")
    check_required_dlls(R, internal, dist_dir)
    R.end_section()

    # ─── Section 5: FX_Machine.exe embedded archive ─────────────────────
    R.begin_section("FX_Machine.exe Embedded Archive (CArchive + PYZ)")
    fx_archive_ok = check_exe_embedded_archive(
        R, fx_exe, "FX_Machine.exe",
        FX_MACHINE_REQUIRED_MODULES,
        FX_MACHINE_OPTIONAL_PACKAGES,
        internal_dir=internal,
    )
    R.end_section()
    result["fx_machine_ok"] = result["fx_machine_ok"] and fx_archive_ok

    # ─── Section 6: Analyze_Session.exe (if present) ────────────────────
    if result["structure"]["analyze_session_exe"]:
        as_exe = dist_dir / "Analyze_Session.exe"

        R.begin_section("Analyze_Session.exe — Basic Verification")
        as_basic_ok = check_exe_file_basics(
            R, as_exe, "Analyze_Session.exe",
            min_size=1_000_000, max_size=15_000_000
        )
        R.end_section()

        if as_basic_ok:
            R.begin_section("Analyze_Session.exe Embedded Archive")
            as_archive_ok = check_exe_embedded_archive(
                R, as_exe, "Analyze_Session.exe",
                ANALYZE_SESSION_REQUIRED_MODULES,
                ANALYZE_SESSION_OPTIONAL_PACKAGES,
                internal_dir=internal,
            )
            R.end_section()
            result["analyze_session_ok"] = as_basic_ok and as_archive_ok
        else:
            result["analyze_session_ok"] = False
    else:
        R.info("\nAnalyze_Session.exe not included in this build (skipping checks)")
        result["analyze_session_ok"] = True

    # ─── Section 7: Config files ────────────────────────────────────────
    config_dir = dist_dir / "config"
    R.begin_section("Config Files")
    files_ok = check_config_files(R, config_dir)
    R.end_section()

    R.begin_section("Config File Content Signatures")
    content_ok = check_config_content(R, config_dir)
    R.end_section()

    R.begin_section("TOML Validity")
    toml_ok = check_toml_validity(R, config_dir)
    R.end_section()

    R.begin_section("Diagnostics Configuration")
    result["diag_enabled"] = check_diagnostics_flag(R, config_dir)
    R.end_section()

    result["config_ok"] = files_ok and content_ok and toml_ok

    # ─── Section 8: Docs (if present) ───────────────────────────────────
    docs_dir = dist_dir / "docs"
    if docs_dir.is_dir():
        R.begin_section("Documentation Folder")
        result["docs_ok"] = check_docs_folder(R, docs_dir)
        R.end_section()

    return result


# ═══════════════════════════════════════════════════════════════════════════
#  USER PAUSE
# ═══════════════════════════════════════════════════════════════════════════

def wait_for_user_keypress():
    """Pause for user input on Windows to prevent console from closing."""
    print(f"\n{C.DIM}  Press any key to exit...{C.END}", end="", flush=True)
    try:
        import msvcrt
        msvcrt.getch()
    except ImportError:
        try:
            input()
        except (EOFError, KeyboardInterrupt):
            pass
    print()


# ═══════════════════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════════════════

def parse_args():
    parser = argparse.ArgumentParser(
        description="Inspect an FX Machine build to verify it's complete and correct.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--exe", type=Path, default=None,
        help="Path to FX_Machine.exe (default: dist/FX_Machine/FX_Machine.exe)",
    )
    parser.add_argument(
        "--no-pause", action="store_true",
        help="Don't wait for keypress on exit (useful when called from build.py)",
    )
    parser.add_argument(
        "--quiet", action="store_true",
        help="Suppress passed checks, only show warnings and errors",
    )
    parser.add_argument(
        "--strict", action="store_true",
        help="Treat warnings as errors (exit 2 even on warnings)",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output raw JSON report instead of pretty-printing",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    start = time.time()

    # Determine dist folder location
    if args.exe:
        exe_path = args.exe.resolve()
        dist_dir = exe_path.parent
    else:
        script_dir = Path(__file__).resolve().parent
        dist_dir = script_dir / "dist" / "FX_Machine"

    # Banner
    if not args.json:
        print(f"\n{C.BOLD}{C.INFO}╔{'═' * 62}╗{C.END}")
        print(f"{C.BOLD}{C.INFO}║{' ' * 14}FX MACHINE — BUILD INSPECTOR{' ' * 20}║{C.END}")
        print(f"{C.BOLD}{C.INFO}╚{'═' * 62}╝{C.END}\n")
        print(f"  {C.DIM}Inspecting:  {dist_dir}{C.END}")
        print(f"  {C.DIM}Layout:      PyInstaller 6.20 onedir{C.END}")
        if args.strict:
            print(f"  {C.DIM}Strict mode: enabled (warnings = errors){C.END}")
        if args.quiet:
            print(f"  {C.DIM}Quiet mode:  enabled (passed checks hidden){C.END}")

    # Check dist folder exists
    if not dist_dir.exists():
        if args.json:
            print(json.dumps({"error": f"Dist folder not found: {dist_dir}"}))
        else:
            print(f"\n{C.FAIL}❌  Dist folder not found: {dist_dir}{C.END}\n")
            print(f"  Run {C.INFO}python build.py{C.END} first to create a build.\n")
        if not args.no_pause:
            wait_for_user_keypress()
        sys.exit(2)

    # Run inspection
    R = Results(quiet=args.quiet)
    result = inspect_bundle(dist_dir, R, strict=args.strict)

    # JSON output mode
    if args.json:
        output = {
            "checks_total": R.checks,
            "checks_passed": R.passed,
            "checks_warned": R.warned,
            "checks_failed": R.failed,
            "errors": R.errors,
            "warnings": R.warns,
            "detected_profile": R.detected_profile,
            "result": result,
        }
        print(json.dumps(output, indent=2, default=str))
        sys.exit(0 if R.failed == 0 else 2)

    # Pretty summary
    elapsed = time.time() - start
    print(f"\n{C.BOLD}{'━' * 64}{C.END}")
    print(f"{C.BOLD}SUMMARY{C.END}  ({elapsed:.1f}s)")
    print(f"  Total checks  : {R.checks}")
    print(f"  {C.OK}Passed{C.END}        : {R.passed}")
    print(f"  {C.WARN}Warnings{C.END}      : {R.warned}")
    print(f"  {C.FAIL}Failed{C.END}        : {R.failed}")
    print(f"  Profile       : {R.detected_profile}")
    print(f"{C.BOLD}{'━' * 64}{C.END}")

    # Determine exit code
    if R.failed > 0:
        print(f"\n{C.FAIL}{C.BOLD}❌  {R.failed} ERROR(S) — DO NOT SHIP THIS BUILD{C.END}")
        print(f"\n{C.FAIL}Errors:{C.END}")
        for e in R.errors:
            print(f"  • {e}")
        exit_code = 2
    elif args.strict and R.warned > 0:
        print(f"\n{C.WARN}⚠   {R.warned} WARNING(S) (--strict: treated as errors){C.END}")
        for w in R.warns:
            print(f"  • {w}")
        exit_code = 2
    elif R.warned > 0:
        print(f"\n{C.WARN}⚠   {R.warned} WARNING(S) — review before shipping{C.END}")
        for w in R.warns:
            print(f"  • {w}")
        print(f"\n{C.OK}Build is functional but has minor issues.{C.END}")
        exit_code = 1
    else:
        print(f"\n{C.OK}{C.BOLD}✅  ALL CHECKS PASSED — BUILD IS GOOD TO SHIP{C.END}")
        print(f"\n  Detected profile: {R.detected_profile}")
        if R.detected_profile == "STANDARD":
            print(f"  This is the recommended profile for distribution.")
        elif R.detected_profile == "FULL":
            print(f"  This is the complete build with documentation.")
        elif R.detected_profile == "MINIMAL":
            print(f"  This is the minimal build (no analyzer, no docs).")
        elif R.detected_profile == "CUSTOM":
            print(f"  This is a custom build configuration.")
        exit_code = 0

    print()

    if not args.no_pause:
        wait_for_user_keypress()

    sys.exit(exit_code)


if __name__ == "__main__":
    main()