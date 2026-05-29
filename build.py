"""
================================================================================
  build.py — Build FX Machine as a portable folder
================================================================================
  Run:    python build.py
  Output: dist/FX_Machine/  (a folder containing FX_Machine.exe + everything)

  Uses PyInstaller in ONEDIR mode (no single-file extraction magic).
  Config files are copied manually after the build for guaranteed reliability.

  To distribute: zip the entire dist/FX_Machine/ folder.
================================================================================
"""

import subprocess
import sys
import shutil
from pathlib import Path


def build():
    print("=" * 64)
    print("  Building FX Machine (portable folder)")
    print("=" * 64)

    project_root = Path(__file__).resolve().parent
    spec_file = project_root / "FX_Machine.spec"
    dist_root = project_root / "dist"
    output_dir = dist_root / "FX_Machine"

    # ─── Verify spec file exists ───
    if not spec_file.is_file():
        print(f"\n  ❌ Spec file not found: {spec_file}")
        return

    # ─── Verify config files exist ───
    print("\n  Verifying source config files...")
    config_src = project_root / "config"
    if not config_src.is_dir():
        print(f"  ❌ config/ folder not found in project root")
        return

    expected = ['default.toml', 'EXAMPLES.toml', 'README.md']
    missing = []
    for fname in expected:
        path = config_src / fname
        if path.is_file():
            print(f"    ✓ config/{fname}  ({path.stat().st_size:,} bytes)")
        else:
            print(f"    ✗ MISSING: config/{fname}")
            missing.append(fname)
    if missing:
        print(f"\n  ❌ Cannot build — missing required files.")
        return

    # ─── Clean previous build ───
    print("\n  Cleaning previous build...")
    if output_dir.exists():
        shutil.rmtree(output_dir)
        print(f"    ✓ Removed old {output_dir}")
    build_dir = project_root / "build"
    if build_dir.exists():
        shutil.rmtree(build_dir)
        print(f"    ✓ Removed old {build_dir}")

    # ─── Run PyInstaller ───
    print(f"\n  Running PyInstaller (1-3 minutes)...\n")
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        str(spec_file),
    ]
    result = subprocess.run(cmd)

    if result.returncode != 0:
        print(f"\n  ❌ PyInstaller failed with exit code {result.returncode}")
        return

    # ─── Verify .exe was created ───
    exe_path = output_dir / "FX_Machine.exe"
    if not exe_path.exists():
        print(f"\n  ❌ Build finished but .exe not found at {exe_path}")
        return

    # ─── Copy config folder into the output ───
    print(f"\n  Copying config files into output folder...")
    config_dst = output_dir / "config"
    config_dst.mkdir(exist_ok=True)
    for fname in expected:
        src = config_src / fname
        dst = config_dst / fname
        shutil.copy2(src, dst)
        print(f"    ✓ {dst.relative_to(project_root)}")

    # ─── Report ───
    print(f"\n" + "=" * 64)
    print(f"  ✅ Build successful!")
    print(f"=" * 64)
    print(f"\n  Output folder: {output_dir}")
    print(f"  Executable:    {exe_path}")
    print(f"  Size on disk:  {get_folder_size_mb(output_dir):.1f} MB")
    print(f"\n  To run the app:")
    print(f"    Double-click  dist\\FX_Machine\\FX_Machine.exe")
    print(f"  Or from command line:")
    print(f"    dist\\FX_Machine\\FX_Machine.exe")
    print(f"\n  To distribute:")
    print(f"    Zip the entire dist/FX_Machine/ folder and share the zip.")
    print(f"    Users unzip and run FX_Machine.exe inside — no install needed.")
    print(f"\n  Config files (editable):")
    print(f"    {config_dst}/default.toml")
    print(f"    {config_dst}/EXAMPLES.toml")
    print(f"    {config_dst}/README.md")
    print(f"\n  On first launch, active.toml is created automatically.")
    print("=" * 64)


def get_folder_size_mb(folder: Path) -> float:
    total = 0
    for f in folder.rglob('*'):
        if f.is_file():
            total += f.stat().st_size
    return total / (1024 * 1024)


if __name__ == "__main__":
    build()