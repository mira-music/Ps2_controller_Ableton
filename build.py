"""
================================================================================
  build.py — Build FX Machine into a standalone .exe
================================================================================
  Run:   python build.py
  Output: dist/FX_Machine.exe

  Uses PyInstaller to bundle Python + all dependencies into a single
  executable. No Python installation needed on the target machine.
================================================================================
"""

import subprocess
import sys
import os

def build():
    print("=" * 64)
    print("  Building FX Machine .exe")
    print("=" * 64)

    # PyInstaller command
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",           # single .exe file
        "--windowed",          # no console window (GUI app)
        "--name", "FX_Machine",
        "--icon", "NONE",      # no custom icon (add one later if you want)

        # Hidden imports that PyInstaller might miss
        "--hidden-import", "pygame",
        "--hidden-import", "pythonosc",
        "--hidden-import", "pythonosc.dispatcher",
        "--hidden-import", "pythonosc.osc_server",
        "--hidden-import", "pythonosc.udp_client",

        # Collect all submodules from our src package
        "--collect-submodules", "src",

        # Entry point
        "run.py",
    ]

    print(f"\n  Command: {' '.join(cmd)}\n")

    result = subprocess.run(cmd)

    if result.returncode == 0:
        exe_path = os.path.join("dist", "FX_Machine.exe")
        if os.path.exists(exe_path):
            size_mb = os.path.getsize(exe_path) / (1024 * 1024)
            print(f"\n  ✅ Build successful!")
            print(f"  📦 Output: {os.path.abspath(exe_path)}")
            print(f"  📏 Size:   {size_mb:.1f} MB")
            print(f"\n  To run:  dist\\FX_Machine.exe")
        else:
            print(f"\n  ⚠  Build finished but .exe not found at expected path")
    else:
        print(f"\n  ❌ Build failed with exit code {result.returncode}")
        print(f"  Check the output above for errors.")

    print("=" * 64)

if __name__ == "__main__":
    build()