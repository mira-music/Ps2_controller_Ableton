# -*- mode: python ; coding: utf-8 -*-
"""
================================================================================
  FX_Machine.spec — PyInstaller specification (ONEDIR mode)
================================================================================
  Builds a folder containing FX_Machine.exe + all dependencies + config files.
  This is the most reliable PyInstaller mode — no runtime extraction, no
  bundled-data-file shenanigans, just a regular folder you can zip and ship.

  Output: dist/FX_Machine/  (a folder containing everything)
================================================================================
"""

from PyInstaller.utils.hooks import collect_submodules
from pathlib import Path
import shutil

PROJECT_ROOT = Path(SPECPATH).resolve()

# ─── Explicit module list (belt-and-suspenders) ───
src_modules = [
    'src',
    'src.config',
    'src.config_loader',
    'src.state',
    'src.helpers',
    'src.log_setup',
    'src.main',

    'src.osc',
    'src.osc.client',
    'src.osc.server',
    'src.osc.discovery',

    'src.engine',
    'src.engine.actions',
    'src.engine.eq',
    'src.engine.fx',
    'src.engine.momentary',
    'src.engine.navigation',
    'src.engine.polling',

    'src.controller',
    'src.controller.axes',
    'src.controller.buttons',
    'src.controller.loop',
    'src.controller.watchdog',

    'src.ui',
    'src.ui.builder',
    'src.ui.palette',
    'src.ui.updater',
    'src.ui.widgets',
]

auto_submodules = (
    collect_submodules('src')
    + collect_submodules('src.osc')
    + collect_submodules('src.engine')
    + collect_submodules('src.controller')
    + collect_submodules('src.ui')
)

third_party_hidden = [
    'pygame',
    'pythonosc',
    'pythonosc.dispatcher',
    'pythonosc.osc_server',
    'pythonosc.udp_client',
]

all_hidden_imports = list(set(src_modules + auto_submodules + third_party_hidden))

# ─── Analysis ───
a = Analysis(
    [str(PROJECT_ROOT / 'run.py')],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=[],  # We'll copy config files manually after build — much more reliable
    hiddenimports=all_hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

# ─── EXE (just the executable wrapper, NOT one-file mode) ───
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,    # CRITICAL: binaries go in COLLECT, not in EXE
    name='FX_Machine',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,            # GUI app, no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

# ─── COLLECT (gathers all dependencies into one folder) ───
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='FX_Machine',
)