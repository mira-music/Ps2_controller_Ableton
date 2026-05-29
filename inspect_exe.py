"""
inspect_exe.py — Look inside a PyInstaller .exe to verify bundled files.
Run: python inspect_exe.py
"""

import zipfile
import sys
from pathlib import Path

EXE_PATH = Path("dist") / "FX_Machine" / "FX_Machine.exe"

if not EXE_PATH.exists():
    print(f"❌ {EXE_PATH} not found")
    sys.exit(1)

print(f"Inspecting {EXE_PATH}")
print(f"Size: {EXE_PATH.stat().st_size:,} bytes")
print()

# PyInstaller exes have an embedded archive. We can try to read it as a zip
# but the wrapper makes it tricky. Let's look at the raw bytes for known
# filenames.

content = EXE_PATH.read_bytes()
print(f"Searching for bundled files...\n")

search_terms = [
    b"default.toml",
    b"EXAMPLES.toml",
    b"README.md",
    b"sweep_seconds",        # appears in default.toml content
    b"PUNCHY CLUB",          # appears in EXAMPLES.toml content
    b"FX Machine Config",    # appears in config/README.md
]

for term in search_terms:
    offsets = []
    start = 0
    while True:
        idx = content.find(term, start)
        if idx == -1:
            break
        offsets.append(idx)
        start = idx + 1
        if len(offsets) >= 5:
            break

    if offsets:
        print(f"  ✓ Found '{term.decode()}' at {len(offsets)}+ location(s)")
    else:
        print(f"  ✗ NOT FOUND: '{term.decode()}'")

print()
print("If the search terms above are found, the files ARE bundled.")
print("If not, --add-data didn't work and we need a .spec file approach.")