#!/usr/bin/env python3
"""
================================================================================
  clean.py — FX Machine Project Cleanup Script
================================================================================
  Removes all generated artifacts, temporary files, caches, and optional
  logs from the project directory. Brings the project back to a clean
  source-only state for a fresh build, git commit, or distribution.

  Usage:
      python clean.py                 # interactive — asks what to clean
      python clean.py --all           # remove everything (no prompts)
      python clean.py --build         # remove only build artifacts
      python clean.py --logs          # remove only log files
      python clean.py --cache         # remove only __pycache__ folders
      python clean.py --config        # remove only active.toml (user config)
      python clean.py --specs         # remove generated .spec files
      python clean.py --dry-run       # show what WOULD be removed, don't delete

  Flags can be combined:
      python clean.py --build --logs  # remove builds + logs
      python clean.py --all --dry-run # show what --all would remove

  What each category contains:

    BUILD ARTIFACTS:
      dist/                       PyInstaller output folder
      build/                      PyInstaller intermediate files
      *.spec                      Generated spec files (FX_Machine.spec, Analyze_Session.spec)

    PYTHON CACHES:
      __pycache__/                Every __pycache__ folder in the project tree
      *.pyc                       Compiled bytecode files
      *.pyo                       Optimized bytecode files

    LOG FILES:
      logs/fxmachine.log*         Main app log + rotated backups
      logs/diagnostics.log*       Diagnostics text log + rotated backups
      logs/diagnostics.jsonl*     Diagnostics JSONL log + rotated backups
      logs/session_analysis_*     Analyzer output reports
      logs/.diagnose_write_test   Temporary file from diagnose.py

    USER CONFIG:
      config/active.toml          User's edited config (regenerated on launch)
      config/presets/*.toml        User-saved presets (CAREFUL — these are personal)

    TEMPORARY / DEBUG FILES:
      debug_pyz*.py               Leftover diagnostic scripts
      commit_msg.txt              Leftover commit message files
      *.backup, *.bak             Backup files

  Safety rules:
    - NEVER deletes source code (src/, run.py, etc.)
    - NEVER deletes default.toml, EXAMPLES.toml, or config/README.md
    - NEVER deletes docs/ content
    - NEVER deletes .git/ or .gitignore
    - Presets are only deleted with explicit --config or --all flag
    - In interactive mode, asks before each category

  Exit codes:
      0 = cleanup completed successfully
      1 = error during cleanup
      2 = cancelled by user
================================================================================
"""

import sys
import os
import shutil
import argparse
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
#  HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def info(msg: str):
    print(f"  {C.INFO}ℹ{C.END} {msg}")

def success(msg: str):
    print(f"  {C.OK}✓{C.END} {msg}")

def warn(msg: str):
    print(f"  {C.WARN}⚠{C.END} {msg}")

def fail(msg: str):
    print(f"  {C.FAIL}✗{C.END} {msg}")

def header(title: str):
    print(f"\n{C.BOLD}{C.INFO}━━━ {title} ━━━{C.END}")

def banner():
    print(f"\n{C.BOLD}{C.INFO}╔{'═' * 62}╗{C.END}")
    print(f"{C.BOLD}{C.INFO}║{' ' * 14}FX MACHINE — PROJECT CLEANUP{' ' * 20}║{C.END}")
    print(f"{C.BOLD}{C.INFO}╚{'═' * 62}╝{C.END}")

def fmt_size(n: int) -> str:
    if n >= 1024 * 1024:
        return f"{n / (1024 * 1024):.1f} MB"
    if n >= 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n} B"

def folder_size(folder: Path) -> int:
    """Total bytes of all files under folder."""
    total = 0
    try:
        for f in folder.rglob("*"):
            if f.is_file():
                try:
                    total += f.stat().st_size
                except OSError:
                    pass
    except Exception:
        pass
    return total

def file_count(folder: Path) -> int:
    """Count of all files under folder."""
    try:
        return sum(1 for f in folder.rglob("*") if f.is_file())
    except Exception:
        return 0


def ask_yes_no(prompt: str, default: bool = True) -> bool:
    """Interactive yes/no prompt."""
    suffix = "[Y/n]" if default else "[y/N]"
    while True:
        try:
            answer = input(f"  {prompt} {suffix}: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print(f"\n  {C.WARN}Cancelled{C.END}")
            sys.exit(2)
        if not answer:
            return default
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        print(f"  {C.WARN}Please answer yes or no{C.END}")


# ═══════════════════════════════════════════════════════════════════════════
#  CLEANUP CATEGORIES
# ═══════════════════════════════════════════════════════════════════════════
#
#  Each category is a function that:
#    1. Scans for matching files/folders
#    2. Reports what was found (with sizes)
#    3. Deletes them (unless dry_run=True)
#    4. Returns (items_found, items_removed, bytes_freed)
# ═══════════════════════════════════════════════════════════════════════════

def clean_build_artifacts(root: Path, dry_run: bool = False) -> tuple[int, int, int]:
    """Remove dist/, build/, and generated .spec files."""
    found = 0
    removed = 0
    freed = 0

    targets = [
        root / "dist",
        root / "build",
    ]

    for target in targets:
        if target.is_dir():
            size = folder_size(target)
            fc = file_count(target)
            found += 1
            if dry_run:
                info(f"Would remove: {target.name}/  ({fc} files, {fmt_size(size)})")
            else:
                try:
                    shutil.rmtree(target)
                    success(f"Removed {target.name}/  ({fc} files, {fmt_size(size)})")
                    removed += 1
                    freed += size
                except Exception as e:
                    fail(f"Could not remove {target.name}/: {e}")

    # Generated spec files
    spec_files = [
        root / "FX_Machine.spec",
        root / "Analyze_Session.spec",
    ]
    for spec in spec_files:
        if spec.is_file():
            size = spec.stat().st_size
            found += 1
            if dry_run:
                info(f"Would remove: {spec.name}  ({fmt_size(size)})")
            else:
                try:
                    spec.unlink()
                    success(f"Removed {spec.name}  ({fmt_size(size)})")
                    removed += 1
                    freed += size
                except Exception as e:
                    fail(f"Could not remove {spec.name}: {e}")

    return found, removed, freed


def clean_python_caches(root: Path, dry_run: bool = False) -> tuple[int, int, int]:
    """Remove all __pycache__ folders and .pyc/.pyo files."""
    found = 0
    removed = 0
    freed = 0

    # __pycache__ folders
    pycache_dirs = list(root.rglob("__pycache__"))
    # Exclude anything inside .git
    pycache_dirs = [d for d in pycache_dirs if ".git" not in d.parts]

    for pdir in pycache_dirs:
        if pdir.is_dir():
            size = folder_size(pdir)
            found += 1
            if dry_run:
                rel = pdir.relative_to(root)
                info(f"Would remove: {rel}/  ({fmt_size(size)})")
            else:
                try:
                    shutil.rmtree(pdir)
                    rel = pdir.relative_to(root)
                    success(f"Removed {rel}/  ({fmt_size(size)})")
                    removed += 1
                    freed += size
                except Exception as e:
                    fail(f"Could not remove {pdir}: {e}")

    # Stray .pyc and .pyo files (not inside __pycache__)
    for pattern in ("*.pyc", "*.pyo"):
        for pyc_file in root.rglob(pattern):
            if ".git" in pyc_file.parts:
                continue
            if "__pycache__" in pyc_file.parts:
                continue  # already handled above
            size = pyc_file.stat().st_size
            found += 1
            if dry_run:
                rel = pyc_file.relative_to(root)
                info(f"Would remove: {rel}  ({fmt_size(size)})")
            else:
                try:
                    pyc_file.unlink()
                    rel = pyc_file.relative_to(root)
                    success(f"Removed {rel}  ({fmt_size(size)})")
                    removed += 1
                    freed += size
                except Exception as e:
                    fail(f"Could not remove {pyc_file}: {e}")

    return found, removed, freed


def clean_log_files(root: Path, dry_run: bool = False) -> tuple[int, int, int]:
    """Remove all log files from the logs/ folder."""
    found = 0
    removed = 0
    freed = 0

    logs_dir = root / "logs"
    if not logs_dir.is_dir():
        info("logs/ folder doesn't exist (nothing to clean)")
        return 0, 0, 0

    # Patterns to clean
    patterns = [
        "fxmachine.log*",          # main log + rotated backups
        "diagnostics.log*",        # diagnostics text log + rotated
        "diagnostics.jsonl*",      # diagnostics JSONL + rotated
        "session_analysis_*.txt",  # analyzer output reports
        ".diagnose_write_test",    # temporary file from diagnose.py
    ]

    for pattern in patterns:
        for log_file in logs_dir.glob(pattern):
            if log_file.is_file():
                size = log_file.stat().st_size
                found += 1
                if dry_run:
                    info(f"Would remove: logs/{log_file.name}  ({fmt_size(size)})")
                else:
                    try:
                        log_file.unlink()
                        success(f"Removed logs/{log_file.name}  ({fmt_size(size)})")
                        removed += 1
                        freed += size
                    except Exception as e:
                        fail(f"Could not remove logs/{log_file.name}: {e}")

    # Remove empty logs/ folder if it's now empty
    if not dry_run and logs_dir.is_dir():
        try:
            remaining = list(logs_dir.iterdir())
            if not remaining:
                logs_dir.rmdir()
                success("Removed empty logs/ folder")
        except Exception:
            pass

    return found, removed, freed


def clean_user_config(root: Path, dry_run: bool = False) -> tuple[int, int, int]:
    """
    Remove user-specific config files.
    CAREFUL: config/presets/*.toml are the user's personal presets.
    """
    found = 0
    removed = 0
    freed = 0

    # active.toml (always safe to remove — regenerated on next launch)
    active = root / "config" / "active.toml"
    if active.is_file():
        size = active.stat().st_size
        found += 1
        if dry_run:
            info(f"Would remove: config/active.toml  ({fmt_size(size)})")
        else:
            try:
                active.unlink()
                success(f"Removed config/active.toml  ({fmt_size(size)})")
                removed += 1
                freed += size
            except Exception as e:
                fail(f"Could not remove config/active.toml: {e}")

    # User presets — be extra cautious
    presets_dir = root / "config" / "presets"
    if presets_dir.is_dir():
        preset_files = [f for f in presets_dir.iterdir()
                        if f.is_file() and f.suffix == ".toml"]
        if preset_files:
            found += len(preset_files)
            total_size = sum(f.stat().st_size for f in preset_files)
            if dry_run:
                info(f"Would remove: {len(preset_files)} user preset(s) "
                     f"in config/presets/  ({fmt_size(total_size)})")
            else:
                for pf in preset_files:
                    try:
                        size = pf.stat().st_size
                        pf.unlink()
                        success(f"Removed config/presets/{pf.name}  ({fmt_size(size)})")
                        removed += 1
                        freed += size
                    except Exception as e:
                        fail(f"Could not remove config/presets/{pf.name}: {e}")

    return found, removed, freed


def clean_spec_files(root: Path, dry_run: bool = False) -> tuple[int, int, int]:
    """Remove generated .spec files (they can be regenerated by build.py)."""
    found = 0
    removed = 0
    freed = 0

    specs = [
        root / "FX_Machine.spec",
        root / "Analyze_Session.spec",
    ]

    for spec in specs:
        if spec.is_file():
            size = spec.stat().st_size
            found += 1
            if dry_run:
                info(f"Would remove: {spec.name}  ({fmt_size(size)})")
            else:
                try:
                    spec.unlink()
                    success(f"Removed {spec.name}  ({fmt_size(size)})")
                    removed += 1
                    freed += size
                except Exception as e:
                    fail(f"Could not remove {spec.name}: {e}")

    return found, removed, freed


def clean_temp_files(root: Path, dry_run: bool = False) -> tuple[int, int, int]:
    """Remove temporary and debug files that shouldn't be in the repo."""
    found = 0
    removed = 0
    freed = 0

    # Patterns for temporary files in the project root
    temp_patterns = [
        "debug_pyz*.py",        # diagnostic debug scripts
        "commit_msg.txt",       # leftover commit message files
        "*.backup",             # backup files
        "*.bak",                # backup files
        ".fxmachine_state.json", # state persistence (future feature placeholder)
    ]

    for pattern in temp_patterns:
        for temp_file in root.glob(pattern):
            if temp_file.is_file():
                size = temp_file.stat().st_size
                found += 1
                if dry_run:
                    info(f"Would remove: {temp_file.name}  ({fmt_size(size)})")
                else:
                    try:
                        temp_file.unlink()
                        success(f"Removed {temp_file.name}  ({fmt_size(size)})")
                        removed += 1
                        freed += size
                    except Exception as e:
                        fail(f"Could not remove {temp_file.name}: {e}")

    return found, removed, freed


# ═══════════════════════════════════════════════════════════════════════════
#  SCAN (reports what exists without deleting anything)
# ═══════════════════════════════════════════════════════════════════════════

def scan_project(root: Path) -> dict:
    """
    Scan the project directory and report what can be cleaned.
    Returns a dict of category → (item_count, total_bytes).
    """
    categories = {}

    # Build artifacts
    items = 0
    total = 0
    for d in [root / "dist", root / "build"]:
        if d.is_dir():
            items += 1
            total += folder_size(d)
    for spec in [root / "FX_Machine.spec", root / "Analyze_Session.spec"]:
        if spec.is_file():
            items += 1
            total += spec.stat().st_size
    categories["build"] = (items, total)

    # Python caches
    items = 0
    total = 0
    for pdir in root.rglob("__pycache__"):
        if ".git" not in pdir.parts and pdir.is_dir():
            items += 1
            total += folder_size(pdir)
    categories["cache"] = (items, total)

    # Log files
    items = 0
    total = 0
    logs_dir = root / "logs"
    if logs_dir.is_dir():
        for f in logs_dir.iterdir():
            if f.is_file():
                items += 1
                total += f.stat().st_size
    categories["logs"] = (items, total)

    # User config
    items = 0
    total = 0
    active = root / "config" / "active.toml"
    if active.is_file():
        items += 1
        total += active.stat().st_size
    presets = root / "config" / "presets"
    if presets.is_dir():
        for f in presets.iterdir():
            if f.is_file() and f.suffix == ".toml":
                items += 1
                total += f.stat().st_size
    categories["config"] = (items, total)

    # Temp files
    items = 0
    total = 0
    for pattern in ["debug_pyz*.py", "commit_msg.txt", "*.backup", "*.bak",
                     ".fxmachine_state.json"]:
        for f in root.glob(pattern):
            if f.is_file():
                items += 1
                total += f.stat().st_size
    categories["temp"] = (items, total)

    return categories


# ═══════════════════════════════════════════════════════════════════════════
#  INTERACTIVE MODE
# ═══════════════════════════════════════════════════════════════════════════

def run_interactive(root: Path, dry_run: bool = False):
    """
    Interactive cleanup — scans first, then asks the user which
    categories to clean.
    """
    header("Scanning project for cleanable items")

    categories = scan_project(root)
    total_items = sum(c[0] for c in categories.values())
    total_bytes = sum(c[1] for c in categories.values())

    if total_items == 0:
        info("Project is already clean — nothing to remove")
        return

    print()
    print(f"  {C.BOLD}Found {total_items} cleanable item(s) totaling "
          f"{fmt_size(total_bytes)}:{C.END}")
    print()

    category_info = [
        ("build",  "Build artifacts",  "dist/, build/, *.spec"),
        ("cache",  "Python caches",    "__pycache__/, *.pyc, *.pyo"),
        ("logs",   "Log files",        "logs/*.log, *.jsonl, session_analysis_*"),
        ("config", "User config",      "active.toml, presets/*.toml"),
        ("temp",   "Temp/debug files",  "debug_pyz*.py, commit_msg.txt, *.bak"),
    ]

    for key, label, desc in category_info:
        items, bytes_val = categories[key]
        if items > 0:
            print(f"    {C.WARN}{items:3d}{C.END} items  {fmt_size(bytes_val):>10}  "
                  f"{C.BOLD}{label}{C.END}  {C.DIM}({desc}){C.END}")
        else:
            print(f"    {C.DIM}  0 items{' ' * 12}{label} — clean{C.END}")

    print()
    mode = dry_run
    mode_label = f" {C.INFO}(DRY RUN){C.END}" if mode else ""

    # Quick option: clean everything?
    if ask_yes_no(f"Clean ALL categories?{mode_label}", default=False):
        total_found = 0
        total_removed = 0
        total_freed = 0

        cleaners = [
            ("Build artifacts", clean_build_artifacts),
            ("Python caches", clean_python_caches),
            ("Log files", clean_log_files),
            ("User config", clean_user_config),
            ("Temp files", clean_temp_files),
        ]
        for label, cleaner in cleaners:
            items, _ = categories.get(label.lower().split()[0], (0, 0))
            # Use the key mapping correctly
            cat_key = {
                "Build artifacts": "build",
                "Python caches": "cache",
                "Log files": "logs",
                "User config": "config",
                "Temp files": "temp",
            }[label]
            cat_items, _ = categories[cat_key]
            if cat_items > 0:
                header(label)
                f, r, freed = cleaner(root, dry_run=mode)
                total_found += f
                total_removed += r
                total_freed += freed

        return total_found, total_removed, total_freed

    # Per-category prompts
    total_found = 0
    total_removed = 0
    total_freed = 0

    per_cat = [
        ("build",  "Build artifacts (dist/, build/, *.spec)?",
         clean_build_artifacts),
        ("cache",  "Python caches (__pycache__)?",
         clean_python_caches),
        ("logs",   "Log files (logs/)?",
         clean_log_files),
        ("config", "User config (active.toml, presets)?",
         clean_user_config),
        ("temp",   "Temp/debug files?",
         clean_temp_files),
    ]

    print()
    for key, prompt, cleaner in per_cat:
        items, bytes_val = categories[key]
        if items == 0:
            continue
        if ask_yes_no(f"Clean {prompt}{mode_label}", default=(key != "config")):
            header(prompt.split("(")[0].strip())
            f, r, freed = cleaner(root, dry_run=mode)
            total_found += f
            total_removed += r
            total_freed += freed

    return total_found, total_removed, total_freed


# ═══════════════════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════════════════

def parse_args():
    parser = argparse.ArgumentParser(
        description="Clean FX Machine project artifacts.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python clean.py                    Interactive mode — asks what to clean
  python clean.py --all              Remove everything (no prompts)
  python clean.py --build --logs     Remove builds and logs only
  python clean.py --all --dry-run    Show what --all would remove
        """,
    )
    parser.add_argument("--all", action="store_true",
                        help="Clean everything (no prompts)")
    parser.add_argument("--build", action="store_true",
                        help="Clean build artifacts (dist/, build/, *.spec)")
    parser.add_argument("--logs", action="store_true",
                        help="Clean log files")
    parser.add_argument("--cache", action="store_true",
                        help="Clean __pycache__ folders")
    parser.add_argument("--config", action="store_true",
                        help="Clean user config (active.toml, presets)")
    parser.add_argument("--specs", action="store_true",
                        help="Clean generated .spec files")
    parser.add_argument("--temp", action="store_true",
                        help="Clean temporary/debug files")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be removed without deleting")
    return parser.parse_args()


def main():
    args = parse_args()
    root = Path(__file__).resolve().parent

    banner()
    print(f"\n  {C.DIM}Project root: {root}{C.END}")
    if args.dry_run:
        print(f"  {C.INFO}DRY RUN MODE — nothing will be deleted{C.END}")

    # Determine which mode we're in
    explicit_flags = any([args.all, args.build, args.logs, args.cache,
                          args.config, args.specs, args.temp])

    if not explicit_flags:
        # Interactive mode
        result = run_interactive(root, dry_run=args.dry_run)
        if result is None:
            result = (0, 0, 0)
        total_found, total_removed, total_freed = result
    else:
        # Flag-driven mode (non-interactive)
        total_found = 0
        total_removed = 0
        total_freed = 0

        if args.all or args.build:
            header("Build artifacts")
            f, r, freed = clean_build_artifacts(root, dry_run=args.dry_run)
            total_found += f
            total_removed += r
            total_freed += freed

        if args.all or args.cache:
            header("Python caches")
            f, r, freed = clean_python_caches(root, dry_run=args.dry_run)
            total_found += f
            total_removed += r
            total_freed += freed

        if args.all or args.logs:
            header("Log files")
            f, r, freed = clean_log_files(root, dry_run=args.dry_run)
            total_found += f
            total_removed += r
            total_freed += freed

        if args.all or args.config:
            header("User config")
            f, r, freed = clean_user_config(root, dry_run=args.dry_run)
            total_found += f
            total_removed += r
            total_freed += freed

        if args.all or args.specs:
            header("Spec files")
            f, r, freed = clean_spec_files(root, dry_run=args.dry_run)
            total_found += f
            total_removed += r
            total_freed += freed

        if args.all or args.temp:
            header("Temporary files")
            f, r, freed = clean_temp_files(root, dry_run=args.dry_run)
            total_found += f
            total_removed += r
            total_freed += freed

    # Summary
    print(f"\n{C.BOLD}{'━' * 64}{C.END}")
    if args.dry_run:
        print(f"{C.BOLD}DRY RUN SUMMARY{C.END}")
        print(f"  Would remove: {total_found} item(s), {fmt_size(total_freed)}")
        print(f"\n  {C.DIM}Run without --dry-run to actually delete.{C.END}")
    else:
        print(f"{C.BOLD}CLEANUP SUMMARY{C.END}")
        if total_removed > 0:
            print(f"  {C.OK}Removed: {total_removed} item(s), "
                  f"freed {fmt_size(total_freed)}{C.END}")
        else:
            print(f"  {C.DIM}Nothing was removed{C.END}")

        if total_found > total_removed:
            skipped = total_found - total_removed
            print(f"  {C.WARN}Skipped: {skipped} item(s) (errors or user declined){C.END}")
    print(f"{C.BOLD}{'━' * 64}{C.END}\n")

    sys.exit(0)


if __name__ == "__main__":
    main()