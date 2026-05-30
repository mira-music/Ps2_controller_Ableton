## docs/BUILDING.md

```markdown
# 🏗️ FX Machine — Building and Distribution Guide

## What This Document Covers

This guide covers everything related to building FX Machine into a
distributable form — running it from source, building the portable
.exe with PyInstaller, verifying the build with the inspector,
distributing to others, troubleshooting build failures, and
understanding what happens under the hood during the build process.

If you're a developer working on FX Machine, you'll use this guide
when you need to ship a new version to friends or test users. If
you're a user who just wants to run the app, see the Quick Start
in the main README — you don't need this document.

---

## Table of Contents

1. [The Two Ways to Run FX Machine](#the-two-ways-to-run-fx-machine)
2. [Running from Source](#running-from-source)
3. [Why Build an .exe at All?](#why-build-an-exe-at-all)
4. [PyInstaller Overview](#pyinstaller-overview)
5. [PyInstaller 6.x Onedir Layout](#pyinstaller-6x-onedir-layout)
6. [The build.py Script](#the-buildpy-script)
7. [Pre-Build Checklist](#pre-build-checklist)
8. [Running the Build](#running-the-build)
9. [Understanding the Build Output](#understanding-the-build-output)
10. [The FX_Machine.spec File](#the-fx_machinespec-file)
11. [What Gets Bundled](#what-gets-bundled)
12. [Config Files in the Bundle](#config-files-in-the-bundle)
13. [Verifying the Build with inspect_exe.py](#verifying-the-build-with-inspect_exepy)
14. [Testing the Built Executable](#testing-the-built-executable)
15. [Distributing to Other Users](#distributing-to-other-users)
16. [What Recipients Need](#what-recipients-need)
17. [Build Size Optimization](#build-size-optimization)
18. [Common Build Failures](#common-build-failures)
19. [Antivirus and SmartScreen](#antivirus-and-smartscreen)
20. [Code Signing (Optional)](#code-signing-optional)
21. [Creating an Installer](#creating-an-installer)
22. [Building for Other Platforms](#building-for-other-platforms)
23. [Continuous Integration](#continuous-integration)
24. [Versioning Your Builds](#versioning-your-builds)
25. [Hosting and Sharing Builds](#hosting-and-sharing-builds)
26. [Updating End Users](#updating-end-users)
27. [Build Artifact Cleanup](#build-artifact-cleanup)
28. [Troubleshooting Build-Specific Issues](#troubleshooting-build-specific-issues)

---

## The Two Ways to Run FX Machine

FX Machine can be run in two modes:

### Mode A — From source (development mode)

```bash
python run.py
```

Requires:
- Python 3.11+ installed
- pygame, python-osc, psutil installed via pip
- The full FX Machine source code

Pros:
- Instant iteration — edit code, save, rerun
- Full access to logs and diagnostics
- Can use IDE debugger
- Easy to modify TOML config

Cons:
- Requires Python knowledge to set up
- Multiple dependencies to manage
- Not portable — can't easily share with non-developers

### Mode B — Portable executable (distribution mode)

```
Double-click FX_Machine.exe
```

Requires:
- Windows 10 or 11
- The extracted dist/FX_Machine/ folder (everything is bundled)

Pros:
- Zero Python or dependency installation needed
- One folder, one .exe, double-click to run
- Anyone can use it
- Identical behavior to source mode

Cons:
- Larger disk footprint (~40-60 MB folder vs ~5 KB script)
- Must rebuild after code changes
- Slightly slower startup (~1-2 seconds vs instant from source)

---

## Running from Source

For development work, run from source. The setup:

### 1. Install Python 3.11 or later

Download from [python.org](https://www.python.org/downloads/).
Make sure "Add Python to PATH" is checked during installation.

Verify:
```bash
python --version
```
Should print `Python 3.11.x` or higher.

### 2. Install dependencies

```bash
pip install pygame python-osc psutil
```

- **pygame:** Gamepad input (required)
- **python-osc:** OSC communication with Ableton (required)
- **psutil:** System resource monitoring (optional, used by diagnostics)

The app runs without psutil but the diagnostics layer's CPU/RAM
metrics will be unavailable.

### 3. Verify the installation

```bash
python diagnose.py
```

Should show all green checks. If anything is red, fix it before
proceeding.

### 4. Run the app

```bash
python run.py
```

The window should appear within ~3 seconds.

### Troubleshooting from-source mode

**"ModuleNotFoundError: No module named 'pygame'"**

You installed dependencies in a different Python environment than
the one you're running. Try:
```bash
python -m pip install pygame python-osc psutil
```

**"FX track '~ FX Macros' not found in session"**

The Ableton setup isn't complete. See [SETUP_ABLETON.md](SETUP_ABLETON.md).

**"OSC sender ready" but no session data appears**

AbletonOSC isn't installed or active. See [SETUP_ABLETON.md](SETUP_ABLETON.md)
Step 1.

---

## Why Build an .exe at All?

The .exe build process is for distribution. Reasons to build:

### Sharing with friends who don't code

A musician or DJ who wants to use FX Machine but doesn't know Python
shouldn't have to install Python, pip, and learn command-line tools.
The .exe is double-clickable.

### Stable releases

You want to lock down a specific version for your live shows. Source
code changes mid-tour are risky. A built .exe is frozen — it works
the same way every night until you rebuild.

### Testing in a clean environment

A built .exe uses only bundled dependencies, so you know it's not
silently relying on something installed in your dev environment. If
the .exe works on a fresh machine, the build is complete.

### Future commercial distribution

If you ever want to sell or freely distribute FX Machine to a wider
audience, you need a .exe. End users will not run Python scripts.

---

## PyInstaller Overview

[PyInstaller](https://pyinstaller.org/) is the tool we use to build
the .exe. It works by:

1. Analyzing your Python script to find all imported modules
2. Bundling Python itself + your script + all dependencies into one
   folder or one file
3. Producing an executable that launches Python from the bundle

### PyInstaller modes

**onefile mode (NOT what we use):**
- Produces ONE .exe containing everything
- Extracts to a temp directory at runtime, then launches
- Slower startup (extraction takes 1-3 seconds)
- Easier to share (just one file)

**onedir mode (what we use):**
- Produces a FOLDER with the .exe + supporting files
- No extraction at runtime — launches instantly
- Larger total footprint but faster startup
- Better for live performance use (no startup delay)

FX Machine uses **onedir** because startup speed matters when you're
about to perform.

---

## PyInstaller 6.x Onedir Layout

The output folder structure is specific to PyInstaller 6.x:

```
dist/FX_Machine/
├── FX_Machine.exe                ← The launcher stub (small, ~3-5 MB)
│                                    Contains: bootloader + embedded PYZ + PKG
│
├── config/                       ← Manually copied by build.py
│   ├── default.toml
│   ├── EXAMPLES.toml
│   ├── README.md
│   └── presets/
│
└── _internal/                    ← Python runtime + dependencies (~35-50 MB)
    ├── python312.dll             ← Python interpreter
    ├── base_library.zip          ← Compressed standard library
    ├── _tkinter.pyd              ← Tkinter C extension
    ├── tcl86t.dll                ← Tcl runtime
    ├── tk86t.dll                 ← Tk runtime
    ├── SDL2.dll                  ← pygame's SDL2
    ├── SDL2_mixer.dll
    ├── SDL2_image.dll
    ├── pygame/                   ← pygame Python package
    │   ├── _freetype.cp312-win_amd64.pyd
    │   ├── _sdl2.cp312-win_amd64.pyd
    │   └── ... (other pygame files)
    ├── libcrypto-3.dll
    ├── libssl-3.dll
    └── ... (many other support DLLs)
```

### Critical PyInstaller 6.x detail

In PyInstaller 5 and earlier, the PYZ archive (containing your Python
modules) was a separate file in `_internal/`. In PyInstaller 6.x, the
PYZ is **embedded inside the .exe stub itself**. This is why:

- The .exe is 3-5 MB (not 800 KB like older versions)
- There's no `PYZ-00.pyz` file visible in `_internal/`
- The inspector tool has special logic to read the embedded PYZ from
  inside the .exe

This is a normal and correct layout. The first time you build, you
might be confused by not seeing PYZ files — they're inside the .exe.

---

## The build.py Script

FX Machine ships with a custom build script that wraps PyInstaller
and handles project-specific details:

```bash
python build.py
```

This script:

1. **Verifies PyInstaller is installed** — fails early with a clear
   error if missing
2. **Verifies the spec file exists** — `FX_Machine.spec` must be
   present in the project root
3. **Verifies config source files** — `config/default.toml`,
   `config/EXAMPLES.toml`, `config/README.md` must exist
4. **Cleans previous build artifacts** — removes `dist/FX_Machine/`
   and `build/` from any previous build
5. **Runs PyInstaller** with the spec file (`--noconfirm --clean`)
6. **Verifies the .exe was created** — fails with helpful output if
   the .exe is missing or has an unexpected name
7. **Copies config files into the output folder** — `default.toml`,
   `EXAMPLES.toml`, `README.md`, and any preset files
8. **Reports the result** — output folder, .exe location, total size,
   instructions for running and distributing

### Why a custom script instead of just `pyinstaller`?

The build process has several steps PyInstaller doesn't handle
automatically:

- Config files need to be copied into the output folder (PyInstaller's
  data-collection mechanism is unreliable for files outside src/)
- The presets folder needs to be created
- We want clear error messages when something goes wrong
- We want a reproducible build (clean previous artifacts first)

The script orchestrates all of this into one command.

---

## Pre-Build Checklist

Before running `python build.py`, verify:

### 1. The app runs from source

```bash
python run.py
```

The app should start, the UI should appear, you should be able to use
it. If source-mode doesn't work, the build won't work either.

### 2. The diagnostic tool passes

```bash
python diagnose.py
```

All checks should pass (or only warnings, no errors). The diagnostic
tool catches many issues that would otherwise show up only at runtime.

### 3. Git status is clean (recommended)

```bash
git status
```

Commit your changes before building. If you find a bug in the built
version, you want to know exactly which code version produced it.

### 4. PyInstaller is installed

```bash
pip install pyinstaller
```

Verify:
```bash
python -m PyInstaller --version
```

Should print `6.x.x` or similar.

### 5. The spec file exists

```
FX_Machine.spec
```

Should be in the project root. This file tells PyInstaller exactly how
to build the app. If it's missing, see "The FX_Machine.spec File"
section below for how to regenerate it.

### 6. Disk space available

The build process needs ~200 MB of temporary space (build artifacts
plus final output). Make sure your drive isn't full.

---

## Running the Build

```bash
python build.py
```

A typical successful build looks like this:

```
================================================================
  Building FX Machine (portable folder)
================================================================

  Verifying source config files...
    ✓ config/default.toml  (24,024 bytes)
    ✓ config/EXAMPLES.toml  (6,713 bytes)
    ✓ config/README.md  (2,619 bytes)

  Cleaning previous build...

  Running PyInstaller (1-3 minutes)...

[... PyInstaller output ...]

  ✓ Executable created: dist/FX_Machine/FX_Machine.exe

  Copying config files into output folder...
    ✓ dist/FX_Machine/config/default.toml
    ✓ dist/FX_Machine/config/EXAMPLES.toml
    ✓ dist/FX_Machine/config/README.md
    ✓ config/presets/  (1 file(s))

================================================================
  ✅ Build successful!
================================================================

  Output folder: D:\midi\PS_controller\dist\FX_Machine
  Executable:    D:\midi\PS_controller\dist\FX_Machine\FX_Machine.exe
  Size on disk:  40.3 MB

  To run the app:
    Double-click  dist\FX_Machine\FX_Machine.exe
  Or from command line:
    dist\FX_Machine\FX_Machine.exe

  To distribute:
    Zip the entire dist/FX_Machine/ folder and share the zip.
    Users unzip and run FX_Machine.exe inside — no install needed.
```

### Build time

Expect 1-3 minutes for a clean build:
- **Analysis:** ~30 seconds (scanning imports)
- **Packaging:** ~60 seconds (creating PYZ, copying files)
- **Final assembly:** ~30 seconds (creating .exe + folder)

Subsequent builds (without `--clean`) are faster because PyInstaller
caches its analysis.

---

## Understanding the Build Output

After a successful build, you have:

```
dist/FX_Machine/
├── FX_Machine.exe          ~3-5 MB
├── config/                 ~30 KB
│   ├── default.toml
│   ├── EXAMPLES.toml
│   ├── README.md
│   └── presets/
│       └── .gitkeep
└── _internal/              ~35-50 MB
    └── [many files]
```

Total: ~40-60 MB

### What you can do with each part

**FX_Machine.exe:** Double-click to run. Don't move or rename it
without also moving the `_internal/` and `config/` folders.

**config/:** Ships with default settings. On first launch, the app
creates `config/active.toml` here from `default.toml`. End users edit
`active.toml` to tune their setup.

**_internal/:** Contains everything the app needs. Don't modify these
files. If you delete them, the .exe won't run.

### What's NOT in the output

- Source code (`src/`)
- Documentation (`docs/`)
- The `build.py` script
- The `diagnose.py` script
- Logs (these are created at runtime in `logs/`)
- Any preset files you've created (unless explicitly copied)

If you want to ship documentation with the build, copy the `docs/`
folder into `dist/FX_Machine/` manually before zipping.

---

## The FX_Machine.spec File

PyInstaller uses a `.spec` file to define build options. FX Machine's
spec file controls:

- Entry point (`run.py`)
- Application name (`FX_Machine`)
- Icon (if you've added one)
- Hidden imports (modules PyInstaller can't auto-detect)
- Data files to include
- Build mode (onedir vs onefile)
- Optimization options

### Where it comes from

If you don't have `FX_Machine.spec` yet, you can generate it with:

```bash
python -m PyInstaller --noconfirm --name FX_Machine --onedir run.py
```

This creates a basic spec file. You then edit it for FX Machine-specific
needs (data files, hidden imports, icon, etc.).

### Editing the spec file

The spec file is Python code. Key sections:

```python
# FX_Machine.spec (simplified example)
a = Analysis(
    ['run.py'],
    pathex=[],
    binaries=[],
    datas=[],                  ← Add data files here
    hiddenimports=[            ← Add modules PyInstaller misses
        'src.diagnostics',
        'src.diagnostics.installer',
        'src.diagnostics.profiler',
        # ... etc
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],               ← Modules to skip
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='FX_Machine',         ← .exe name
    icon='icon.ico',           ← Optional icon
    console=False,             ← True for console window, False for windowed
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name='FX_Machine',         ← Output folder name
)
```

### When to regenerate the spec file

You probably won't need to. Once it works for your project, leave it
alone. Regenerate only if:

- You renamed `run.py` (different entry point)
- You want to add an icon
- You're switching from onedir to onefile
- PyInstaller's defaults changed in a major version update

---

## What Gets Bundled

PyInstaller analyzes your code to find all imports, then bundles them.
For FX Machine, this includes:

### Python standard library

Almost everything Python provides:
- `tkinter` (UI)
- `threading`, `time` (concurrency)
- `tomllib` (config parsing)
- `json`, `logging`, `pathlib` (utilities)
- `socket`, `select` (networking via OSC)
- `gc`, `weakref` (memory management)

### Third-party packages

- **pygame** (~10 MB) — Gamepad input + SDL2 runtime
- **python-osc** (~2 MB) — OSC communication
- **psutil** (~3 MB, optional) — System monitoring

### Your application code

All files in `src/` plus `run.py`. PyInstaller compiles `.py` files
to `.pyc` and includes them in the embedded PYZ archive.

### Excluded by default

PyInstaller automatically excludes things that won't work in a bundled
environment:
- Development tools (pip, setuptools)
- Testing frameworks (pytest, unittest helpers)
- Documentation generators

### What might be missing

Sometimes PyInstaller can't detect dynamically-imported modules. If
you see "ModuleNotFoundError" in the built .exe but not in source
mode, add the module name to `hiddenimports` in the spec file:

```python
hiddenimports=[
    'src.diagnostics.installer',  # always include this
    'some_dynamically_imported_module',
],
```

---

## Config Files in the Bundle

PyInstaller's data-file collection (`datas=` in the spec) is unreliable
for files outside `src/`. The `build.py` script handles config files
manually:

```python
# In build.py
config_files = ['default.toml', 'EXAMPLES.toml', 'README.md']
config_src = project_root / "config"
config_dst = output_dir / "config"
config_dst.mkdir(exist_ok=True)

for fname in config_files:
    shutil.copy2(config_src / fname, config_dst / fname)
```

This guarantees the config files end up in the right place every time.

### What happens on first launch

When an end user double-clicks `FX_Machine.exe` for the first time:

1. The app sees that `config/active.toml` doesn't exist
2. It copies `config/default.toml` → `config/active.toml`
3. The user can now edit `active.toml` without breaking the original

This is why the build ships `default.toml` (the read-only template)
and NOT `active.toml` (the user-editable file). `active.toml` is
created per-installation.

---

## Verifying the Build with inspect_exe.py

The build might succeed but the resulting .exe might still be broken.
The `inspect_exe.py` tool verifies the bundle is complete and correct:

```bash
python inspect_exe.py
```

Checks performed:

1. **EXE file existence and size** — verifies the .exe was created and
   has a reasonable size (2-8 MB for PyInstaller 6 onedir stub)
2. **_internal/ folder structure** — verifies the Python runtime is
   bundled
3. **Output folder structure** — verifies all expected directories exist
4. **Config files present** — verifies `default.toml`, `EXAMPLES.toml`,
   `README.md` are in `config/`
5. **Config content signatures** — verifies the config files contain
   expected content (catches the case where an empty file was copied)
6. **EXE embedded archive** — parses the CArchive inside the .exe to
   verify Python modules are bundled
7. **PYZ module inventory** — extracts the PYZ from inside the .exe
   and lists every Python module that's bundled. Verifies all FX Machine
   modules are present.
8. **Required DLLs** — verifies SDL2, Tk, Python DLLs are present
9. **EXE binary markers** — checks PyInstaller magic bytes in the binary
10. **TOML validity** — actually parses the shipped TOML files to
    verify they're not corrupted
11. **Runtime import simulation** — imports the project source modules
    to verify they'd import correctly inside the bundle

### Reading the inspector output

```
╔══════════════════════════════════════════════════════════════╗
║      FX MACHINE — EXE BUNDLE INSPECTOR (v3)                 ║
╚══════════════════════════════════════════════════════════════╝

  Target  : dist/FX_Machine/FX_Machine.exe
  Layout  : PyInstaller 6.20 onedir (PYZ embedded in EXE)

━━━ EXE File Existence + Sanity ━━━
  ✓ 3 check(s) passed

━━━ _internal/ Folder ━━━
  ✓ 4 check(s) passed

━━━ Output Folder Structure ━━━
  ✓ 3 check(s) passed

━━━ Config Files in Output Folder ━━━
  ✓ 4 check(s) passed

━━━ Config File Content Signatures ━━━
  ✓ 12 check(s) passed

━━━ EXE Embedded Archive ━━━
  ✓ All 23 FX Machine modules confirmed in bundle
  ✓ pygame found in _internal/ as C extension

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SUMMARY  (0.9s)
  Total checks : 87
  ✓ Passed:    87
  ⚠ Warnings:   0
  ✗ Failed:     0

✅  ALL CHECKS PASSED — BUILD IS GOOD TO SHIP
```

If any check fails, the output will tell you exactly what's wrong and
which file/folder to investigate.

### When to run inspect_exe.py

Always, after every build. The inspection takes ~1 second and catches
real problems before you ship a broken build.

---

## Testing the Built Executable

After the inspector passes, do a real-world test:

### 1. Launch the .exe

```bash
dist\FX_Machine\FX_Machine.exe
```

The window should appear within 1-3 seconds. The console window
(if you built with `console=True` in the spec) should show normal
startup logs.

### 2. Verify Ableton connection

The app should connect to AbletonOSC and discover your session. Watch
for "Session: N scenes, N tracks" in the console or logs.

### 3. Verify gamepad works

Move the sticks. Press some buttons. The UI should respond.

### 4. Verify diagnostics (if enabled)

If you have `[diagnostics] enabled = true` in `active.toml`, after a
minute or two of use, check `dist/FX_Machine/logs/diagnostics.log` —
it should contain summary blocks.

### 5. Verify clean shutdown

Close the window normally. The console should print "👋 Stopped." and
exit cleanly. No "Fatal Python error" or other crash messages.

### 6. Verify on a different machine

The ultimate test — copy the entire `dist/FX_Machine/` folder to a
DIFFERENT computer (preferably one without Python installed) and run
it there. If it works, the build is truly portable.

---

## Distributing to Other Users

The simplest distribution:

### 1. Zip the build folder

Right-click `dist/FX_Machine/` → Send to → Compressed (zipped) folder.

Or via command line:
```bash
# PowerShell
Compress-Archive -Path dist\FX_Machine -DestinationPath FX_Machine_v1.0.0.zip
```

### 2. Share the zip

Upload to Google Drive, Dropbox, WeTransfer, GitHub Releases, or any
file-sharing service. The zip will be ~30-50 MB compressed.

### 3. Recipient instructions

Provide a simple README for recipients:

```
FX Machine v1.0.0

To install:
1. Extract this zip to any folder on your computer
2. Inside the extracted folder, double-click FX_Machine.exe
3. The app will start and create its config files on first launch

Requirements:
- Windows 10 or 11
- Ableton Live 10, 11, or 12
- AbletonOSC installed (see SETUP_ABLETON.md)
- USB gamepad

For full setup instructions, see docs/SETUP_ABLETON.md
For troubleshooting, see docs/TROUBLESHOOTING.md
```

---

## What Recipients Need

End users need:

### Required

- **Windows 10 or 11** (64-bit). FX Machine v1.0.0 doesn't run on
  macOS or Linux from a Windows build.
- **The extracted `FX_Machine/` folder** with all its contents.
- **A USB gamepad** (PlayStation, Xbox, or generic — any 12-button
  pad with two analog sticks works).
- **Ableton Live 10, 11, or 12** installed.
- **AbletonOSC** installed in Ableton (see SETUP_ABLETON.md).

### NOT required

- Python (bundled)
- pygame, python-osc, psutil (bundled)
- Tkinter (bundled)
- Any compiler or build tools

### Disk space

- ~50 MB extracted
- ~50 MB additional for the zip download
- ~10 MB more for logs accumulated over time

### First-launch behavior

When the user runs `FX_Machine.exe` for the first time:

1. Windows may show a SmartScreen warning (see "Antivirus and SmartScreen")
2. The app launches and creates `config/active.toml` from `default.toml`
3. The app creates `logs/fxmachine.log`
4. The UI appears

If Ableton + AbletonOSC are running, the app discovers the session
within ~3 seconds. If not, the UI shows "—" for various fields until
the connection is established.

---

## Build Size Optimization

The default build is ~40-60 MB. Most of this is unavoidable (Python
runtime, Tk, pygame, SDL2). But you can shrink it somewhat:

### Exclude unused modules

In the spec file's `excludes=` list, add modules you don't use:

```python
excludes=[
    'matplotlib',    # not used
    'numpy',         # not used (psutil doesn't need it)
    'PIL',           # not used
    'PyQt5',         # not used
    'PyQt6',         # not used
    'pandas',        # not used
],
```

Don't exclude things you actually use — the .exe will crash at runtime.

### Use UPX compression

UPX compresses .exe and .dll files. Add to the spec file:

```python
exe = EXE(
    ...,
    upx=True,            ← compress the .exe stub
    upx_exclude=[],      ← list of files to skip
)
```

UPX can reduce size by 30-50%. Trade-off: slightly slower startup
(decompression on launch) and some antivirus tools flag UPX-compressed
binaries as suspicious.

### Disable diagnostics dependency

If you're sure you'll never use the diagnostics layer, remove psutil
from your installed packages before building:

```bash
pip uninstall psutil
python build.py
```

Saves ~3 MB. The diagnostics layer will run in degraded mode (no
CPU/RAM metrics) but everything else works.

### Strip debug symbols

PyInstaller already does this by default. No additional action needed.

### Realistic minimum size

After all optimizations, expect ~30-40 MB. Going below 30 MB requires
giving up Tk (switching to a lighter UI framework) or removing pygame
(losing gamepad support). Not worth the trade-offs.

---

## Common Build Failures

### "PyInstaller is not installed"

```
❌ PyInstaller is not installed.
   Run:  pip install pyinstaller
```

Fix:
```bash
pip install pyinstaller
```

### "Spec file not found: FX_Machine.spec"

You don't have the spec file. Generate it once:

```bash
python -m PyInstaller --noconfirm --name FX_Machine --onedir run.py
```

This creates `FX_Machine.spec` in the project root. Subsequent builds
use this file.

### "config/ folder not found"

The build script expects `config/default.toml`, `config/EXAMPLES.toml`,
and `config/README.md` to exist. Verify:

```bash
dir config
```

If any are missing, the build can't ship them.

### "PyInstaller failed with exit code N"

Look at the PyInstaller output above this message. Common causes:

- **"FileNotFoundError" for a hook file:** A PyInstaller hook (auto-
  generated bundling rules) is broken. Update PyInstaller:
  `pip install --upgrade pyinstaller`
- **"Unable to find module X":** Add X to `hiddenimports` in the spec
  file
- **Permission errors:** Run as administrator, or close any program
  holding files in `dist/` or `build/`
- **Antivirus blocking writes:** Temporarily disable real-time
  protection or add the project folder to exclusions

### "Build completed but .exe not found"

PyInstaller succeeded but produced a different filename. Check:

```bash
dir dist\FX_Machine
```

If you see something like `FX_Machine.exe.bak` or a different name,
your spec file's `name=` field doesn't match what `build.py` expects.
Update the spec file or rename the output.

### "ModuleNotFoundError" at runtime (works from source)

PyInstaller didn't detect a dynamically-imported module. Add it to
`hiddenimports` in the spec file:

```python
hiddenimports=[
    'src.some_module',
    'package.subpackage.module',
],
```

Rebuild and test.

### "DLL load failed" on launch

A native dependency (SDL2, Tk runtime, Python DLL) isn't being
bundled correctly. Check `_internal/` for the missing DLL. If absent,
PyInstaller's hook for the parent package needs updating. Workaround:
manually copy the missing DLL from your Python environment into
`_internal/`.

### App runs from source but built .exe crashes immediately

Run from command line to see the error:

```bash
dist\FX_Machine\FX_Machine.exe
```

If the .exe was built with `console=False`, you won't see errors —
rebuild with `console=True` temporarily to see what's happening.

---

## Antivirus and SmartScreen

Windows treats unsigned executables with suspicion. Common issues:

### Windows SmartScreen warning

First-time users see:

```
Windows protected your PC
Microsoft Defender SmartScreen prevented an unrecognized app from starting...
[Don't run]  [More info]
```

To run anyway: Click "More info" → "Run anyway".

This warning appears because the .exe isn't code-signed by a trusted
publisher. To eliminate it, you'd need a code signing certificate
(~$80-200/year from Sectigo, DigiCert, etc.).

### Antivirus false positives

Some antivirus tools flag PyInstaller-built executables as suspicious
because they're statistically similar to malware (a packaged executable
extracting and running code at startup).

If your antivirus blocks the .exe:

1. Add the entire `dist/FX_Machine/` folder to the antivirus's
   exclusion list
2. Or scan the .exe with [VirusTotal](https://www.virustotal.com/)
   to confirm it's a false positive
3. For widespread distribution, submit the .exe to your antivirus
   vendor as a false positive report

### UPX-compressed binaries

If you used UPX compression, antivirus false-positive rates increase
significantly. Many antivirus tools flag ALL UPX-compressed
executables. Consider disabling UPX in your spec file for distribution
builds.

---

## Code Signing (Optional)

For professional distribution, code-sign your .exe:

### What it does

A code signing certificate ties the .exe to a verified publisher
identity. Windows recognizes the signature and:
- Suppresses SmartScreen warnings (after some reputation building)
- Shows your publisher name in the UAC prompt
- Reduces antivirus false positives

### What you need

- A code signing certificate from a trusted CA:
  - Sectigo (~$80/year)
  - DigiCert (~$400/year)
  - SSL.com (~$120/year)
- The `signtool.exe` from Windows SDK
- Your certificate file (.pfx)

### Signing the .exe

```bash
signtool sign /f your_cert.pfx /p your_password /t http://timestamp.digicert.com /fd sha256 dist\FX_Machine\FX_Machine.exe
```

Verify:
```bash
signtool verify /pa dist\FX_Machine\FX_Machine.exe
```

### When to sign

- Public distribution (yes, sign)
- Sharing with friends (probably overkill, but eliminates warnings)
- Commercial product (definitely sign)
- Personal use only (don't bother)

Code signing is outside the scope of FX Machine itself — it's a
distribution concern.

---

## Creating an Installer

For end users who don't know how to extract zip files, you can create
an installer. Options:

### Inno Setup (recommended, free)

[Inno Setup](https://jrsoftware.org/isinfo.php) is a popular open-
source installer creator. It produces a single `.exe` installer that:

- Extracts files to `C:\Program Files\FX Machine\`
- Creates Start menu shortcuts
- Creates desktop shortcut (optional)
- Registers an uninstaller in Windows
- Optionally requires admin rights or installs per-user

Basic Inno Setup script for FX Machine:

```iss
[Setup]
AppName=FX Machine
AppVersion=1.0.0
DefaultDirName={pf}\FX Machine
DefaultGroupName=FX Machine
OutputBaseFilename=FX_Machine_v1.0.0_Setup
Compression=lzma2
SolidCompression=yes

[Files]
Source: "dist\FX_Machine\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs

[Icons]
Name: "{group}\FX Machine"; Filename: "{app}\FX_Machine.exe"
Name: "{commondesktop}\FX Machine"; Filename: "{app}\FX_Machine.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"
```

Save as `installer.iss`, then compile with Inno Setup IDE.

### NSIS (more complex)

[NSIS](https://nsis.sourceforge.io/) is more powerful but has a
steeper learning curve. Use if you need custom installer UI or
scripting.

### MSI installer (enterprise)

For enterprise deployment, you'd want a .msi installer (Windows
Installer format). Tools: WiX Toolset (free), Advanced Installer
(commercial).

### Should you bother?

For most use cases, a zip is fine. Recipients extract once and run.
Installer adds installation/uninstallation complexity that's not
needed for a single-folder app like FX Machine.

---

## Building for Other Platforms

PyInstaller can target:
- **Windows** (.exe) ← current setup
- **macOS** (.app)
- **Linux** (binary)

But: **You must build on the target platform.** A Windows machine
cannot build a macOS .app. You'd need:

- Windows machine for Windows builds
- Mac for macOS builds
- Linux machine (or VM/container) for Linux builds

### macOS build

On a Mac with Python installed:

```bash
pip install pyinstaller pygame python-osc psutil
python build.py
```

The build script would need adjustments for macOS-specific paths
and the `.app` bundle structure. Currently, `build.py` is written
for Windows. Adding macOS support requires:

- Different output path handling
- `.app` bundle wrapping
- macOS-specific code signing (Apple Developer ID)
- Notarization for distribution outside the Mac App Store

### Linux build

On Linux with Python installed:

```bash
pip install pyinstaller pygame python-osc psutil
python build.py
```

Produces a binary that runs on similar Linux distributions. Cross-
distro compatibility requires AppImage or similar packaging.

### Cross-platform consideration

FX Machine v1.0.0 is Windows-only because:
1. Development was on Windows
2. Tkinter UI hasn't been tested on other platforms
3. Path handling assumes Windows conventions in some places
4. AbletonOSC works on all platforms, so the audio side is portable

A proper cross-platform release would require porting effort. Future
versions may support macOS/Linux.

---

## Continuous Integration

For serious release management, automate builds with CI:

### GitHub Actions example

```yaml
# .github/workflows/build.yml
name: Build FX Machine

on:
  push:
    tags: ['v*']

jobs:
  build-windows:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.12'
      - run: pip install pyinstaller pygame python-osc psutil
      - run: python build.py
      - run: python inspect_exe.py
      - uses: actions/upload-artifact@v3
        with:
          name: FX_Machine_Windows
          path: dist/FX_Machine/
```

Every time you push a tag like `v1.0.0`, GitHub builds the .exe and
uploads it as a release artifact. No manual building needed.

### Why bother

- Reproducible builds (always same environment)
- Builds happen on a clean machine (no dev artifacts contaminating)
- Multiple platforms (Windows, Mac, Linux) from one repo
- Release notes auto-generated from git tags

Overkill for personal projects, essential for serious distribution.

---

## Versioning Your Builds

Use semantic versioning (semver): `MAJOR.MINOR.PATCH`

- **MAJOR:** Breaking changes (incompatible with old configs)
- **MINOR:** New features (backward compatible)
- **PATCH:** Bug fixes only (no new features)

### Where to set the version

```python
# src/config.py
VERSION = "1.0.0"
```

Update this BEFORE building. The version appears:
- In the window title bar
- In the diagnostic tool output
- In log files
- In the .exe's file properties (with proper spec file configuration)

### Tagging in git

```bash
git tag -a v1.0.0 -m "First stable release"
git push --tags
```

Tags let you easily check out a specific version later. Combined with
CI, tagging triggers automated builds.

### Release naming

When you ship a zip:

```
FX_Machine_v1.0.0_Windows.zip
```

Include:
- App name
- Version
- Platform

Don't ship `FX_Machine.zip` without a version — recipients can't tell
old from new.

---

## Hosting and Sharing Builds

### For free distribution

- **GitHub Releases:** Free, integrates with git tags, 2 GB per file
  limit. Best for open-source projects.
- **Google Drive / Dropbox:** Free up to a limit, easy sharing via
  links. Recipients need a free account (usually) to download.
- **WeTransfer:** No account needed for recipients, 2 GB free
  transfers, links expire after 7 days. Good for one-off shares.

### For paid distribution

- **Gumroad:** Sell your app for a fee. Handles payments, license
  keys (optional), customer downloads.
- **Itch.io:** Originally for indie games, also hosts other software.
  Pay-what-you-want or fixed price.
- **Your own website:** Most control, requires hosting and bandwidth.

### What to ship

A single zip containing:
- `FX_Machine/` folder (the built app)
- `docs/` folder (the documentation)
- `README.txt` (quick install instructions for non-technical users)
- `LICENSE.txt` (the license terms)

Optionally:
- A short video showing how to install and use it
- Screenshots
- Demo Ableton project file

---

## Updating End Users

When you release a new version, users need to know:

### Update strategy A — Manual

User downloads new zip, extracts over old folder. Their `active.toml`
gets overwritten unless they back it up first.

To prevent config loss:

1. User extracts new zip to a DIFFERENT folder (e.g., `FX_Machine_v1.1.0/`)
2. User copies their `config/active.toml` from old to new
3. User deletes old folder when comfortable

### Update strategy B — Built-in update notification

Add code that checks a remote version file on launch:

```python
# Pseudocode
import urllib.request
import json

def check_for_update():
    try:
        with urllib.request.urlopen("https://example.com/fxmachine/version.json", timeout=2) as r:
            data = json.load(r)
            latest = data["version"]
            if latest != VERSION:
                push_notification(f"Update available: v{latest}", "info", 5.0)
    except Exception:
        pass  # offline, skip
```

Not implemented in v1.0.0 but architecturally simple to add.

### Update strategy C — Installer with auto-update

Use an installer framework (Inno Setup + a third-party updater) that
handles updates seamlessly. Most complex, most user-friendly.

For a hobby project, manual updates are fine.

---

## Build Artifact Cleanup

After building, these temporary files/folders accumulate:

```
build/                       PyInstaller's intermediate build artifacts
dist/FX_Machine/             The output (you keep this)
__pycache__/                 Python bytecode caches (in every src/ folder)
*.spec.bak                   Spec file backups (occasionally)
```

### Manual cleanup

```bash
# Windows
rmdir /s /q build
del /s /q __pycache__

# PowerShell
Remove-Item -Recurse -Force build
Get-ChildItem -Recurse -Directory __pycache__ | Remove-Item -Recurse -Force
```

The `build.py` script automatically removes `dist/FX_Machine/` and
`build/` before each build, so you don't usually need to manually clean.

### .gitignore for build artifacts

Already in FX Machine's `.gitignore`:

```
build/
dist/
__pycache__/
*.pyc
```

These never get committed to git, keeping the repo clean.

---

## Troubleshooting Build-Specific Issues

### "Build works on my machine but not on the recipient's"

Most likely cause: the recipient's Windows is missing the Visual C++
Runtime that pygame's SDL2 requires.

Fix: Install [Microsoft Visual C++ Redistributable](https://aka.ms/vs/17/release/vc_redist.x64.exe)
on the recipient's machine.

PyInstaller doesn't bundle the C++ runtime because it's a system
component. Most Windows 10/11 machines have it already, but not all.

### "App starts but window doesn't appear"

The .exe is launching but the Tkinter window isn't showing. Possible
causes:

- Tkinter DLLs missing from `_internal/`
- Display server issue (very rare on Windows)
- The window is appearing OFF-SCREEN (saved position from a different
  monitor configuration)

Run with `console=True` in the spec file and check the log output.

### "App appears, then crashes after a few seconds"

Likely an unhandled exception in a background thread. Check
`logs/fxmachine.log` for stack traces.

### "OSC doesn't work in the .exe but works from source"

Most likely a firewall is blocking the .exe specifically. From source,
you're running `python.exe` (already trusted). The new `FX_Machine.exe`
hasn't been seen before and may need firewall permission.

Fix: Add a Windows Firewall rule allowing FX_Machine.exe through.

### "Diagnostics log files aren't being created"

The .exe's working directory may differ from your dev environment.
Logs are written to `logs/` relative to the .exe location.

Verify the `logs/` folder gets created when the .exe runs. If permissions
prevent writing to the Program Files folder, install elsewhere.

### "Different behavior in built vs source mode"

Investigate:
- Did all modules get bundled? Run `python inspect_exe.py`.
- Are config files identical? Compare `dist/FX_Machine/config/default.toml`
  with `config/default.toml`.
- Are there environment differences (PATH, Python version, locale)?

The built .exe is supposed to behave identically to source mode. If
it doesn't, the build is incomplete or the spec file is misconfigured.

---

*This document describes the build and distribution process as it
stands for FX Machine v1.0.0 using PyInstaller 6.x onedir mode. Future
versions may switch to different bundling approaches (Nuitka, PyOxidizer,
or a different framework's native build tools) — check the main README
for current build instructions.*

```