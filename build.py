"""
================================================================================
  build.py — Build FX Machine as a portable folder
================================================================================
  Run:    python build.py
  Output: dist/FX_Machine/  (folder containing FX_Machine.exe + all dependencies)

  Uses PyInstaller in ONEDIR mode (not single-file). Config files are copied
  manually after the build for guaranteed reliability — PyInstaller's data
  collection can be unreliable for TOML files that live outside src/.

  To distribute: zip the entire dist/FX_Machine/ folder and share the zip.
  Recipients unzip and double-click FX_Machine.exe — no Python required.

  Fixes applied:
    - Added PyInstaller pre-check (import test) before running subprocess.
      Previously, if PyInstaller was not installed, the subprocess call would
      fail with a non-zero exit code and a generic error message. Now we
      detect the missing package immediately and print a clear install command.
    - Added .exe name detection: if PyInstaller produces an .exe with a
      different name than expected, we list what IS in the output folder
      instead of failing with a misleading "not found" message.
    - Duplicate *.log comment removed from .gitignore is noted here for
      completeness (fixed in .gitignore separately).
================================================================================
"""

import subprocess
import sys
import shutil
from pathlib import Path


# ═══════════════════════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def get_folder_size_mb(folder: Path) -> float:
    """
    Recursively sum the size of all files in folder.
    Returns total in megabytes.

    Note: uses individual stat() calls per file. A PyInstaller onedir build
    typically has 200-400 files (Python runtime, DLLs, data). This is
    acceptable for an infrequent build tool.
    """
    total = 0
    for f in folder.rglob('*'):
        if f.is_file():
            try:
                total += f.stat().st_size
            except OSError:
                pass
    return total / (1024 * 1024)


def _check_pyinstaller() -> bool:
    """
    Verify PyInstaller is importable before attempting the subprocess call.

    If PyInstaller is missing, the subprocess would fail with a confusing
    'No module named PyInstaller' message buried in stderr. We catch it
    here and print a clear install command instead.

    Returns True if PyInstaller is available, False otherwise.
    """
    try:
        import PyInstaller
        version = getattr(PyInstaller, "__version__", "unknown")
        print(f"  ✓ PyInstaller {version} found")
        return True
    except ImportError:
        print(
            "\n  ❌ PyInstaller is not installed.\n"
            "     Run:  pip install pyinstaller\n"
            "     Then re-run this script."
        )
        return False


def _find_exe_in_folder(folder: Path) -> Path | None:
    """
    Find the first .exe file in folder (non-recursive).
    Returns the Path if found, None otherwise.

    Used to give a helpful error when the .exe has an unexpected name.
    """
    exes = list(folder.glob("*.exe"))
    return exes[0] if exes else None


# ═══════════════════════════════════════════════════════════════════════════
#  MAIN BUILD FUNCTION
# ═══════════════════════════════════════════════════════════════════════════

def build():
    print("=" * 64)
    print("  FX Machine — Portable Folder Build")
    print("=" * 64)

    project_root = Path(__file__).resolve().parent
    spec_file    = project_root / "FX_Machine.spec"
    dist_root    = project_root / "dist"
    output_dir   = dist_root / "FX_Machine"

    # ── Pre-flight: PyInstaller available? ──────────────────────────────
    print("\n  Checking build dependencies...")
    if not _check_pyinstaller():
        return

    # ── Pre-flight: spec file present? ──────────────────────────────────
    if not spec_file.is_file():
        print(
            f"\n  ❌ Spec file not found: {spec_file}\n"
            f"     The spec file tells PyInstaller how to bundle the app.\n"
            f"     If you deleted it, regenerate with:\n"
            f"       pyinstaller --name FX_Machine --onedir run.py\n"
            f"     Then customise the generated .spec as needed."
        )
        return

    print(f"  ✓ Spec file: {spec_file.name}")

    # ── Pre-flight: required config source files ─────────────────────────
    # These files are copied into the output folder after the build.
    # active.toml is intentionally excluded — it is user-specific and
    # created automatically on first launch.
    print("\n  Verifying source config files...")
    config_src = project_root / "config"

    if not config_src.is_dir():
        print(
            f"\n  ❌ config/ folder not found at {config_src}\n"
            f"     This folder must exist and contain default.toml, "
            f"EXAMPLES.toml, and README.md."
        )
        return

    expected_config_files = ["default.toml", "EXAMPLES.toml", "README.md"]
    missing_files = []

    for fname in expected_config_files:
        path = config_src / fname
        if path.is_file():
            size_bytes = path.stat().st_size
            print(f"    ✓ config/{fname}  ({size_bytes:,} bytes)")
        else:
            print(f"    ✗ MISSING: config/{fname}")
            missing_files.append(fname)

    if missing_files:
        print(
            f"\n  ❌ Cannot build — {len(missing_files)} required config file(s) missing:\n"
            + "\n".join(f"       config/{f}" for f in missing_files)
        )
        return

    # ── Clean previous build artifacts ──────────────────────────────────
    print("\n  Cleaning previous build artifacts...")

    if output_dir.exists():
        shutil.rmtree(output_dir)
        print(f"    ✓ Removed {output_dir.relative_to(project_root)}")

    build_dir = project_root / "build"
    if build_dir.exists():
        shutil.rmtree(build_dir)
        print(f"    ✓ Removed {build_dir.relative_to(project_root)}")

    # ── Run PyInstaller ──────────────────────────────────────────────────
    print(f"\n  Running PyInstaller (this takes 1-3 minutes)...\n"
          f"  {'─' * 60}")

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        str(spec_file),
    ]

    result = subprocess.run(cmd, cwd=str(project_root))

    print(f"  {'─' * 60}")

    if result.returncode != 0:
        print(
            f"\n  ❌ PyInstaller exited with code {result.returncode}.\n"
            f"     Check the output above for the specific error.\n"
            f"     Common causes:\n"
            f"       - Missing hidden imports (add to FX_Machine.spec)\n"
            f"       - Antivirus blocking PyInstaller's temp writes\n"
            f"       - Corrupted PyInstaller cache (try: pip install --upgrade pyinstaller)"
        )
        return

    # ── Verify .exe was created ──────────────────────────────────────────
    # Check for the expected name first, then fall back to any .exe found.
    expected_exe = output_dir / "FX_Machine.exe"

    if not expected_exe.exists():
        # Give a more helpful error: list what IS in the folder
        found_exe = _find_exe_in_folder(output_dir) if output_dir.exists() else None
        if found_exe:
            print(
                f"\n  ❌ Expected {expected_exe.name} but found {found_exe.name} instead.\n"
                f"     Check the 'name' field in FX_Machine.spec — it controls the .exe name.\n"
                f"     Current spec name may not be 'FX_Machine'."
            )
        elif output_dir.exists():
            contents = [f.name for f in output_dir.iterdir()]
            print(
                f"\n  ❌ Build completed but no .exe found in {output_dir}.\n"
                f"     Folder contents: {contents[:10]}\n"
                f"     Check FX_Machine.spec for the correct output configuration."
            )
        else:
            print(
                f"\n  ❌ Build completed but output folder does not exist: {output_dir}\n"
                f"     Check the 'distpath' setting in FX_Machine.spec."
            )
        return

    print(f"\n  ✓ Executable created: {expected_exe.relative_to(project_root)}")

    # ── Copy config files into output folder ─────────────────────────────
    # Config files are copied manually rather than relying on PyInstaller's
    # data collection. This guarantees they land in the right place and are
    # editable by the end user without extracting anything.
    print(f"\n  Copying config files into output folder...")

    config_dst = output_dir / "config"
    config_dst.mkdir(exist_ok=True)

    for fname in expected_config_files:
        src = config_src / fname
        dst = config_dst / fname
        shutil.copy2(src, dst)
        print(f"    ✓ {dst.relative_to(project_root)}")

    # Copy presets folder if it exists and has files worth shipping
    presets_src = config_src / "presets"
    if presets_src.is_dir():
        presets_dst = config_dst / "presets"
        presets_dst.mkdir(exist_ok=True)
        shipped = 0
        for f in presets_src.iterdir():
            # Ship .gitkeep and any bundled example presets but not
            # the user's personal active.toml-derived presets (those
            # are in .gitignore and won't be in the source tree anyway)
            if f.is_file():
                shutil.copy2(f, presets_dst / f.name)
                shipped += 1
        if shipped:
            print(f"    ✓ config/presets/  ({shipped} file(s))")

    # ── Final report ─────────────────────────────────────────────────────
    folder_size_mb = get_folder_size_mb(output_dir)

    print(f"\n{'=' * 64}")
    print(f"  ✅  Build successful!")
    print(f"{'=' * 64}")
    print(f"\n  Output folder : {output_dir}")
    print(f"  Executable    : {expected_exe}")
    print(f"  Total size    : {folder_size_mb:.1f} MB")
    print()
    print(f"  ── To run the app ──────────────────────────────────────")
    print(f"  Double-click:   dist\\FX_Machine\\FX_Machine.exe")
    print(f"  Command line:   dist\\FX_Machine\\FX_Machine.exe")
    print()
    print(f"  ── On first launch ─────────────────────────────────────")
    print(f"  config/active.toml is created automatically from")
    print(f"  config/default.toml. Edit active.toml to tune feel.")
    print()
    print(f"  ── To distribute ───────────────────────────────────────")
    print(f"  Zip the entire dist/FX_Machine/ folder:")
    print(f"    Right-click dist/FX_Machine → Send to → Compressed folder")
    print(f"  Recipients unzip and run FX_Machine.exe — no install needed.")
    print()
    print(f"  ── Config files (editable by end user) ─────────────────")
    for fname in expected_config_files:
        print(f"    {(config_dst / fname).relative_to(project_root)}")
    print(f"{'=' * 64}")


# ═══════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    build()