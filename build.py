#!/usr/bin/env python3
"""
================================================================================
  build.py — FX Machine Interactive Build Wizard
================================================================================
  Interactive installer-style build script for FX Machine v1.0.0.

  Usage:
      python build.py                  # interactive wizard
      python build.py --version        # print version info and exit

  Build profiles:
      1. MINIMAL    Just FX_Machine.exe + config (~40 MB)
      2. STANDARD   FX_Machine.exe + Analyze_Session.exe + config (~50 MB)
      3. FULL       Everything in STANDARD + docs/ + README.md (~52 MB)
      4. CUSTOM     Choose each component individually.

  Build process:
      Steps 1-2:   Pre-flight checks (PyInstaller, deps, config files)
      Steps 3-4:   Interactive wizard (profile selection + confirmation)
      Step 5:      Generate spec files if missing
      Step 6:      Clean previous build artifacts
      Step 7:      Build FX_Machine.exe via PyInstaller
      Step 8:      Build Analyze_Session.exe if selected
      Step 9:      Copy config files (with diagnostics flag set per profile)
      Step 10:     Copy docs and README if selected
      Step 11:     Cleanup intermediate artifacts
      Step 12:     Run the build inspector for independent verification
      Step 13:     Final report + pause for user to read results

  Exit codes:
      0 = build succeeded and inspector passed
      1 = pre-flight check failed
      2 = user cancelled the wizard
      3 = PyInstaller failed or inspector found errors
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

FX_MACHINE_HIDDEN_IMPORTS = [
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
    "psutil",
    "psutil._psutil_windows",
    "pythonosc.dispatcher",
    "pythonosc.osc_server",
    "pythonosc.udp_client",
    "pythonosc.osc_message",
    "pythonosc.osc_message_builder",
    "tomllib",
]

ANALYZE_SESSION_HIDDEN_IMPORTS = [
    "src.diagnostics",
    "src.diagnostics.analyzer",
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

def wait_for_keypress():
    """Pause so user can read results before console closes."""
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
#  USER INPUT HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def ask_yes_no(prompt: str, default: bool = True) -> bool:
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
                        value = parts[1].strip().split("#")[0].strip()
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
        except Exception:
            pass
        return True
    except ImportError:
        fail("PyInstaller is not installed", "Run:  pip install pyinstaller")
        return False


def check_dependencies() -> bool:
    all_ok = True
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

    try:
        import psutil
        success(f"psutil {psutil.__version__}")
    except ImportError:
        warn("psutil not installed — diagnostics will run in degraded mode")

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
            success(f"config/{fname}  ({fmt_size(path.stat().st_size)})")
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
    print(f"\n  {C.BOLD}Choose a build profile:{C.END}\n")

    print(f"    {C.BOLD}1. MINIMAL{C.END}     "
          f"Just FX_Machine.exe + config (~40 MB)")
    print(f"                  {C.DIM}Diagnostics OFF by default.{C.END}")
    print(f"                  {C.DIM}Smallest download for end users.{C.END}")
    print()
    print(f"    {C.BOLD}2. STANDARD{C.END}    "
          f"FX_Machine.exe + Analyze_Session.exe + config (~50 MB)")
    print(f"                  {C.DIM}Diagnostics ON by default.{C.END}")
    print(f"                  {C.OK}RECOMMENDED for distribution.{C.END}")
    print()
    print(f"    {C.BOLD}3. FULL{C.END}        "
          f"STANDARD + docs/ + README.md (~52 MB)")
    print(f"                  {C.DIM}Diagnostics ON by default.{C.END}")
    print(f"                  {C.DIM}Complete build with all documentation.{C.END}")
    print()
    print(f"    {C.BOLD}4. CUSTOM{C.END}      "
          f"Choose each component individually")
    print()


def show_component(included: bool, name: str, desc: str):
    icon = f"{C.OK}✓{C.END}" if included else f"{C.DIM}✗{C.END}"
    name_color = C.BOLD if included else C.DIM
    desc_color = "" if included else C.DIM
    print(f"    {icon} {name_color}{name:30}{C.END} {desc_color}{desc}{C.END}")


def run_custom_wizard() -> dict:
    print(f"\n  {C.BOLD}Custom build configuration{C.END}\n")
    print(f"  {C.DIM}For each component, answer y/n. Defaults shown in caps.{C.END}\n")
    return {
        "fx_machine": True,
        "analyze_session": ask_yes_no(
            "Include Analyze_Session.exe (post-session analyzer)?", default=True),
        "docs": ask_yes_no(
            "Include docs/ folder (9 guides)?", default=False),
        "readme": ask_yes_no(
            "Include main README.md in distribution?", default=True),
        "presets": ask_yes_no(
            "Include config/presets/ folder?", default=True),
        "diag_enabled": ask_yes_no(
            "Enable diagnostics by default in shipped config?", default=True),
    }


def run_wizard(project_root: Path) -> dict:
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
        sys.exit(2)

    header("Step 4 — Confirm selection")
    print(f"\n  Profile: {C.BOLD}{profile['name']}{C.END}\n")
    print(f"  Components to bundle:")
    show_component(True, "FX_Machine.exe", "main app (always included)")
    show_component(profile["analyze_session"], "Analyze_Session.exe",
                   "post-session analyzer")
    show_component(profile["docs"], "docs/ folder", "9 detailed guides")
    show_component(profile["readme"], "README.md", "main project README")
    show_component(profile["presets"], "config/presets/", "preset profiles")
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


# ═══════════════════════════════════════════════════════════════════════════
#  SPEC FILE GENERATION
# ═══════════════════════════════════════════════════════════════════════════

def generate_fx_machine_spec(project_root: Path, spec_file: Path) -> bool:
    imports_str = ",\n        ".join(f'"{imp}"' for imp in FX_MACHINE_HIDDEN_IMPORTS)
    spec_content = f'''# -*- mode: python ; coding: utf-8 -*-
"""FX_Machine.spec — Generated by build.py"""
block_cipher = None
a = Analysis(
    ['run.py'], pathex=[], binaries=[], datas=[],
    hiddenimports=[{imports_str}],
    hookspath=[], hooksconfig={{}}, runtime_hooks=[],
    excludes=['matplotlib','numpy','pandas','PIL','PyQt5','PyQt6',
              'PySide2','PySide6','IPython','jupyter','pytest'],
    win_no_prefer_redirects=False, win_private_assemblies=False,
    cipher=block_cipher, noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True,
    name='FX_Machine', debug=False, strip=False, upx=False,
    console=False, disable_windowed_traceback=False)
coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas,
    strip=False, upx=False, name='FX_Machine')
'''
    try:
        with open(spec_file, "w", encoding="utf-8") as f:
            f.write(spec_content)
        success(f"Generated {spec_file.name}")
        return True
    except Exception as e:
        fail(f"Could not write spec file: {e}")
        return False


def generate_analyze_session_spec(project_root: Path, spec_file: Path) -> bool:
    imports_str = ",\n        ".join(f'"{imp}"' for imp in ANALYZE_SESSION_HIDDEN_IMPORTS)
    spec_content = f'''# -*- mode: python ; coding: utf-8 -*-
"""Analyze_Session.spec — Generated by build.py"""
block_cipher = None
a = Analysis(
    ['analyze_diagnostics.py'], pathex=[], binaries=[], datas=[],
    hiddenimports=[{imports_str}],
    hookspath=[], hooksconfig={{}}, runtime_hooks=[],
    excludes=['matplotlib','numpy','pandas','PIL','PyQt5','PyQt6',
              'PySide2','PySide6','IPython','jupyter','pytest',
              'pygame','tkinter','pythonosc'],
    win_no_prefer_redirects=False, win_private_assemblies=False,
    cipher=block_cipher, noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True,
    name='Analyze_Session', debug=False, strip=False, upx=False,
    console=True, disable_windowed_traceback=False)
coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas,
    strip=False, upx=False, name='Analyze_Session')
'''
    try:
        with open(spec_file, "w", encoding="utf-8") as f:
            f.write(spec_content)
        success(f"Generated {spec_file.name}")
        return True
    except Exception as e:
        fail(f"Could not write spec file: {e}")
        return False


# ═══════════════════════════════════════════════════════════════════════════
#  CLEAN BUILD ARTIFACTS
# ═══════════════════════════════════════════════════════════════════════════

def clean_artifacts(project_root: Path):
    items = [
        ("dist/FX_Machine/", project_root / "dist" / "FX_Machine"),
        ("dist/Analyze_Session/", project_root / "dist" / "Analyze_Session"),
        ("build/", project_root / "build"),
    ]
    cleaned = 0
    for label, path in items:
        if path.exists():
            try:
                shutil.rmtree(path)
                success(f"Removed {label}")
                cleaned += 1
            except Exception as e:
                warn(f"Could not remove {label}: {e}")

    src_dir = project_root / "src"
    if src_dir.is_dir():
        pc = 0
        for pycache in src_dir.rglob("__pycache__"):
            try:
                shutil.rmtree(pycache)
                pc += 1
            except Exception:
                pass
        if pc > 0:
            success(f"Removed {pc} __pycache__ folder(s)")

    if cleaned == 0:
        info("Nothing to clean")


# ═══════════════════════════════════════════════════════════════════════════
#  RUN PYINSTALLER
# ═══════════════════════════════════════════════════════════════════════════

def run_pyinstaller(project_root: Path, spec_file: Path, label: str) -> bool:
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", str(spec_file),
    ]
    info(f"Building {label} (1-3 minutes)...")
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

    success(f"{label} completed in {elapsed:.1f}s")
    return True


# ═══════════════════════════════════════════════════════════════════════════
#  COPY ANALYZE_SESSION TO MAIN BUNDLE
# ═══════════════════════════════════════════════════════════════════════════

def copy_analyze_session_to_main(project_root: Path) -> bool:
    src_exe = project_root / "dist" / "Analyze_Session" / "Analyze_Session.exe"
    dst_exe = project_root / "dist" / "FX_Machine" / "Analyze_Session.exe"

    if not src_exe.is_file():
        fail(f"Analyze_Session.exe not found at {src_exe}")
        return False

    try:
        shutil.copy2(src_exe, dst_exe)
        success("Copied Analyze_Session.exe to main bundle")

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
    expected_exe = output_dir / exe_name
    if expected_exe.is_file():
        success(f"{exe_name} created ({fmt_size(expected_exe.stat().st_size)})")
        return expected_exe
    fail(f"{exe_name} not found at expected path")
    return None


def verify_internal_folder(output_dir: Path) -> bool:
    internal = output_dir / "_internal"
    if not internal.is_dir():
        fail("_internal/ folder missing")
        return False

    critical = [
        ("python3*.dll", "Python runtime"),
        ("base_library.zip", "Compressed stdlib"),
        ("_tkinter*.pyd", "Tkinter"),
        ("SDL2.dll", "pygame SDL2"),
    ]
    all_ok = True
    for pattern, desc in critical:
        if not list(internal.glob(pattern)):
            fail(f"Missing: _internal/{pattern}", desc)
            all_ok = False

    if all_ok:
        success("_internal/ contains all critical files")
    return all_ok


# ═══════════════════════════════════════════════════════════════════════════
#  COPY CONFIG FILES
# ═══════════════════════════════════════════════════════════════════════════

def copy_config_files(config_src: Path, output_dir: Path,
                       diag_enabled: bool, include_presets: bool) -> bool:
    config_dst = output_dir / "config"
    config_dst.mkdir(exist_ok=True)

    required_files = ['default.toml', 'EXAMPLES.toml', 'README.md']
    all_copied = True

    for fname in required_files:
        src = config_src / fname
        dst = config_dst / fname
        try:
            shutil.copy2(src, dst)
            if fname == "default.toml":
                modified = modify_diagnostics_setting(dst, diag_enabled)
                state = "ENABLED" if diag_enabled else "DISABLED"
                if modified:
                    success(f"config/{fname}  (diagnostics {state})")
                else:
                    success(f"config/{fname}")
            else:
                success(f"config/{fname}")
        except Exception as e:
            fail(f"Could not copy config/{fname}: {e}")
            all_copied = False

    if include_presets:
        presets_src = config_src / "presets"
        if presets_src.is_dir():
            presets_dst = config_dst / "presets"
            presets_dst.mkdir(exist_ok=True)
            count = 0
            for f in presets_src.iterdir():
                if f.is_file():
                    try:
                        shutil.copy2(f, presets_dst / f.name)
                        count += 1
                    except Exception:
                        pass
            if count > 0:
                success(f"config/presets/  ({count} file(s))")

    return all_copied


def modify_diagnostics_setting(toml_path: Path, enabled: bool) -> bool:
    try:
        with open(toml_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        new_lines = []
        in_diag = False
        modified = False

        for line in lines:
            stripped = line.strip()
            if stripped == "[diagnostics]":
                in_diag = True
                new_lines.append(line)
                continue
            if in_diag and stripped.startswith("[") and not stripped.startswith("[diagnostics"):
                in_diag = False
            if in_diag and stripped.startswith("enabled") and "=" in stripped:
                new_lines.append(f"enabled = {'true' if enabled else 'false'}\n")
                modified = True
                continue
            new_lines.append(line)

        if modified:
            with open(toml_path, "w", encoding="utf-8") as f:
                f.writelines(new_lines)
        return modified
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════════════════════
#  COPY DOCS AND README
# ═══════════════════════════════════════════════════════════════════════════

def copy_docs_folder(project_root: Path, output_dir: Path) -> bool:
    docs_src = project_root / "docs"
    if not docs_src.is_dir():
        warn("docs/ folder not found — skipping")
        return False
    docs_dst = output_dir / "docs"
    try:
        if docs_dst.exists():
            shutil.rmtree(docs_dst)
        shutil.copytree(docs_src, docs_dst)
        fc = sum(1 for _ in docs_dst.rglob("*") if _.is_file())
        success(f"docs/  ({fc} files)")
        return True
    except Exception as e:
        warn(f"Could not copy docs/: {e}")
        return False


def copy_readme(project_root: Path, output_dir: Path) -> bool:
    readme_src = project_root / "README.md"
    if not readme_src.is_file():
        warn("README.md not found — skipping")
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
#  RUN BUILD INSPECTOR
# ═══════════════════════════════════════════════════════════════════════════

def run_inspector(project_root: Path, output_dir: Path) -> bool:
    """
    Run inspect_exe.py as a subprocess for independent build verification.

    Returns True if inspector passed (exit code 0 or 1), False if errors found.
    The inspector runs without --quiet so all checks are visible, and with
    --no-pause because we handle the pause ourselves at the end of build.py.
    """
    inspector_script = project_root / "inspect_exe.py"

    if not inspector_script.is_file():
        warn("inspect_exe.py not found — skipping build verification")
        warn("Build may be complete but hasn't been independently verified")
        return True

    exe_path = output_dir / "FX_Machine.exe"
    cmd = [
        sys.executable,
        str(inspector_script),
        "--exe", str(exe_path),
        "--no-pause",
    ]

    try:
        result = subprocess.run(cmd, cwd=str(project_root))

        if result.returncode == 0:
            print()
            success("Build inspector: ALL CHECKS PASSED")
            return True
        elif result.returncode == 1:
            print()
            warn("Build inspector: WARNINGS found (build is functional)")
            return True
        else:
            print()
            fail("Build inspector: ERRORS found",
                 "The build has issues that should be fixed before shipping.")
            return False
    except Exception as e:
        warn(f"Could not run build inspector: {e}")
        return True


# ═══════════════════════════════════════════════════════════════════════════
#  FINAL REPORT
# ═══════════════════════════════════════════════════════════════════════════

def print_final_report(output_dir: Path, profile: dict, version: str,
                       total_time: float, inspector_passed: bool = True):
    folder_size = get_folder_size_mb(output_dir)

    print(f"\n{C.BOLD}{'═' * 64}{C.END}")
    if inspector_passed:
        print(f"{C.OK}{C.BOLD}  ✅  BUILD SUCCESSFUL — v{version} ({profile['name']}){C.END}")
    else:
        print(f"{C.WARN}{C.BOLD}  ⚠  BUILD COMPLETED WITH ISSUES — v{version} ({profile['name']}){C.END}")
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

    print(f"\n  {C.BOLD}Bundled config:{C.END}")
    config_dst = output_dir / "config"
    for fname in ['default.toml', 'EXAMPLES.toml', 'README.md']:
        if (config_dst / fname).is_file():
            print(f"    ✓ config/{fname}")
    if profile["presets"] and (config_dst / "presets").is_dir():
        pc = sum(1 for _ in (config_dst / "presets").iterdir() if _.is_file())
        print(f"    ✓ config/presets/  ({pc} file(s))")

    if profile["docs"] and (output_dir / "docs").is_dir():
        dc = sum(1 for _ in (output_dir / "docs").rglob("*") if _.is_file())
        print(f"\n  {C.BOLD}Documentation:{C.END}")
        print(f"    ✓ docs/  ({dc} files)")
    if profile["readme"] and (output_dir / "README.md").is_file():
        print(f"    ✓ README.md")

    diag_status = "ENABLED" if profile["diag_enabled"] else "DISABLED"
    diag_color = C.OK if profile["diag_enabled"] else C.WARN
    print(f"\n  {C.BOLD}Diagnostics:{C.END} {diag_color}{diag_status}{C.END}")

    print(f"\n  {C.BOLD}To run:{C.END}")
    print(f"    {output_dir / 'FX_Machine.exe'}")

    if profile["analyze_session"]:
        print(f"\n  {C.BOLD}To analyze a past session:{C.END}")
        print(f"    {output_dir / 'Analyze_Session.exe'}")

    print(f"\n  {C.BOLD}To distribute:{C.END}")
    print(f"    Zip the entire {output_dir.name}/ folder (~{folder_size:.0f} MB)")
    print(f"    Recipients unzip and run FX_Machine.exe — no install needed")

    if inspector_passed:
        print(f"\n  {C.BOLD}Next step:{C.END}")
        print(f"    Test the built .exe:")
        print(f"      {C.INFO}{output_dir / 'FX_Machine.exe'}{C.END}")
    else:
        print(f"\n  {C.BOLD}Next step:{C.END}")
        print(f"    Fix the issues reported by the inspector above,")
        print(f"    then rebuild:")
        print(f"      {C.INFO}python build.py{C.END}")

    print(f"\n{C.BOLD}{'═' * 64}{C.END}")


# ═══════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════

def parse_args():
    parser = argparse.ArgumentParser(
        description="Interactive build wizard for FX Machine.",
    )
    parser.add_argument("--version", action="store_true",
                        help="Print version and exit")
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

    # Step 1: Pre-flight checks
    header("Step 1 — Pre-flight checks")
    if not check_pyinstaller():
        sys.exit(1)
    if not check_dependencies():
        fail("Missing required dependencies")
        sys.exit(1)
    if not check_source_files(project_root):
        fail("Critical source files missing")
        sys.exit(1)

    # Step 2: Verify config files
    header("Step 2 — Verify config files")
    config_ok, missing = check_config_files(config_src)
    if not config_ok:
        fail("Required config files missing")
        sys.exit(1)

    # Steps 3-4: Interactive wizard
    profile = run_wizard(project_root)

    # Step 5: Spec files
    header("Step 5 — Verify or generate spec files")
    if not fx_spec.is_file():
        info(f"Generating {fx_spec.name}...")
        if not generate_fx_machine_spec(project_root, fx_spec):
            sys.exit(1)
    else:
        success(f"{fx_spec.name} found")

    if profile["analyze_session"]:
        if not analyze_spec.is_file():
            info(f"Generating {analyze_spec.name}...")
            if not generate_analyze_session_spec(project_root, analyze_spec):
                sys.exit(1)
        else:
            success(f"{analyze_spec.name} found")

    # Step 6: Clean
    header("Step 6 — Clean previous build artifacts")
    clean_artifacts(project_root)

    # Step 7: Build FX_Machine.exe
    header("Step 7 — Build FX_Machine.exe")
    if not run_pyinstaller(project_root, fx_spec, "FX_Machine"):
        wait_for_keypress()
        sys.exit(3)
    if not verify_exe_created(output_dir, "FX_Machine.exe"):
        wait_for_keypress()
        sys.exit(4)
    if not verify_internal_folder(output_dir):
        wait_for_keypress()
        sys.exit(4)

    # Step 8: Build Analyze_Session.exe (if selected)
    if profile["analyze_session"]:
        header("Step 8 — Build Analyze_Session.exe")
        if not run_pyinstaller(project_root, analyze_spec, "Analyze_Session"):
            wait_for_keypress()
            sys.exit(3)
        analyze_output = project_root / "dist" / "Analyze_Session"
        if not verify_exe_created(analyze_output, "Analyze_Session.exe"):
            wait_for_keypress()
            sys.exit(4)
        if not copy_analyze_session_to_main(project_root):
            wait_for_keypress()
            sys.exit(4)

    # Step 9: Copy config files
    header("Step 9 — Copy config files")
    copy_config_files(config_src, output_dir,
                      profile["diag_enabled"], profile["presets"])

    # Step 10: Copy docs and README
    if profile["docs"] or profile["readme"]:
        header("Step 10 — Copy documentation")
        if profile["docs"]:
            copy_docs_folder(project_root, output_dir)
        if profile["readme"]:
            copy_readme(project_root, output_dir)

    # Step 11: Cleanup
    header("Step 11 — Cleanup intermediate artifacts")
    cleanup_intermediate(project_root)

    # Step 12: Run inspector
    header("Step 12 — Verify build integrity")
    info("Running the build inspector for independent verification...")
    print()
    inspector_passed = run_inspector(project_root, output_dir)

    # Step 13: Final report
    total_time = time.time() - start_time
    print_final_report(output_dir, profile, version, total_time,
                       inspector_passed)

    # Pause so user can read the results
    wait_for_keypress()

    sys.exit(0 if inspector_passed else 3)


if __name__ == "__main__":
    main()