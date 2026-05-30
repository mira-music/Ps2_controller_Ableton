#!/usr/bin/env python3
"""
================================================================================
  build.py — FX Machine Interactive Build Wizard
================================================================================
  Interactive installer-style build script for FX Machine v1.0.0.

  Usage:
      python build.py                  # interactive wizard
      python build.py --version        # print version info and exit

  The wizard asks the user (developer) what kind of build to produce:

  Build profiles:
      1. MINIMAL    Just FX_Machine.exe + config (~40 MB)
                    Diagnostics OFF by default in shipped config.
                    For end users who want the smallest download.

      2. STANDARD   FX_Machine.exe + Analyze_Session.exe + config (~50 MB)
                    Diagnostics ON by default in shipped config.
                    RECOMMENDED for distribution. Users can analyze
                    their sessions and send reports for support.

      3. FULL       Everything in STANDARD + docs/ + README.md (~52 MB)
                    For end users who want complete documentation.

      4. CUSTOM     Choose each component individually.

  Output:
      dist/FX_Machine/
      ├── FX_Machine.exe              (always)
      ├── Analyze_Session.exe         (STANDARD, FULL, optional CUSTOM)
      ├── _internal/                  (shared Python runtime + DLLs)
      ├── config/
      │   ├── default.toml            (with diagnostics ON or OFF
      │   ├── EXAMPLES.toml             based on profile)
      │   ├── README.md
      │   └── presets/
      ├── docs/                       (FULL or optional CUSTOM)
      └── README.md                   (FULL or optional CUSTOM)

  Build process:
      1. Pre-flight checks (PyInstaller, dependencies, source files)
      2. Version detection from src/config.py
      3. Interactive wizard — user picks profile and components
      4. Generate spec files for selected binaries (if missing)
      5. Clean previous build artifacts
      6. Run PyInstaller for each binary (FX_Machine first, then optionals)
      7. Verify each .exe was created
      8. Copy config files (with diagnostics enabled/disabled per profile)
      9. Copy presets, docs, README per profile
      10. Cleanup intermediate artifacts
      11. Print detailed report with distribution instructions

  Exit codes:
      0 = build succeeded
      1 = pre-flight check failed
      2 = user cancelled the wizard
      3 = PyInstaller failed for one or more binaries
      4 = post-build verification failed
================================================================================
"""

import sys
import os
import shutil
import subprocess
import argparse
import time
from pathlib import Path


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
#  BUILD PROFILE DEFINITIONS
# ═══════════════════════════════════════════════════════════════════════════
#
#  Each profile is a dict of which components to include. Profiles can
#  be selected by number (1-4) or via the CUSTOM path which asks per
#  component.
#
#  Components:
#    fx_machine        Always True — main app is required
#    analyze_session   Build Analyze_Session.exe?
#    docs              Copy docs/ folder?
#    readme            Copy main README.md?
#    presets           Copy config/presets/ folder?
#    diag_enabled      Set [diagnostics] enabled=true in shipped config?
# ═══════════════════════════════════════════════════════════════════════════

PROFILES = {
    "MINIMAL": {
        "fx_machine":      True,
        "analyze_session": False,
        "docs":            False,
        "readme":          False,
        "presets":         True,
        "diag_enabled":    False,
    },
    "STANDARD": {
        "fx_machine":      True,
        "analyze_session": True,
        "docs":            False,
        "readme":          False,
        "presets":         True,
        "diag_enabled":    True,
    },
    "FULL": {
        "fx_machine":      True,
        "analyze_session": True,
        "docs":            True,
        "readme":          True,
        "presets":         True,
        "diag_enabled":    True,
    },
}


# ═══════════════════════════════════════════════════════════════════════════
#  HIDDEN IMPORTS (for PyInstaller spec files)
# ═══════════════════════════════════════════════════════════════════════════
#
#  These modules are loaded dynamically (via monkey-patching for diagnostics,
#  or referenced by string name in TOML) so PyInstaller's static analysis
#  doesn't detect them. They must be declared explicitly in the spec file.
# ═══════════════════════════════════════════════════════════════════════════

FX_MACHINE_HIDDEN_IMPORTS = [
    # Diagnostics package — loaded via monkey-patch installer
    "src.diagnostics",
    "src.diagnostics.installer",
    "src.diagnostics.profiler",
    "src.diagnostics.counters",
    "src.diagnostics.osc_tracker",
    "src.diagnostics.sampler",
    "src.diagnostics.thread_health",
    "src.diagnostics.rate_limiter",
    "src.diagnostics.reporter",
    "src.diagnostics.analyzer",

    # Optional psutil submodules
    "psutil",
    "psutil._psutil_windows",

    # pythonosc submodules
    "pythonosc.dispatcher",
    "pythonosc.osc_server",
    "pythonosc.udp_client",
    "pythonosc.osc_message",
    "pythonosc.osc_message_builder",

    # tomllib (stdlib in 3.11+, sometimes missed)
    "tomllib",
]


ANALYZE_SESSION_HIDDEN_IMPORTS = [
    # The analyzer module itself
    "src.diagnostics",
    "src.diagnostics.analyzer",

    # tomllib for version detection
    "tomllib",
]


# ═══════════════════════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def info(msg: str):
    print(f"  {C.INFO}ℹ{C.END} {msg}")

def success(msg: str):
    print(f"  {C.OK}✓{C.END} {msg}")

def warn(msg: str):
    print(f"  {C.WARN}⚠{C.END} {msg}")

def fail(msg: str, detail: str = ""):
    print(f"  {C.FAIL}✗{C.END} {msg}")
    if detail:
        print(f"      {C.DIM}{detail}{C.END}")

def header(title: str):
    print(f"\n{C.BOLD}{C.INFO}━━━ {title} ━━━{C.END}")

def banner():
    print(f"\n{C.BOLD}{C.INFO}╔{'═' * 62}╗{C.END}")
    print(f"{C.BOLD}{C.INFO}║{' ' * 12}FX MACHINE — INTERACTIVE BUILD WIZARD{' ' * 13}║{C.END}")
    print(f"{C.BOLD}{C.INFO}╚{'═' * 62}╝{C.END}")

def fmt_size(bytes_count: int) -> str:
    if bytes_count >= 1024 * 1024:
        return f"{bytes_count / (1024 * 1024):.1f} MB"
    elif bytes_count >= 1024:
        return f"{bytes_count / 1024:.1f} KB"
    return f"{bytes_count} B"

def get_folder_size_mb(folder: Path) -> float:
    total = 0
    try:
        for f in folder.rglob('*'):
            if f.is_file():
                try:
                    total += f.stat().st_size
                except OSError:
                    pass
    except Exception:
        pass
    return total / (1024 * 1024)

def find_exe_in_folder(folder: Path) -> Path | None:
    try:
        exes = list(folder.glob("*.exe"))
        return exes[0] if exes else None
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════════════════════
#  USER INPUT HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def ask_yes_no(prompt: str, default: bool = True) -> bool:
    """
    Ask a yes/no question. Returns True for yes, False for no.
    The default is highlighted in the prompt (Y/n means default yes).
    """
    suffix = "[Y/n]" if default else "[y/N]"
    while True:
        try:
            answer = input(f"  {prompt} {suffix}: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print(f"\n  {C.WARN}Build cancelled by user{C.END}\n")
            sys.exit(2)

        if not answer:
            return default
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        print(f"  {C.WARN}Please answer yes or no{C.END}")


def ask_choice(prompt: str, choices: list[str], default: str | None = None) -> str:
    """
    Ask user to pick from a list of choices. Returns the chosen string.
    `choices` should be a list like ['1', '2', '3', '4'].
    """
    suffix = "/".join(choices)
    default_hint = f" (default: {default})" if default else ""
    while True:
        try:
            answer = input(f"  {prompt} [{suffix}]{default_hint}: ").strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n  {C.WARN}Build cancelled by user{C.END}\n")
            sys.exit(2)

        if not answer and default:
            return default
        if answer in choices:
            return answer
        print(f"  {C.WARN}Please choose one of: {', '.join(choices)}{C.END}")


# ═══════════════════════════════════════════════════════════════════════════
#  VERSION DETECTION
# ═══════════════════════════════════════════════════════════════════════════

def detect_version(project_root: Path) -> str:
    config_path = project_root / "src" / "config.py"
    if not config_path.is_file():
        return "unknown"
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("VERSION") and "=" in line:
                    parts = line.split("=", 1)
                    if len(parts) == 2:
                        value = parts[1].strip()
                        value = value.split("#")[0].strip()
                        value = value.strip('"').strip("'")
                        if value:
                            return value
        return "unknown"
    except Exception:
        return "unknown"


# ═══════════════════════════════════════════════════════════════════════════
#  PRE-FLIGHT CHECKS
# ═══════════════════════════════════════════════════════════════════════════

def check_pyinstaller() -> bool:
    try:
        import PyInstaller
        version = getattr(PyInstaller, "__version__", "unknown")
        success(f"PyInstaller {version} found")
        try:
            major = int(version.split(".")[0])
            if major < 5:
                warn(f"PyInstaller {version} is older than v5 — upgrade recommended")
                warn("Run: pip install --upgrade pyinstaller")
        except Exception:
            pass
        return True
    except ImportError:
        fail("PyInstaller is not installed",
             "Run:  pip install pyinstaller")
        return False


def check_dependencies() -> bool:
    """Check that all required Python dependencies are installed."""
    all_ok = True

    # Required
    try:
        import pygame
        success(f"pygame {pygame.version.ver}")
    except ImportError:
        fail("pygame not installed", "Run: pip install pygame")
        all_ok = False

    try:
        import pythonosc
        success("python-osc installed")
    except ImportError:
        fail("python-osc not installed", "Run: pip install python-osc")
        all_ok = False

    # Optional
    try:
        import psutil
        success(f"psutil {psutil.__version__} (diagnostics will have full features)")
    except ImportError:
        warn("psutil not installed — diagnostics will run in degraded mode")
        warn("Install for full diagnostics: pip install psutil")
        # Not a failure — build can proceed

    return all_ok


def check_config_files(config_src: Path) -> tuple[bool, list[str]]:
    if not config_src.is_dir():
        fail(f"config/ folder not found at {config_src}")
        return False, ["config/ folder itself"]

    required = ['default.toml', 'EXAMPLES.toml', 'README.md']
    missing = []

    for fname in required:
        path = config_src / fname
        if path.is_file():
            size = path.stat().st_size
            success(f"config/{fname}  ({fmt_size(size)})")
        else:
            fail(f"config/{fname} not found")
            missing.append(fname)

    return len(missing) == 0, missing


def check_source_files(project_root: Path) -> bool:
    critical_files = [
        "run.py",
        "analyze_diagnostics.py",
        "src/main.py",
        "src/config.py",
        "src/state.py",
        "src/diagnostics/__init__.py",
        "src/diagnostics/analyzer.py",
    ]
    all_ok = True
    for rel_path in critical_files:
        path = project_root / rel_path
        if not path.is_file():
            fail(f"Critical source file missing: {rel_path}")
            all_ok = False
    if all_ok:
        success("All critical source files present")
    return all_ok


# ═══════════════════════════════════════════════════════════════════════════
#  INTERACTIVE WIZARD
# ═══════════════════════════════════════════════════════════════════════════

def show_profile_menu():
    """Show the build profile menu."""
    print(f"\n  {C.BOLD}Choose a build profile:{C.END}\n")

    print(f"    {C.BOLD}1. MINIMAL{C.END}     "
          f"Just FX_Machine.exe + config (~40 MB)")
    print(f"                  {C.DIM}Diagnostics OFF by default in shipped config.{C.END}")
    print(f"                  {C.DIM}For end users who want the smallest download.{C.END}")
    print()

    print(f"    {C.BOLD}2. STANDARD{C.END}    "
          f"FX_Machine.exe + Analyze_Session.exe + config (~50 MB)")
    print(f"                  {C.DIM}Diagnostics ON by default in shipped config.{C.END}")
    print(f"                  {C.OK}RECOMMENDED for distribution.{C.END}")
    print(f"                  {C.DIM}Users can analyze their sessions and send reports.{C.END}")
    print()

    print(f"    {C.BOLD}3. FULL{C.END}        "
          f"STANDARD + docs/ + README.md (~52 MB)")
    print(f"                  {C.DIM}Diagnostics ON by default.{C.END}")
    print(f"                  {C.DIM}For end users who want complete documentation.{C.END}")
    print()

    print(f"    {C.BOLD}4. CUSTOM{C.END}      "
          f"Choose each component individually")
    print()


def run_wizard(project_root: Path) -> dict:
    """
    Run the interactive build wizard.
    Returns a profile dict with the user's selections.
    """
    header("Step 3 — Build profile selection")

    show_profile_menu()

    choice = ask_choice("Enter choice", ["1", "2", "3", "4"], default="2")

    if choice == "1":
        profile = dict(PROFILES["MINIMAL"])
        profile["name"] = "MINIMAL"
    elif choice == "2":
        profile = dict(PROFILES["STANDARD"])
        profile["name"] = "STANDARD"
    elif choice == "3":
        profile = dict(PROFILES["FULL"])
        profile["name"] = "FULL"
    elif choice == "4":
        profile = run_custom_wizard()
        profile["name"] = "CUSTOM"
    else:
        # Should not reach here due to ask_choice validation
        sys.exit(2)

    # Confirm
    header("Step 4 — Confirm selection")
    print(f"\n  Profile: {C.BOLD}{profile['name']}{C.END}\n")
    print(f"  Components to bundle:")
    show_component(True, "FX_Machine.exe", "main app (always included)")
    show_component(profile["analyze_session"], "Analyze_Session.exe",
                   "post-session analyzer")
    show_component(profile["docs"], "docs/ folder",
                   "9 detailed guides, ~9000 lines")
    show_component(profile["readme"], "README.md",
                   "main project README in root of distribution")
    show_component(profile["presets"], "config/presets/",
                   "preset profile snippets")
    print()
    diag_status = "ENABLED" if profile["diag_enabled"] else "DISABLED"
    diag_color = C.OK if profile["diag_enabled"] else C.WARN
    print(f"  Diagnostics in shipped config: {diag_color}{diag_status}{C.END}")
    print(f"    {C.DIM}User can change in config/active.toml after install.{C.END}")
    print()

    if not ask_yes_no("Proceed with build?", default=True):
        print(f"\n  {C.WARN}Build cancelled by user{C.END}\n")
        sys.exit(2)

    return profile


def show_component(included: bool, name: str, desc: str):
    icon = f"{C.OK}✓{C.END}" if included else f"{C.DIM}✗{C.END}"
    name_color = C.BOLD if included else C.DIM
    desc_color = "" if included else C.DIM
    print(f"    {icon} {name_color}{name:30}{C.END} {desc_color}{desc}{C.END}")


def run_custom_wizard() -> dict:
    """
    Custom wizard — ask about each component individually.
    Returns a profile dict.
    """
    print(f"\n  {C.BOLD}Custom build configuration{C.END}\n")
    print(f"  {C.DIM}For each component, answer y/n. Defaults are shown in caps.{C.END}\n")

    profile = {
        "fx_machine": True,    # always
        "analyze_session": ask_yes_no(
            "Include Analyze_Session.exe (post-session analyzer)?",
            default=True,
        ),
        "docs": ask_yes_no(
            "Include docs/ folder (9 guides, ~9000 lines)?",
            default=False,
        ),
        "readme": ask_yes_no(
            "Include main README.md in distribution?",
            default=True,
        ),
        "presets": ask_yes_no(
            "Include config/presets/ folder?",
            default=True,
        ),
        "diag_enabled": ask_yes_no(
            "Enable diagnostics by default in shipped config?",
            default=True,
        ),
    }

    return profile


# ═══════════════════════════════════════════════════════════════════════════
#  SPEC FILE GENERATION
# ═══════════════════════════════════════════════════════════════════════════

def generate_fx_machine_spec(project_root: Path, spec_file: Path) -> bool:
    """Generate FX_Machine.spec."""
    imports_str = ",\n        ".join(f'"{imp}"' for imp in FX_MACHINE_HIDDEN_IMPORTS)

    spec_content = f'''# -*- mode: python ; coding: utf-8 -*-
"""
FX_Machine.spec — PyInstaller specification for the main FX Machine app.
Generated by build.py.
"""

block_cipher = None

a = Analysis(
    ['run.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        {imports_str},
    ],
    hookspath=[],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes=[
        'matplotlib', 'numpy', 'pandas', 'PIL',
        'PyQt5', 'PyQt6', 'PySide2', 'PySide6',
        'IPython', 'jupyter', 'pytest',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='FX_Machine',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='FX_Machine',
)
'''
    try:
        with open(spec_file, "w", encoding="utf-8") as f:
            f.write(spec_content)
        success(f"Generated spec file: {spec_file.name}")
        return True
    except Exception as e:
        fail(f"Could not write spec file: {e}")
        return False


def generate_analyze_session_spec(project_root: Path, spec_file: Path) -> bool:
    """Generate Analyze_Session.spec — built with console=True since
    it's a terminal-output tool."""
    imports_str = ",\n        ".join(f'"{imp}"' for imp in ANALYZE_SESSION_HIDDEN_IMPORTS)

    spec_content = f'''# -*- mode: python ; coding: utf-8 -*-
"""
Analyze_Session.spec — PyInstaller specification for the post-session analyzer.
Generated by build.py. Built as a console app so users can see the report.
"""

block_cipher = None

a = Analysis(
    ['analyze_diagnostics.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        {imports_str},
    ],
    hookspath=[],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes=[
        'matplotlib', 'numpy', 'pandas', 'PIL',
        'PyQt5', 'PyQt6', 'PySide2', 'PySide6',
        'IPython', 'jupyter', 'pytest',
        # The analyzer doesn't need pygame, tkinter, or pythonosc
        'pygame', 'tkinter', 'pythonosc',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Analyze_Session',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,                    # console app — user sees the report
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='Analyze_Session',
)
'''
    try:
        with open(spec_file, "w", encoding="utf-8") as f:
            f.write(spec_content)
        success(f"Generated spec file: {spec_file.name}")
        return True
    except Exception as e:
        fail(f"Could not write spec file: {e}")
        return False


# ═══════════════════════════════════════════════════════════════════════════
#  CLEAN BUILD ARTIFACTS
# ═══════════════════════════════════════════════════════════════════════════

def clean_artifacts(project_root: Path):
    """Remove previous build artifacts."""
    items_to_clean = [
        ("dist/FX_Machine/", project_root / "dist" / "FX_Machine"),
        ("dist/Analyze_Session/", project_root / "dist" / "Analyze_Session"),
        ("build/", project_root / "build"),
        ("__pycache__/ (root)", project_root / "__pycache__"),
    ]

    cleaned = 0
    for label, path in items_to_clean:
        if path.exists():
            try:
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()
                success(f"Removed {label}")
                cleaned += 1
            except Exception as e:
                warn(f"Could not remove {label}: {e}")

    # Clean __pycache__ folders in src/
    src_dir = project_root / "src"
    if src_dir.is_dir():
        pycache_count = 0
        for pycache in src_dir.rglob("__pycache__"):
            try:
                shutil.rmtree(pycache)
                pycache_count += 1
            except Exception:
                pass
        if pycache_count > 0:
            success(f"Removed {pycache_count} __pycache__ folder(s) from src/")

    if cleaned == 0:
        info("Nothing to clean (no previous artifacts found)")


# ═══════════════════════════════════════════════════════════════════════════
#  RUN PYINSTALLER
# ═══════════════════════════════════════════════════════════════════════════

def run_pyinstaller(project_root: Path, spec_file: Path, label: str) -> bool:
    """Run PyInstaller with a given spec file."""
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        str(spec_file),
    ]

    info(f"Building {label} (this takes 1-3 minutes)...")
    print(f"  {C.DIM}{'─' * 64}{C.END}")
    start_time = time.time()

    try:
        result = subprocess.run(cmd, cwd=str(project_root))
    except Exception as e:
        fail(f"PyInstaller invocation failed: {e}")
        return False

    elapsed = time.time() - start_time
    print(f"  {C.DIM}{'─' * 64}{C.END}")

    if result.returncode != 0:
        fail(f"PyInstaller exited with code {result.returncode} after {elapsed:.1f}s")
        return False

    success(f"{label} build completed in {elapsed:.1f}s")
    return True


# ═══════════════════════════════════════════════════════════════════════════
#  COPY ADDITIONAL BINARIES
# ═══════════════════════════════════════════════════════════════════════════

def copy_analyze_session_to_main(project_root: Path) -> bool:
    """
    Copy Analyze_Session.exe from dist/Analyze_Session/ to dist/FX_Machine/.
    The Analyze_Session build has its own _internal/ which we discard —
    we use the FX_Machine bundle's _internal/ to keep size down.

    This works because Analyze_Session only needs the same Python runtime
    that FX_Machine already includes. The _internal/ folder is the same.
    """
    src_exe = project_root / "dist" / "Analyze_Session" / "Analyze_Session.exe"
    dst_exe = project_root / "dist" / "FX_Machine" / "Analyze_Session.exe"

    if not src_exe.is_file():
        fail(f"Analyze_Session.exe not found at {src_exe}")
        return False

    try:
        shutil.copy2(src_exe, dst_exe)
        success(f"Copied Analyze_Session.exe to main bundle")

        # Cleanup the now-redundant Analyze_Session folder
        analyze_dir = project_root / "dist" / "Analyze_Session"
        try:
            shutil.rmtree(analyze_dir)
            success("Removed redundant dist/Analyze_Session/ folder")
        except Exception as e:
            warn(f"Could not remove dist/Analyze_Session/: {e}")

        return True
    except Exception as e:
        fail(f"Could not copy Analyze_Session.exe: {e}")
        return False


# ═══════════════════════════════════════════════════════════════════════════
#  POST-BUILD VERIFICATION
# ═══════════════════════════════════════════════════════════════════════════

def verify_exe_created(output_dir: Path, exe_name: str) -> Path | None:
    """Verify a specific .exe was created in the output folder."""
    expected_exe = output_dir / exe_name

    if expected_exe.is_file():
        size = expected_exe.stat().st_size
        success(f"{exe_name} created ({fmt_size(size)})")
        return expected_exe

    fail(f"{exe_name} not found at expected path")
    return None


def verify_internal_folder(output_dir: Path) -> bool:
    internal = output_dir / "_internal"

    if not internal.is_dir():
        fail("_internal/ folder missing")
        return False

    critical_patterns = [
        ("python3*.dll", "Python runtime"),
        ("base_library.zip", "Compressed stdlib"),
        ("_tkinter*.pyd", "Tkinter C extension"),
        ("SDL2.dll", "pygame SDL2 core"),
    ]

    all_present = True
    for pattern, desc in critical_patterns:
        matches = list(internal.glob(pattern))
        if matches:
            pass  # OK, don't spam output
        else:
            fail(f"Missing critical file: _internal/{pattern}", desc)
            all_present = False

    if all_present:
        success("_internal/ folder contains all critical files")

    return all_present


# ═══════════════════════════════════════════════════════════════════════════
#  COPY CONFIG FILES (with diagnostics flag set per profile)
# ═══════════════════════════════════════════════════════════════════════════

def copy_config_files(config_src: Path, output_dir: Path,
                       diag_enabled: bool, include_presets: bool) -> bool:
    """
    Copy config files into the output folder.
    If diag_enabled is True, modify default.toml to set diagnostics on.
    """
    config_dst = output_dir / "config"
    config_dst.mkdir(exist_ok=True)

    required_files = ['default.toml', 'EXAMPLES.toml', 'README.md']
    all_copied = True

    for fname in required_files:
        src = config_src / fname
        dst = config_dst / fname
        try:
            shutil.copy2(src, dst)

            # Modify default.toml's diagnostics setting per profile
            if fname == "default.toml":
                modified = modify_diagnostics_setting(dst, diag_enabled)
                if modified:
                    state = "ENABLED" if diag_enabled else "DISABLED"
                    success(f"config/{fname}  (diagnostics set to {state})")
                else:
                    success(f"config/{fname}")
            else:
                success(f"config/{fname}")
        except Exception as e:
            fail(f"Could not copy config/{fname}: {e}")
            all_copied = False

    # Copy presets folder if requested and exists
    if include_presets:
        presets_src = config_src / "presets"
        if presets_src.is_dir():
            presets_dst = config_dst / "presets"
            presets_dst.mkdir(exist_ok=True)
            shipped_count = 0
            for f in presets_src.iterdir():
                if f.is_file():
                    try:
                        shutil.copy2(f, presets_dst / f.name)
                        shipped_count += 1
                    except Exception as e:
                        warn(f"Could not copy preset {f.name}: {e}")
            if shipped_count > 0:
                success(f"config/presets/  ({shipped_count} file(s))")

    return all_copied


def modify_diagnostics_setting(toml_path: Path, enabled: bool) -> bool:
    """
    Read default.toml and set the diagnostics enabled flag.
    Returns True if modified, False if no change needed.
    """
    try:
        with open(toml_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        new_lines = []
        in_diagnostics_section = False
        modified = False

        for line in lines:
            stripped = line.strip()

            # Detect entering [diagnostics] section
            if stripped == "[diagnostics]":
                in_diagnostics_section = True
                new_lines.append(line)
                continue

            # Detect leaving [diagnostics] section (entering another section)
            if (in_diagnostics_section and stripped.startswith("[") and
                    not stripped.startswith("[diagnostics")):
                in_diagnostics_section = False

            # If in diagnostics section, find and modify "enabled = X"
            if in_diagnostics_section and stripped.startswith("enabled"):
                if "=" in stripped:
                    new_value = "true" if enabled else "false"
                    new_line = f"enabled = {new_value}\n"
                    new_lines.append(new_line)
                    modified = True
                    continue

            new_lines.append(line)

        if modified:
            with open(toml_path, "w", encoding="utf-8") as f:
                f.writelines(new_lines)

        return modified
    except Exception as e:
        warn(f"Could not modify diagnostics setting: {e}")
        return False


# ═══════════════════════════════════════════════════════════════════════════
#  COPY DOCS AND README
# ═══════════════════════════════════════════════════════════════════════════

def copy_docs_folder(project_root: Path, output_dir: Path) -> bool:
    docs_src = project_root / "docs"
    if not docs_src.is_dir():
        warn("docs/ folder not found in project — skipping")
        return False

    docs_dst = output_dir / "docs"
    try:
        if docs_dst.exists():
            shutil.rmtree(docs_dst)
        shutil.copytree(docs_src, docs_dst)
        file_count = sum(1 for _ in docs_dst.rglob("*") if _.is_file())
        success(f"docs/  ({file_count} files)")
        return True
    except Exception as e:
        warn(f"Could not copy docs folder: {e}")
        return False


def copy_readme(project_root: Path, output_dir: Path) -> bool:
    readme_src = project_root / "README.md"
    if not readme_src.is_file():
        warn("README.md not found in project root — skipping")
        return False

    try:
        shutil.copy2(readme_src, output_dir / "README.md")
        success("README.md")
        return True
    except Exception as e:
        warn(f"Could not copy README.md: {e}")
        return False


# ═══════════════════════════════════════════════════════════════════════════
#  CLEANUP
# ═══════════════════════════════════════════════════════════════════════════

def cleanup_intermediate(project_root: Path):
    build_dir = project_root / "build"
    if build_dir.is_dir():
        try:
            shutil.rmtree(build_dir)
            success("Removed build/ folder")
        except Exception as e:
            warn(f"Could not clean build/: {e}")


# ═══════════════════════════════════════════════════════════════════════════
#  FINAL REPORT
# ═══════════════════════════════════════════════════════════════════════════

def print_final_report(output_dir: Path, profile: dict, version: str,
                       total_time: float):
    folder_size = get_folder_size_mb(output_dir)

    print(f"\n{C.BOLD}{'═' * 64}{C.END}")
    print(f"{C.OK}{C.BOLD}  ✅  BUILD SUCCESSFUL — v{version} ({profile['name']}){C.END}")
    print(f"{C.BOLD}{'═' * 64}{C.END}")

    print(f"\n  {C.BOLD}Output:{C.END}")
    print(f"    Folder:     {output_dir}")
    print(f"    Total size: {folder_size:.1f} MB")
    print(f"    Build time: {total_time:.1f}s")

    print(f"\n  {C.BOLD}Bundled binaries:{C.END}")
    fx_exe = output_dir / "FX_Machine.exe"
    if fx_exe.is_file():
        print(f"    ✓ FX_Machine.exe              ({fmt_size(fx_exe.stat().st_size)})")
    if profile["analyze_session"]:
        as_exe = output_dir / "Analyze_Session.exe"
        if as_exe.is_file():
            print(f"    ✓ Analyze_Session.exe         ({fmt_size(as_exe.stat().st_size)})")

    print(f"\n  {C.BOLD}Bundled config files:{C.END}")
    config_dst = output_dir / "config"
    for fname in ['default.toml', 'EXAMPLES.toml', 'README.md']:
        path = config_dst / fname
        if path.is_file():
            print(f"    ✓ config/{fname}")
    if profile["presets"] and (config_dst / "presets").is_dir():
        presets_count = sum(1 for _ in (config_dst / "presets").iterdir() if _.is_file())
        print(f"    ✓ config/presets/  ({presets_count} file(s))")

    if profile["docs"] and (output_dir / "docs").is_dir():
        print(f"\n  {C.BOLD}Bundled documentation:{C.END}")
        doc_count = sum(1 for _ in (output_dir / "docs").rglob("*") if _.is_file())
        print(f"    ✓ docs/  ({doc_count} files)")
    if profile["readme"] and (output_dir / "README.md").is_file():
        print(f"    ✓ README.md")

    diag_status = "ENABLED" if profile["diag_enabled"] else "DISABLED"
    diag_color = C.OK if profile["diag_enabled"] else C.WARN
    print(f"\n  {C.BOLD}Diagnostics in shipped config:{C.END} {diag_color}{diag_status}{C.END}")
    print(f"    {C.DIM}User can change in config/active.toml after install.{C.END}")

    print(f"\n  {C.BOLD}To run the app:{C.END}")
    print(f"    Double-click:  {output_dir / 'FX_Machine.exe'}")

    if profile["analyze_session"]:
        print(f"\n  {C.BOLD}To analyze a past session:{C.END}")
        print(f"    Double-click:  {output_dir / 'Analyze_Session.exe'}")
        print(f"    {C.DIM}Reads logs/diagnostics.jsonl and produces a report.{C.END}")
        print(f"    {C.DIM}Report saved to logs/session_analysis_TIMESTAMP.txt{C.END}")

    print(f"\n  {C.BOLD}To distribute:{C.END}")
    print(f"    1. Zip the entire {output_dir.name}/ folder")
    print(f"    2. Share the .zip file (~{folder_size:.0f} MB)")
    print(f"    3. Recipients unzip and run FX_Machine.exe — no install needed")
    print(f"    4. Recipients need: Windows 10/11, Ableton Live + AbletonOSC, USB gamepad")

    print(f"\n  {C.BOLD}Recommended next step:{C.END}")
    print(f"    Verify the build is complete:")
    print(f"      {C.INFO}python inspect_exe.py{C.END}")

    print(f"\n{C.BOLD}{'═' * 64}{C.END}\n")


# ═══════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════

def parse_args():
    parser = argparse.ArgumentParser(
        description="Interactive build wizard for FX Machine.",
    )
    parser.add_argument(
        "--version", action="store_true",
        help="Print FX Machine version and exit",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    start_time = time.time()

    project_root = Path(__file__).resolve().parent
    config_src   = project_root / "config"
    output_dir   = project_root / "dist" / "FX_Machine"

    fx_spec      = project_root / "FX_Machine.spec"
    analyze_spec = project_root / "Analyze_Session.spec"

    version = detect_version(project_root)

    if args.version:
        print(f"FX Machine version: {version}")
        sys.exit(0)

    banner()
    print(f"\n  {C.DIM}Project root: {project_root}{C.END}")
    print(f"  {C.DIM}Version:      {version}{C.END}")

    # ───────────────────────────────────────────────────────────────────────
    #  Step 1: Pre-flight checks
    # ───────────────────────────────────────────────────────────────────────
    header("Step 1 — Pre-flight checks")

    if not check_pyinstaller():
        sys.exit(1)

    if not check_dependencies():
        fail("Missing required dependencies — install them and retry")
        sys.exit(1)

    if not check_source_files(project_root):
        fail("Critical source files missing — cannot build")
        sys.exit(1)

    # ───────────────────────────────────────────────────────────────────────
    #  Step 2: Verify config files
    # ───────────────────────────────────────────────────────────────────────
    header("Step 2 — Verify config files")

    config_ok, missing = check_config_files(config_src)
    if not config_ok:
        fail("Cannot build — required config files missing")
        for m in missing:
            print(f"        - {m}")
        sys.exit(1)

    # ───────────────────────────────────────────────────────────────────────
    #  Step 3 + 4: Interactive wizard (profile selection and confirmation)
    # ───────────────────────────────────────────────────────────────────────
    profile = run_wizard(project_root)

    # ───────────────────────────────────────────────────────────────────────
    #  Step 5: Generate spec files (if missing)
    # ───────────────────────────────────────────────────────────────────────
    header("Step 5 — Verify or generate spec files")

    if not fx_spec.is_file():
        info(f"Generating {fx_spec.name}...")
        if not generate_fx_machine_spec(project_root, fx_spec):
            fail("Could not generate FX_Machine.spec")
            sys.exit(1)
    else:
        success(f"{fx_spec.name} found")

    if profile["analyze_session"]:
        if not analyze_spec.is_file():
            info(f"Generating {analyze_spec.name}...")
            if not generate_analyze_session_spec(project_root, analyze_spec):
                fail("Could not generate Analyze_Session.spec")
                sys.exit(1)
        else:
            success(f"{analyze_spec.name} found")

    # ───────────────────────────────────────────────────────────────────────
    #  Step 6: Clean previous artifacts
    # ───────────────────────────────────────────────────────────────────────
    header("Step 6 — Clean previous build artifacts")
    clean_artifacts(project_root)

    # ───────────────────────────────────────────────────────────────────────
    #  Step 7: Build FX_Machine.exe
    # ───────────────────────────────────────────────────────────────────────
    header("Step 7 — Build FX_Machine.exe")
    if not run_pyinstaller(project_root, fx_spec, "FX_Machine"):
        sys.exit(3)

    if not verify_exe_created(output_dir, "FX_Machine.exe"):
        sys.exit(4)

    if not verify_internal_folder(output_dir):
        sys.exit(4)

    # ───────────────────────────────────────────────────────────────────────
    #  Step 8: Build Analyze_Session.exe (if selected)
    # ───────────────────────────────────────────────────────────────────────
    if profile["analyze_session"]:
        header("Step 8 — Build Analyze_Session.exe")
        if not run_pyinstaller(project_root, analyze_spec, "Analyze_Session"):
            sys.exit(3)

        analyze_output = project_root / "dist" / "Analyze_Session"
        if not verify_exe_created(analyze_output, "Analyze_Session.exe"):
            sys.exit(4)

        # Copy Analyze_Session.exe into FX_Machine bundle and discard its
        # separate _internal/ folder (FX_Machine's _internal/ is identical)
        if not copy_analyze_session_to_main(project_root):
            sys.exit(4)

    # ───────────────────────────────────────────────────────────────────────
    #  Step 9: Copy config files
    # ───────────────────────────────────────────────────────────────────────
    header("Step 9 — Copy config files into output folder")
    if not copy_config_files(config_src, output_dir,
                              profile["diag_enabled"], profile["presets"]):
        warn("Some config files failed to copy")

    # ───────────────────────────────────────────────────────────────────────
    #  Step 10: Copy docs and README (if selected)
    # ───────────────────────────────────────────────────────────────────────
    if profile["docs"] or profile["readme"]:
        header("Step 10 — Copy documentation")
        if profile["docs"]:
            copy_docs_folder(project_root, output_dir)
        if profile["readme"]:
            copy_readme(project_root, output_dir)

    # ───────────────────────────────────────────────────────────────────────
    #  Step 11: Cleanup intermediate files
    # ───────────────────────────────────────────────────────────────────────
    header("Step 11 — Cleanup intermediate artifacts")
    cleanup_intermediate(project_root)

    # ───────────────────────────────────────────────────────────────────────
    #  Step 12: Final report
    # ───────────────────────────────────────────────────────────────────────
    total_time = time.time() - start_time
    print_final_report(output_dir, profile, version, total_time)

    sys.exit(0)


if __name__ == "__main__":
    main()