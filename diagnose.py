#!/usr/bin/env python3
"""
================================================================================
  FX Machine — Diagnostic Tool
================================================================================
  Comprehensive health check for the FX Machine codebase.
  Run BEFORE every commit, AFTER every refactor, BEFORE every show.

  Usage:
      python diagnose.py            # full check
      python diagnose.py --quick    # skip slow tests (no OSC/gamepad/git)
      python diagnose.py --verbose  # show every check, not just failures

  Exit codes:
      0 = all checks passed
      1 = warnings only (still safe to run)
      2 = errors found (do NOT run the app until fixed)

  Fixes applied:
    - check_cfg_singleton() was duplicated (the full deep-check body ran,
      then the same critical-attrs-only body ran again immediately after,
      printing the "cfg Singleton Health" header twice). Second copy removed.
    - check_dead_imports() header updated to clarify false positives are
      possible (attribute access patterns like module.NAME are not tracked).
    - check_imports() gains a display-server guard so headless environments
      (CI, SSH without DISPLAY) don't crash when importing src.main which
      pulls in tkinter at module level.
    - check_toml_config() required_sections loop removed — it was redundant
      with the _CFG_MAP cross-reference check that follows it and already
      catches missing keys at leaf level.
    - check_osc_ports() success message corrected to note that UDP sendto
      only verifies the local network stack, not that Ableton is listening.
    - build.py PyInstaller pre-check noted in check_project_structure comments.
================================================================================
"""

import sys
import os
import ast
import importlib
import importlib.util
import time
import socket
from pathlib import Path

# ═══════════════════════════════════════════════════════════════════════════
#  CLI ARGS
# ═══════════════════════════════════════════════════════════════════════════

QUICK   = "--quick"   in sys.argv
VERBOSE = "--verbose" in sys.argv

# ═══════════════════════════════════════════════════════════════════════════
#  SUPPRESS PYGAME GREETING
# ═══════════════════════════════════════════════════════════════════════════

os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'

# ═══════════════════════════════════════════════════════════════════════════
#  ANSI COLORS (Windows 10+ supports these natively)
# ═══════════════════════════════════════════════════════════════════════════

try:
    import ctypes
    kernel32 = ctypes.windll.kernel32
    kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
except Exception:
    pass


class C:
    OK   = "\033[92m"   # green
    WARN = "\033[93m"   # yellow
    FAIL = "\033[91m"   # red
    INFO = "\033[96m"   # cyan
    DIM  = "\033[90m"   # grey
    BOLD = "\033[1m"
    END  = "\033[0m"


# ═══════════════════════════════════════════════════════════════════════════
#  RESULTS TRACKING
# ═══════════════════════════════════════════════════════════════════════════

class Results:
    def __init__(self):
        self.checks  = 0
        self.passed  = 0
        self.warned  = 0
        self.failed  = 0
        self.errors  = []
        self.warns   = []
        self._section_start_passed = 0
        self._section_start_warned = 0
        self._section_start_failed = 0
        self._section_title = ""

    def ok(self, label):
        self.checks += 1
        self.passed += 1
        if VERBOSE:
            print(f"  {C.OK}✓{C.END} {label}")

    def warn(self, label, detail=""):
        self.checks += 1
        self.warned += 1
        msg = f"  {C.WARN}⚠{C.END} {label}"
        if detail:
            msg += f"\n      {C.DIM}{detail}{C.END}"
        print(msg)
        self.warns.append(label)

    def fail(self, label, detail=""):
        self.checks += 1
        self.failed += 1
        msg = f"  {C.FAIL}✗{C.END} {label}"
        if detail:
            msg += f"\n      {C.DIM}{detail}{C.END}"
        print(msg)
        self.errors.append(label)


R = Results()


# ═══════════════════════════════════════════════════════════════════════════
#  PRETTY OUTPUT
# ═══════════════════════════════════════════════════════════════════════════

def header(title):
    print(f"\n{C.BOLD}{C.INFO}━━━ {title} ━━━{C.END}")
    R._section_start_passed = R.passed
    R._section_start_warned = R.warned
    R._section_start_failed = R.failed
    R._section_title = title


def section_summary():
    """Print a compact pass summary in non-verbose mode when no issues occurred."""
    if VERBOSE:
        return
    new_passed = R.passed - R._section_start_passed
    new_warned = R.warned - R._section_start_warned
    new_failed = R.failed - R._section_start_failed
    if new_warned == 0 and new_failed == 0 and new_passed > 0:
        print(f"  {C.OK}✓{C.END} {new_passed} check(s) passed")


def info(msg):
    print(f"  {C.INFO}ℹ{C.END} {msg}")


# ═══════════════════════════════════════════════════════════════════════════
#  CHECK 1 — PYTHON VERSION
# ═══════════════════════════════════════════════════════════════════════════

def check_python_version():
    header("Python Version")

    v = sys.version_info
    version_str = f"{v.major}.{v.minor}.{v.micro}"

    if v.major == 3 and v.minor >= 11:
        R.ok(f"Python {version_str} (tomllib available as built-in)")
    elif v.major == 3 and v.minor >= 8:
        R.warn(
            f"Python {version_str}",
            "Below 3.11 — tomllib not built-in, TOML loading will fail. "
            "Upgrade to Python 3.11+."
        )
    else:
        R.fail(
            f"Python {version_str}",
            "Need Python 3.11+ for tomllib and full functionality."
        )

    section_summary()


# ═══════════════════════════════════════════════════════════════════════════
#  CHECK 2 — REQUIRED THIRD-PARTY PACKAGES
# ═══════════════════════════════════════════════════════════════════════════

def check_dependencies():
    header("Third-Party Dependencies")

    required = {
        "pygame":    "Gamepad input (required). Install: pip install pygame",
        "pythonosc": "OSC communication (required). Install: pip install python-osc",
    }

    for pkg, desc in required.items():
        try:
            mod = importlib.import_module(pkg)
            ver = getattr(mod, "__version__", "unknown")
            R.ok(f"{pkg} {ver}")
        except ImportError:
            R.fail(f"Missing package: {pkg}", desc)

    builtins = {
        "tomllib": "TOML parser (built-in to Python 3.11+)",
        "tkinter": "UI toolkit (standard library)",
    }
    for pkg, desc in builtins.items():
        try:
            importlib.import_module(pkg)
            R.ok(f"{pkg} (built-in)")
        except ImportError:
            R.fail(f"Missing built-in: {pkg}", desc)

    section_summary()


# ═══════════════════════════════════════════════════════════════════════════
#  CHECK 3 — PROJECT STRUCTURE
# ═══════════════════════════════════════════════════════════════════════════

def check_project_structure():
    header("Project Structure")

    required = {
        "run.py":                     "Entry point",
        "build.py":                   "PyInstaller builder",
        "README.md":                  "Project documentation",
        ".gitignore":                 "Git ignore rules",
        "src/__init__.py":            "src package marker",
        "src/config.py":              "Hardcoded architectural constants",
        "src/config_loader.py":       "TOML loader + cfg singleton",
        "src/state.py":               "Shared state + thread locks",
        "src/helpers.py":             "Utility functions",
        "src/log_setup.py":           "Logging configuration",
        "src/main.py":                "Application entry point",
        "src/osc/__init__.py":        "osc package marker",
        "src/osc/client.py":          "OSC send functions",
        "src/osc/server.py":          "OSC receive handlers",
        "src/osc/discovery.py":       "Ableton session discovery",
        "src/engine/__init__.py":     "engine package marker",
        "src/engine/eq.py":           "EQ mode engine",
        "src/engine/fx.py":           "FX macro stick driver",
        "src/engine/navigation.py":   "Scene/track/bookmark navigation",
        "src/engine/actions.py":      "Discrete button actions",
        "src/engine/momentary.py":    "Momentary FX effects",
        "src/engine/polling.py":      "Background polling + EQ ramp",
        "src/controller/__init__.py": "controller package marker",
        "src/controller/buttons.py":  "Button press/release handlers",
        "src/controller/axes.py":     "Axis + D-pad handlers",
        "src/controller/watchdog.py": "Controller health + recovery",
        "src/controller/loop.py":     "Main controller thread (125 Hz)",
        "src/ui/__init__.py":         "ui package marker",
        "src/ui/palette.py":          "Colors + typography",
        "src/ui/widgets.py":          "Canvas renderers",
        "src/ui/builder.py":          "Tkinter UI construction",
        "src/ui/updater.py":          "UI update loop (40 Hz)",
        "config/default.toml":        "Factory config template (do not edit)",
        "config/README.md":           "Config folder explainer",
        "config/EXAMPLES.toml":       "Preset snippets",
    }

    for path, desc in required.items():
        if Path(path).is_file():
            R.ok(f"{path}")
        else:
            R.fail(f"Missing: {path}", desc)

    optional = {
        "config/active.toml":  "Created automatically on first run (OK if missing)",
        "config/presets/":     "User preset folder",
        "logs/":               "Log output folder (created at runtime)",
        "docs/screenshots/":   "README screenshots",
        "FX_Machine.spec":     "PyInstaller spec file (needed for build.py)",
    }

    for path, desc in optional.items():
        p = Path(path)
        if p.exists():
            R.ok(f"{path} (optional, present)")
        else:
            if VERBOSE:
                print(f"  {C.DIM}○ {path} — not present ({desc}){C.END}")

    section_summary()


# ═══════════════════════════════════════════════════════════════════════════
#  CHECK 4 — PYTHON SYNTAX (AST compile-check every .py file)
# ═══════════════════════════════════════════════════════════════════════════

def check_python_syntax():
    header("Python Syntax (AST compile-check)")

    py_files = list(Path("src").rglob("*.py"))
    py_files += [Path("run.py"), Path("build.py"), Path("diagnose.py")]

    for py_file in py_files:
        if not py_file.exists():
            continue
        try:
            with open(py_file, "r", encoding="utf-8") as f:
                source = f.read()
            ast.parse(source, filename=str(py_file))
            R.ok(f"{py_file}")
        except SyntaxError as e:
            R.fail(f"Syntax error in {py_file}",
                   f"Line {e.lineno}: {e.msg}")
        except Exception as e:
            R.fail(f"Cannot read {py_file}", str(e))

    section_summary()


# ═══════════════════════════════════════════════════════════════════════════
#  CHECK 5 — IMPORT RESOLUTION
# ═══════════════════════════════════════════════════════════════════════════

def check_imports():
    header("Module Imports")

    modules_to_check = [
        "src.config",
        "src.state",
        "src.helpers",
        "src.log_setup",
        "src.config_loader",
        "src.osc.client",
        "src.osc.server",
        "src.osc.discovery",
        "src.engine.polling",
        "src.engine.momentary",
        "src.engine.navigation",
        "src.engine.actions",
        "src.engine.eq",
        "src.engine.fx",
        "src.controller.watchdog",
        "src.controller.buttons",
        "src.controller.axes",
        "src.controller.loop",
        "src.ui.palette",
        "src.ui.widgets",
        "src.ui.builder",
        "src.ui.updater",
        "src.main",
    ]

    for mod_name in modules_to_check:
        try:
            if mod_name in sys.modules:
                del sys.modules[mod_name]
            importlib.import_module(mod_name)
            R.ok(f"import {mod_name}")
        except ImportError as e:
            # Distinguish display-server failures (headless environments) from
            # real import errors so CI pipelines aren't broken by tkinter
            # requiring a display when importing src.main or src.ui.*.
            err_str = str(e).lower()
            if any(kw in err_str for kw in ("display", "tkinter", "_tkinter", "no module named '_tkinter'")):
                R.warn(
                    f"import {mod_name} (headless environment — no display server)",
                    f"{type(e).__name__}: {e}. This is expected on CI/SSH without DISPLAY."
                )
            else:
                R.fail(f"Cannot import {mod_name}",
                       f"{type(e).__name__}: {e}")
        except Exception as e:
            R.fail(f"Cannot import {mod_name}",
                   f"{type(e).__name__}: {e}")

    section_summary()


# ═══════════════════════════════════════════════════════════════════════════
#  CHECK 6 — TOML CONFIG VALIDATION
# ═══════════════════════════════════════════════════════════════════════════

def check_toml_config():
    header("TOML Configuration")

    try:
        import tomllib
    except ImportError:
        R.fail("tomllib not available", "Need Python 3.11+")
        section_summary()
        return

    # ── Parse default.toml ──────────────────────────────────────────────
    default = Path("config/default.toml")
    if not default.exists():
        R.fail("config/default.toml missing",
               "Required as the factory template and fallback.")
        section_summary()
        return

    try:
        with open(default, "rb") as f:
            default_data = tomllib.load(f)
        R.ok("config/default.toml parses correctly")
    except tomllib.TOMLDecodeError as e:
        R.fail("config/default.toml has syntax errors", str(e))
        section_summary()
        return

    # ── Parse active.toml (optional) ────────────────────────────────────
    active = Path("config/active.toml")
    if active.exists():
        try:
            with open(active, "rb") as f:
                active_data = tomllib.load(f)
            R.ok("config/active.toml parses correctly")
        except tomllib.TOMLDecodeError as e:
            R.fail(
                "config/active.toml has syntax errors",
                f"{e}\nDelete it and restart the app to regenerate from default.toml."
            )
    else:
        if VERBOSE:
            print(f"  {C.DIM}○ config/active.toml not present "
                  f"(will be created on first run){C.END}")

    # ── Cross-reference _CFG_MAP against default.toml ───────────────────
    # This is the authoritative check: every key the loader maps to must
    # exist in default.toml. Section-level checks are not needed because
    # a missing section implies missing leaf keys, which this catches.
    def nested_get(d, path):
        cur = d
        for k in path:
            if not isinstance(cur, dict) or k not in cur:
                return None
            cur = cur[k]
        return cur

    try:
        if "src.config_loader" in sys.modules:
            del sys.modules["src.config_loader"]
        from src.config_loader import _CFG_MAP

        unreachable = []
        for attr, path in _CFG_MAP:
            value = nested_get(default_data, path)
            if value is None:
                unreachable.append(f"{attr} ← {'.'.join(path)}")

        if unreachable:
            R.warn(
                f"Loader maps {len(unreachable)} key(s) not present in default.toml",
                f"First few: {unreachable[:5]}\n"
                f"      These fall back to hardcoded defaults from src/config.py, "
                f"which is safe but means the key is undocumented in default.toml."
            )
        else:
            R.ok(f"All {len(_CFG_MAP)} loader mappings resolve to keys in default.toml")

    except Exception as e:
        R.fail("Cannot validate loader mappings against default.toml", str(e))

    section_summary()


# ═══════════════════════════════════════════════════════════════════════════
#  CHECK 7 — CFG SINGLETON SANITY + DEEP cfg.X REFERENCE CHECK
# ═══════════════════════════════════════════════════════════════════════════

def check_cfg_singleton():
    """
    Two-part check:

    Part A — Critical attribute presence:
      Verifies a set of known-required cfg attributes exist and are not None.
      Fast sanity check that the singleton initialized correctly.

    Part B — Deep AST reference walk:
      Scans every src/*.py file for cfg.ATTR references and verifies that
      ATTR actually exists on the singleton. This catches the class of bug
      where code references cfg.SOME_VALUE that was never added to
      _RuntimeConfig.__init__(). These bugs would crash at runtime during
      a show but are invisible to syntax checking and basic imports.

    Previously this function had its body duplicated — the deep check ran,
    then the critical-attrs-only check ran again with a second header print.
    The duplicate has been removed.
    """
    header("cfg Singleton Health")

    try:
        if "src.config_loader" in sys.modules:
            del sys.modules["src.config_loader"]
        from src.config_loader import cfg

        # ── Part A: Critical attributes ──────────────────────────────────
        critical_attrs = [
            # EQ encoder
            "EQ_SWEEP_SECONDS",
            "EQ_ENCODER_CURVE_EXP",
            "EQ_AXIS_DEAD_ZONE",
            "EQ_FLICK_TIMEOUT_MS",
            "EQ_BASS_BOOST_CAP",
            "EQ_WRITE_EPSILON",
            "EQ_WRITE_THROTTLE",
            "EQ_DETENT_RANGE",
            "EQ_DETENT_MIN_FACTOR",
            "EQ_BOOST_PCT",
            "EQ_RAMP_MIN_MS",
            "EQ_RAMP_MAX_MS",
            # TRIM
            "TRIM_SWEEP_SECONDS",
            "TRIM_DEAD_ZONE",
            "TRIM_MAX_DB",
            "TRIM_WRITE_THROTTLE",
            "TRIM_WRITE_EPSILON",
            "TRIM_DETENT_RANGE",
            "TRIM_DETENT_MIN_FACTOR",
            # FX
            "FX_AXIS_DEAD_ZONE",
            "FX_WRITE_THROTTLE",
            "FX_WRITE_EPSILON_FRAC",
            "FX_ACCEL_RAMP_S",
            "FX_ACCEL_MAX_MULT",
            "FX_DELAY_FB_STEPS",
            "FX_DELAY_FB_CLAMP_FRAC",
            "FX_DELAY_FB_DEBOUNCE",
            # Meter
            "METER_REFERENCE_OFFSET_DB",
            "METER_RELEASE_DB_PER_SEC",
            "METER_PEAK_HOLD_SECONDS",
            "METER_PEAK_FALL_DB_PER_SEC",
            "METER_CLIP_WARN_DB",
            "METER_CLIP_CRITICAL_DB",
            "METER_CLIP_FLICKER_HZ",
            "METER_CLIP_FADEOUT_SECONDS",
            # Volume
            "VOL_DEAD_ZONE",
            "VOL_SENSITIVITY",
            "ABLETON_UNITY",
            "VOL_CHANGE_THRESHOLD",
            # Navigation
            "ANALOG_THRESHOLD",
            "HOLD_SCROLL_DELAY",
            "HOLD_SCROLL_RATE",
            "SMOOTHING_FACTOR",
            "DPAD_DEBOUNCE",
            # Timing
            "R3_DOUBLE_CLICK_WINDOW",
            "QUERY_DEFER_TIME",
            "FX_SAFETY_POLL_INTERVAL",
            "WATCHDOG_INTERVAL",
            "IDLE_REPROBE_AFTER",
            "SELECT_RECONCILE_INTERVAL",
            # UI
            "UI_REFRESH_MS",
            "BLINK_PERIOD_MS",
            "WINDOW_WIDTH",
            "WINDOW_HEIGHT",
            # Network
            "OSC_HOST",
            "OSC_SEND_PORT",
            "OSC_RECEIVE_PORT",
        ]

        missing_attrs = []
        for attr in critical_attrs:
            if not hasattr(cfg, attr):
                missing_attrs.append(attr)
                R.fail(f"cfg.{attr} MISSING")
            else:
                val = getattr(cfg, attr)
                if val is None:
                    R.warn(f"cfg.{attr} is None")
                else:
                    R.ok(f"cfg.{attr} = {val!r}")

        if missing_attrs:
            R.fail(
                f"cfg singleton is missing {len(missing_attrs)} critical attribute(s)",
                "Missing: " + ", ".join(missing_attrs)
            )

        # ── Part B: Deep AST cfg.X reference walk ────────────────────────
        # Walk every src/*.py file. Find every `cfg.ATTR` attribute access.
        # Check that ATTR exists on the singleton. Report any that don't.
        #
        # This catches: a developer writes cfg.NEW_THING in code but forgets
        # to add NEW_THING to _RuntimeConfig.__init__(). The code passes syntax
        # check and imports fine, but crashes with AttributeError at the
        # exact moment that code path executes — potentially mid-show.

        cfg_references = set()   # set of (attr_name, source_file_path)

        for py_file in Path("src").rglob("*.py"):
            try:
                with open(py_file, "r", encoding="utf-8") as f:
                    source = f.read()
                tree = ast.parse(source, filename=str(py_file))
            except Exception:
                continue

            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute):
                    if (isinstance(node.value, ast.Name) and
                            node.value.id == "cfg"):
                        cfg_references.add((node.attr, str(py_file)))

        broken_refs = []
        for attr, source_file in sorted(cfg_references):
            if not hasattr(cfg, attr):
                broken_refs.append((attr, source_file))

        if broken_refs:
            R.fail(
                f"Found {len(broken_refs)} broken cfg.X reference(s) in source code",
                "These will raise AttributeError at runtime — fix before any show."
            )
            for attr, source_file in broken_refs[:10]:
                print(
                    f"      {C.FAIL}✗{C.END} cfg.{attr} "
                    f"referenced in {source_file} — attribute NOT in singleton"
                )
            if len(broken_refs) > 10:
                print(f"      {C.DIM}... and {len(broken_refs) - 10} more{C.END}")
        else:
            R.ok(
                f"All {len(cfg_references)} cfg.ATTR reference(s) in source "
                f"resolve correctly on the singleton"
            )

    except Exception as e:
        R.fail("Cannot inspect cfg singleton", str(e))

    section_summary()


# ═══════════════════════════════════════════════════════════════════════════
#  CHECK 8 — LOG FOLDER WRITABLE
# ═══════════════════════════════════════════════════════════════════════════

def check_log_folder():
    header("Log Folder")

    log_dir = Path("logs")
    try:
        log_dir.mkdir(exist_ok=True)
        test_file = log_dir / ".diagnose_write_test"
        test_file.write_text("test")
        test_file.unlink()
        R.ok("logs/ folder is writable")
    except Exception as e:
        R.fail("Cannot write to logs/", str(e))

    existing_log = log_dir / "fxmachine.log"
    if existing_log.exists():
        size_mb = existing_log.stat().st_size / (1024 * 1024)
        R.ok(f"Existing log file: {size_mb:.2f} MB")
        if size_mb > 40:
            R.warn(
                f"Log file is large ({size_mb:.1f} MB)",
                "Rotation should handle this automatically (5 MB × 10 backups = 50 MB max)."
            )

    section_summary()


# ═══════════════════════════════════════════════════════════════════════════
#  CHECK 9 — DEAD IMPORTS HINT
# ═══════════════════════════════════════════════════════════════════════════

def check_dead_imports():
    """
    AST-based scan for imported names that don't appear to be used.

    IMPORTANT: False positives are expected and common. This checker only
    tracks bare Name nodes (e.g. `clamp(x)`). It does NOT track:
      - Attribute access (e.g. `helpers.clamp` — 'clamp' would look unused)
      - String references (e.g. used in getattr() or eval())
      - Re-exports (imported then exported from __init__.py)
      - Names used only in type annotations

    Treat output as hints for manual review, not as definitive errors.
    All warnings from this section are advisory only.
    """
    header("Dead Code Hints — potentially unused imports (false positives possible)")

    py_files = list(Path("src").rglob("*.py"))

    for py_file in py_files:
        try:
            with open(py_file, "r", encoding="utf-8") as f:
                source = f.read()
            tree = ast.parse(source, filename=str(py_file))
        except Exception:
            continue

        # Collect all names imported via "from X import Y" style
        imported_names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    name = alias.asname or alias.name
                    if name != "*":
                        imported_names.add(name)

        # Collect all identifiers used in the file (excluding import nodes).
        # Tracks bare Name references only — attribute access is handled by
        # walking down to the root of ast.Attribute chains.
        used_names = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            for child in ast.walk(node):
                if isinstance(child, ast.Name):
                    used_names.add(child.id)
                elif isinstance(child, ast.Attribute):
                    # For a.b.c, we add 'a' to used_names (the root object).
                    # 'b' and 'c' are attribute names, not bare identifiers,
                    # so they are NOT added. This means "from x import b; a.b"
                    # would falsely flag 'b' as unused. Known limitation.
                    cur = child
                    while isinstance(cur, ast.Attribute):
                        cur = cur.value
                    if isinstance(cur, ast.Name):
                        used_names.add(cur.id)

        unused = imported_names - used_names
        if unused:
            for name in sorted(unused):
                R.warn(
                    f"{py_file}: '{name}' imported but not detected as used",
                    "May be a false positive — check manually before removing."
                )

    section_summary()


# ═══════════════════════════════════════════════════════════════════════════
#  CHECK 10 — OSC PORT AVAILABILITY
# ═══════════════════════════════════════════════════════════════════════════

def check_osc_ports():
    if QUICK:
        return

    header("OSC Port Availability")

    try:
        from src.config import OSC_HOST, OSC_RECEIVE_PORT, OSC_SEND_PORT
    except Exception as e:
        R.fail("Cannot read OSC config from src.config", str(e))
        section_summary()
        return

    # ── Receive port: try to bind ────────────────────────────────────────
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.bind((OSC_HOST, OSC_RECEIVE_PORT))
        s.close()
        R.ok(f"Receive port {OSC_RECEIVE_PORT} is available (not in use)")
    except OSError as e:
        R.warn(
            f"Receive port {OSC_RECEIVE_PORT} could not be bound",
            f"Port may be in use by another FX Machine instance. Error: {e}"
        )

    # ── Send port: range check ───────────────────────────────────────────
    if 1 <= OSC_SEND_PORT <= 65535:
        R.ok(f"Send port {OSC_SEND_PORT} is in valid range (1-65535)")
    else:
        R.fail(
            f"Send port {OSC_SEND_PORT} out of range",
            "Must be between 1 and 65535."
        )

    # ── Send port: UDP stack smoke test ─────────────────────────────────
    # NOTE: UDP sendto() only verifies the LOCAL network stack can send
    # to this address. It does NOT verify that Ableton or AbletonOSC is
    # listening. A success here does not mean Ableton is running.
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        s.sendto(b"/ping", (OSC_HOST, OSC_SEND_PORT))
        s.close()
        R.ok(
            f"UDP stack can send to {OSC_HOST}:{OSC_SEND_PORT} "
            f"(does NOT confirm Ableton is listening)"
        )
    except Exception as e:
        R.warn(f"UDP send test failed for {OSC_HOST}:{OSC_SEND_PORT}", str(e))

    section_summary()


# ═══════════════════════════════════════════════════════════════════════════
#  CHECK 11 — GAMEPAD DETECTION
# ═══════════════════════════════════════════════════════════════════════════

def check_gamepad():
    if QUICK:
        return

    header("Gamepad Detection")

    try:
        import pygame
        pygame.init()
        pygame.joystick.init()

        count = pygame.joystick.get_count()
        if count == 0:
            R.warn(
                "No gamepad detected",
                "Plug one in before starting the app, or it will run in "
                "NO CONTROLLER mode (OSC and UI still work)."
            )
        else:
            for i in range(count):
                joy = pygame.joystick.Joystick(i)
                joy.init()
                name    = joy.get_name()
                axes    = joy.get_numaxes()
                buttons = joy.get_numbuttons()
                hats    = joy.get_numhats()
                R.ok(f"Gamepad {i}: {name!r}")
                info(f"    {axes} axes, {buttons} buttons, {hats} hats")

                if buttons < 12:
                    R.warn(
                        f"Gamepad {i} has only {buttons} buttons",
                        "FX Machine expects 12+ (PlayStation-style layout). "
                        "Some functions may be unreachable."
                    )
                if axes < 4:
                    R.warn(
                        f"Gamepad {i} has only {axes} axes",
                        "FX Machine expects 4 (two sticks). "
                        "EQ or FX control will be impaired."
                    )
                if hats < 1:
                    R.warn(
                        f"Gamepad {i} has no D-pad (hats=0)",
                        "Bookmark and group navigation via D-pad will not work."
                    )

                joy.quit()

        pygame.quit()

    except Exception as e:
        R.fail("Gamepad check crashed", str(e))

    section_summary()


# ═══════════════════════════════════════════════════════════════════════════
#  CHECK 12 — GIT STATUS
# ═══════════════════════════════════════════════════════════════════════════

def check_git_status():
    if QUICK:
        return

    header("Git Status")

    if not Path(".git").is_dir():
        R.warn(
            ".git folder not found",
            "Project is not under version control. "
            "Strongly recommended before every show."
        )
        section_summary()
        return

    try:
        import subprocess
        result = subprocess.run(
            ["git", "status", "--short"],
            capture_output=True, text=True, timeout=3
        )
        if result.returncode == 0:
            output = result.stdout.strip()
            if not output:
                R.ok("Working tree is clean (nothing uncommitted)")
            else:
                lines = output.split("\n")
                R.warn(
                    f"{len(lines)} uncommitted change(s) in working tree",
                    "Commit your changes before a show so you can roll back "
                    "if something breaks."
                )
                for line in lines[:5]:
                    print(f"      {C.DIM}{line}{C.END}")
                if len(lines) > 5:
                    print(f"      {C.DIM}... and {len(lines) - 5} more{C.END}")
        else:
            R.warn("git status returned non-zero", result.stderr.strip())

    except FileNotFoundError:
        R.warn(
            "git not found in PATH",
            "Install git or add it to PATH to enable this check."
        )
    except subprocess.TimeoutExpired:
        R.warn("git status timed out (>3s)", "Check for a stuck git process.")
    except Exception as e:
        R.warn("git check error", str(e))

    section_summary()


# ═══════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main():
    start = time.time()

    print(f"\n{C.BOLD}{C.INFO}╔{'═' * 62}╗{C.END}")
    print(f"{C.BOLD}{C.INFO}║{' ' * 10}FX MACHINE — DIAGNOSTIC TOOL{' ' * 24}║{C.END}")
    print(f"{C.BOLD}{C.INFO}╚{'═' * 62}╝{C.END}")

    if QUICK:
        info("Quick mode — skipping OSC port, gamepad, and git checks")
    if VERBOSE:
        info("Verbose mode — showing all checks including passed ones")

    check_python_version()
    check_dependencies()
    check_project_structure()
    check_python_syntax()
    check_imports()
    check_toml_config()
    check_cfg_singleton()
    check_log_folder()
    check_dead_imports()
    check_osc_ports()
    check_gamepad()
    check_git_status()

    elapsed = time.time() - start

    print(f"\n{C.BOLD}{'━' * 64}{C.END}")
    print(f"{C.BOLD}SUMMARY{C.END}  ({elapsed:.1f}s)")
    print(f"  Total checks : {R.checks}")
    print(f"  {C.OK}Passed{C.END}       : {R.passed}")
    print(f"  {C.WARN}Warnings{C.END}     : {R.warned}")
    print(f"  {C.FAIL}Failed{C.END}       : {R.failed}")
    print(f"{C.BOLD}{'━' * 64}{C.END}")

    if R.failed > 0:
        print(
            f"\n{C.FAIL}{C.BOLD}"
            f"❌  {R.failed} ERROR(S) FOUND — DO NOT RUN THE APP UNTIL FIXED"
            f"{C.END}"
        )
        print(f"\n{C.FAIL}Failing checks:{C.END}")
        for e in R.errors:
            print(f"  • {e}")
        sys.exit(2)

    elif R.warned > 0:
        print(
            f"\n{C.WARN}"
            f"⚠   {R.warned} WARNING(S) — review before a show, "
            f"but app should still run"
            f"{C.END}"
        )
        sys.exit(1)

    else:
        print(f"\n{C.OK}{C.BOLD}✅  ALL CHECKS PASSED — SAFE TO RUN{C.END}")
        sys.exit(0)


if __name__ == "__main__":
    main()