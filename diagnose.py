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
#  SUPPRESS PYGAME GREETING (must be set BEFORE pygame is imported anywhere)
# ═══════════════════════════════════════════════════════════════════════════

os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'

# ═══════════════════════════════════════════════════════════════════════════
#  ANSI COLORS (Windows 10+ supports these out of the box)
# ═══════════════════════════════════════════════════════════════════════════

try:
    import ctypes
    kernel32 = ctypes.windll.kernel32
    kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
except Exception:
    pass

class C:
    OK    = "\033[92m"   # green
    WARN  = "\033[93m"   # yellow
    FAIL  = "\033[91m"   # red
    INFO  = "\033[96m"   # cyan
    DIM   = "\033[90m"   # grey
    BOLD  = "\033[1m"
    END   = "\033[0m"

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
        # Per-section counters for summary lines
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
    """Print a quick OK summary if non-verbose mode produced no visible output."""
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
        R.ok(f"Python {version_str} (tomllib available)")
    elif v.major == 3 and v.minor >= 8:
        R.warn(f"Python {version_str}",
               "Below 3.11 — tomllib not available, TOML loading will fail")
    else:
        R.fail(f"Python {version_str}",
               "Need Python 3.11+ for full functionality")

    section_summary()

# ═══════════════════════════════════════════════════════════════════════════
#  CHECK 2 — REQUIRED THIRD-PARTY PACKAGES
# ═══════════════════════════════════════════════════════════════════════════

def check_dependencies():
    header("Third-Party Dependencies")

    deps = {
        "pygame":     "Gamepad input (required)",
        "pythonosc":  "OSC communication (required)",
    }

    for pkg, desc in deps.items():
        try:
            mod = importlib.import_module(pkg)
            ver = getattr(mod, "__version__", "unknown")
            R.ok(f"{pkg} {ver}")
        except ImportError:
            R.fail(f"Missing package: {pkg}",
                   f"{desc}. Install with: pip install {pkg}")

    optional = {
        "tomllib":     "TOML parser (built-in to Python 3.11+)",
        "tkinter":     "UI toolkit (standard library)",
    }
    for pkg, desc in optional.items():
        try:
            importlib.import_module(pkg)
            R.ok(f"{pkg} (built-in)")
        except ImportError:
            R.fail(f"Missing: {pkg}", desc)

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
        "src/config.py":              "Hardcoded defaults",
        "src/config_loader.py":       "TOML loader + cfg singleton",
        "src/state.py":               "Shared state",
        "src/helpers.py":             "Utility functions",
        "src/log_setup.py":           "Logging config",
        "src/main.py":                "Application entry",
        "src/osc/__init__.py":        "osc package marker",
        "src/osc/client.py":          "OSC send",
        "src/osc/server.py":          "OSC receive",
        "src/osc/discovery.py":       "Ableton session discovery",
        "src/engine/__init__.py":     "engine package marker",
        "src/engine/eq.py":           "EQ engine",
        "src/engine/fx.py":           "FX engine",
        "src/engine/navigation.py":   "Navigation",
        "src/engine/actions.py":      "Discrete actions",
        "src/engine/momentary.py":    "Momentary FX",
        "src/engine/polling.py":      "Background polling",
        "src/controller/__init__.py": "controller package marker",
        "src/controller/buttons.py":  "Button handlers",
        "src/controller/axes.py":     "Axis handlers",
        "src/controller/watchdog.py": "Controller health",
        "src/controller/loop.py":     "Main controller thread",
        "src/ui/__init__.py":         "ui package marker",
        "src/ui/palette.py":          "Colors + fonts",
        "src/ui/widgets.py":          "Canvas renderers",
        "src/ui/builder.py":          "UI construction",
        "src/ui/updater.py":          "UI update loop",
        "config/default.toml":        "Factory config template",
        "config/README.md":           "Config folder explainer",
        "config/EXAMPLES.toml":       "Preset snippets",
    }

    for path, desc in required.items():
        if Path(path).is_file():
            R.ok(f"{path}")
        else:
            R.fail(f"Missing: {path}", desc)

    optional = {
        "config/active.toml":         "Created on first run (OK if missing)",
        "config/presets/":            "User preset folder",
        "logs/":                      "Log output folder (created at runtime)",
        "docs/screenshots/":          "README screenshots",
    }

    for path, desc in optional.items():
        p = Path(path)
        if p.exists():
            R.ok(f"{path} (optional)")
        else:
            if VERBOSE:
                print(f"  {C.DIM}○ {path} not present — {desc}{C.END}")

    section_summary()

# ═══════════════════════════════════════════════════════════════════════════
#  CHECK 4 — PYTHON SYNTAX (compile-check every .py file)
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

    default = Path("config/default.toml")
    if not default.exists():
        R.fail("config/default.toml missing", "Required as fallback template")
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

    active = Path("config/active.toml")
    if active.exists():
        try:
            with open(active, "rb") as f:
                active_data = tomllib.load(f)
            R.ok("config/active.toml parses correctly")
        except tomllib.TOMLDecodeError as e:
            R.fail("config/active.toml has syntax errors",
                   f"{e}\nDelete it and restart the app to regenerate")
    else:
        if VERBOSE:
            print(f"  {C.DIM}○ config/active.toml not present (created on first run){C.END}")

    required_sections = [
        ["eq", "encoder"], ["eq", "dominance"], ["eq", "flick"],
        ["eq", "detent"], ["eq", "osc"], ["eq", "ramp"], ["eq", "safety"],
        ["trim"],
        ["meter"], ["meter", "clip"],
        ["fx"], ["fx", "delay_fb"],
        ["volume"], ["navigation"], ["timing"], ["ui"], ["network"],
    ]

    def nested_get(d, path):
        cur = d
        for k in path:
            if not isinstance(cur, dict) or k not in cur:
                return None
            cur = cur[k]
        return cur

    for path in required_sections:
        section = nested_get(default_data, path)
        section_name = ".".join(path)
        if section is None:
            R.warn(f"default.toml missing section [{section_name}]")
        elif not isinstance(section, dict):
            R.warn(f"default.toml section [{section_name}] is not a table")
        else:
            R.ok(f"default.toml has [{section_name}]")

    try:
        if "src.config_loader" in sys.modules:
            del sys.modules["src.config_loader"]
        from src.config_loader import cfg, _CFG_MAP

        unreachable = []
        for attr, path in _CFG_MAP:
            value = nested_get(default_data, path)
            if value is None:
                unreachable.append(f"{attr} ← {'.'.join(path)}")

        if unreachable:
            R.warn(f"Loader maps to {len(unreachable)} keys not in default.toml",
                   f"First few: {unreachable[:5]}")
        else:
            R.ok(f"All {len(_CFG_MAP)} loader mappings resolve to default.toml keys")

    except Exception as e:
        R.fail("Cannot validate loader mappings", str(e))

    section_summary()

# ═══════════════════════════════════════════════════════════════════════════
#  CHECK 7 — CFG SINGLETON SANITY
# ═══════════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════════════
#  CHECK 7 — CFG SINGLETON SANITY (with deep verification)
# ═══════════════════════════════════════════════════════════════════════════

def check_cfg_singleton():
    header("cfg Singleton Health")

    try:
        if "src.config_loader" in sys.modules:
            del sys.modules["src.config_loader"]
        from src.config_loader import cfg

        critical_attrs = [
            "EQ_SWEEP_SECONDS", "EQ_ENCODER_CURVE_EXP", "EQ_AXIS_DEAD_ZONE",
            "EQ_FLICK_TIMEOUT_MS", "EQ_BASS_BOOST_CAP",
            "FX_AXIS_DEAD_ZONE",
            "VOL_DEAD_ZONE",
            "UI_REFRESH_MS",
            "OSC_HOST", "OSC_SEND_PORT",
        ]

        missing_attrs = []
        for attr in critical_attrs:
            if not hasattr(cfg, attr):
                missing_attrs.append(attr)
            else:
                val = getattr(cfg, attr)
                if val is None:
                    R.warn(f"cfg.{attr} is None")
                else:
                    R.ok(f"cfg.{attr} = {val}")

        if missing_attrs:
            R.fail("cfg missing critical attributes",
                   "Missing: " + ", ".join(missing_attrs))

        # ─── Deep check: scan all src/ files for cfg.X references and verify ───
        cfg_references = set()
        for py_file in Path("src").rglob("*.py"):
            try:
                with open(py_file, "r", encoding="utf-8") as f:
                    source = f.read()
                tree = ast.parse(source, filename=str(py_file))
            except Exception:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute):
                    if isinstance(node.value, ast.Name) and node.value.id == "cfg":
                        cfg_references.add((node.attr, str(py_file)))

        broken_refs = []
        for attr, source_file in cfg_references:
            if not hasattr(cfg, attr):
                broken_refs.append((attr, source_file))

        if broken_refs:
            R.fail(f"Found {len(broken_refs)} broken cfg.X references in code",
                   "These will crash at runtime!")
            for attr, source_file in broken_refs[:10]:
                print(f"      {C.FAIL}✗{C.END} cfg.{attr} used in {source_file} — NOT IN SINGLETON")
            if len(broken_refs) > 10:
                print(f"      {C.DIM}... and {len(broken_refs) - 10} more{C.END}")
        else:
            R.ok(f"All {len(cfg_references)} cfg.X references in code resolve correctly")

    except Exception as e:
        R.fail("Cannot inspect cfg", str(e))

    section_summary()
    header("cfg Singleton Health")

    try:
        if "src.config_loader" in sys.modules:
            del sys.modules["src.config_loader"]
        from src.config_loader import cfg

        critical_attrs = [
            "EQ_SWEEP_SECONDS", "EQ_ENCODER_CURVE_EXP", "EQ_AXIS_DEAD_ZONE",
            "EQ_FLICK_TIMEOUT_MS", "EQ_BASS_BOOST_CAP",
            "FX_AXIS_DEAD_ZONE",
            "VOL_DEAD_ZONE",
            "UI_REFRESH_MS",
            "OSC_HOST", "OSC_SEND_PORT",
        ]

        missing_attrs = []
        for attr in critical_attrs:
            if not hasattr(cfg, attr):
                missing_attrs.append(attr)
            else:
                val = getattr(cfg, attr)
                if val is None:
                    R.warn(f"cfg.{attr} is None")
                else:
                    R.ok(f"cfg.{attr} = {val}")

        if missing_attrs:
            R.fail("cfg missing critical attributes",
                   "Missing: " + ", ".join(missing_attrs))

    except Exception as e:
        R.fail("Cannot inspect cfg", str(e))

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
        R.ok(f"logs/ folder is writable")
    except Exception as e:
        R.fail("Cannot write to logs/", str(e))

    existing_log = log_dir / "fxmachine.log"
    if existing_log.exists():
        size_mb = existing_log.stat().st_size / (1024 * 1024)
        R.ok(f"Existing log: {size_mb:.2f} MB")

    section_summary()

# ═══════════════════════════════════════════════════════════════════════════
#  CHECK 9 — DEAD IMPORTS HINT
# ═══════════════════════════════════════════════════════════════════════════

def check_dead_imports():
    header("Dead Code Hints (potentially unused imports)")

    # AST-based check: find each imported name, then check if it appears
    # anywhere else in the file (excluding the import statement itself).
    py_files = list(Path("src").rglob("*.py"))

    for py_file in py_files:
        try:
            with open(py_file, "r", encoding="utf-8") as f:
                source = f.read()
            tree = ast.parse(source, filename=str(py_file))
        except Exception:
            continue

        # Collect imported names (only `from X import Y` style)
        imported_names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    name = alias.asname or alias.name
                    if name != "*":
                        imported_names.add(name)

        # Get all identifiers used in the file (excluding the import nodes)
        used_names = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            for child in ast.walk(node):
                if isinstance(child, ast.Name):
                    used_names.add(child.id)
                elif isinstance(child, ast.Attribute):
                    # For x.y.z, we want to count x as used
                    cur = child
                    while isinstance(cur, ast.Attribute):
                        cur = cur.value
                    if isinstance(cur, ast.Name):
                        used_names.add(cur.id)

        # Check which imports are unused
        unused = imported_names - used_names
        if unused:
            for name in sorted(unused):
                R.warn(f"{py_file}: '{name}' is imported but never used")

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
        R.fail("Cannot read OSC config", str(e))
        section_summary()
        return

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.bind((OSC_HOST, OSC_RECEIVE_PORT))
        s.close()
        R.ok(f"Receive port {OSC_RECEIVE_PORT} available")
    except OSError as e:
        R.warn(f"Receive port {OSC_RECEIVE_PORT} in use",
               f"Is another FX Machine instance running? Error: {e}")

    if 1 <= OSC_SEND_PORT <= 65535:
        R.ok(f"Send port {OSC_SEND_PORT} is valid")
    else:
        R.fail(f"Send port {OSC_SEND_PORT} out of range")

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        s.sendto(b"/ping", (OSC_HOST, OSC_SEND_PORT))
        s.close()
        R.ok(f"Sent test UDP to {OSC_HOST}:{OSC_SEND_PORT}")
    except Exception as e:
        R.warn(f"Could not send UDP test", str(e))

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
            R.warn("No gamepad detected",
                   "Plug one in or app will run in NO CONTROLLER mode")
        else:
            for i in range(count):
                joy = pygame.joystick.Joystick(i)
                joy.init()
                name = joy.get_name()
                axes = joy.get_numaxes()
                buttons = joy.get_numbuttons()
                hats = joy.get_numhats()
                R.ok(f"Gamepad {i}: {name}")
                info(f"  {axes} axes, {buttons} buttons, {hats} hats")

                if buttons < 12:
                    R.warn(f"Only {buttons} buttons — FX Machine expects 12+")
                if axes < 4:
                    R.warn(f"Only {axes} axes — FX Machine expects 4")
                if hats < 1:
                    R.warn(f"No D-pad detected")

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
        R.warn(".git folder missing", "Project is not under version control")
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
                R.ok("Working tree clean (nothing to commit)")
            else:
                lines = output.split("\n")
                R.warn(f"{len(lines)} uncommitted change(s)",
                       "Commit before running shows in case of issues")
                for line in lines[:5]:
                    print(f"      {C.DIM}{line}{C.END}")
                if len(lines) > 5:
                    print(f"      {C.DIM}... and {len(lines) - 5} more{C.END}")
        else:
            R.warn("git status failed", result.stderr.strip())
    except FileNotFoundError:
        R.warn("git not installed or not in PATH")
    except subprocess.TimeoutExpired:
        R.warn("git status timed out")
    except Exception as e:
        R.warn("git check error", str(e))

    section_summary()

# ═══════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main():
    start = time.time()

    print(f"\n{C.BOLD}{C.INFO}╔{'═' * 62}╗{C.END}")
    print(f"{C.BOLD}{C.INFO}║          FX MACHINE — DIAGNOSTIC TOOL{' ' * 22}║{C.END}")
    print(f"{C.BOLD}{C.INFO}╚{'═' * 62}╝{C.END}")

    if QUICK:
        info("Quick mode — skipping OSC, gamepad, and git checks")
    if VERBOSE:
        info("Verbose mode — showing all checks")

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
    print(f"  Total checks:  {R.checks}")
    print(f"  {C.OK}Passed:{C.END}        {R.passed}")
    print(f"  {C.WARN}Warnings:{C.END}      {R.warned}")
    print(f"  {C.FAIL}Failed:{C.END}        {R.failed}")
    print(f"{C.BOLD}{'━' * 64}{C.END}")

    if R.failed > 0:
        print(f"\n{C.FAIL}{C.BOLD}❌ {R.failed} ERROR(S) — DO NOT RUN THE APP UNTIL FIXED{C.END}")
        print(f"\n{C.FAIL}Errors:{C.END}")
        for e in R.errors:
            print(f"  • {e}")
        sys.exit(2)
    elif R.warned > 0:
        print(f"\n{C.WARN}⚠  {R.warned} WARNING(S) — review but app should still run{C.END}")
        sys.exit(1)
    else:
        print(f"\n{C.OK}{C.BOLD}✅ ALL CHECKS PASSED — SAFE TO RUN{C.END}")
        sys.exit(0)


if __name__ == "__main__":
    main()