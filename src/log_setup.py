"""
================================================================================
  src/log_setup.py — Centralized Logging Configuration
================================================================================
  Initializes the logging system for the entire FX Machine.

  Behavior:
    - Detects whether running as .py script or bundled .exe
    - Places log files in: [base_dir]/logs/fxmachine.log
    - Rotates at 5 MB, keeps 10 backups
    - Writes to both file AND console
    - Per-module loggers via get_logger(__name__)

  Usage in other modules:
      from src.log_setup import get_logger
      log = get_logger(__name__)
      log.info("Something happened")
      log.warning("Heads up")
      log.error("Something broke")
      log.debug("Verbose detail")
================================================================================
"""

import sys
import os
import logging
import logging.handlers
from pathlib import Path

# ═══════════════════════════════════════════════════════════════════════════
#  CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════

LOG_FILENAME       = "fxmachine.log"
LOG_FOLDER_NAME    = "logs"
LOG_MAX_BYTES      = 5 * 1024 * 1024   # 5 MB per file
LOG_BACKUP_COUNT   = 10                # keep 10 rotated files
LOG_FORMAT         = "%(asctime)s.%(msecs)03d [%(levelname)-5s] %(name)-32s: %(message)s"
LOG_DATE_FORMAT    = "%H:%M:%S"

DEFAULT_LEVEL      = logging.INFO

# ═══════════════════════════════════════════════════════════════════════════
#  PATH DETECTION
# ═══════════════════════════════════════════════════════════════════════════

def _get_base_dir() -> Path:
    """
    Detect base directory for logs.

    Running as .exe (PyInstaller bundle):
        Returns the folder containing the .exe
    Running as .py script:
        Returns the project root (parent of src/)
    """
    if getattr(sys, 'frozen', False):
        # Running as bundled .exe
        # sys.executable is the path to FX_Machine.exe
        return Path(sys.executable).parent
    else:
        # Running as .py script
        # This file lives in src/log_setup.py, so go up two levels:
        # src/log_setup.py -> src/ -> project_root/
        return Path(__file__).resolve().parent.parent

def _get_log_path() -> Path:
    """Returns the full path to the main log file."""
    base = _get_base_dir()
    log_dir = base / LOG_FOLDER_NAME
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / LOG_FILENAME

# ═══════════════════════════════════════════════════════════════════════════
#  INITIALIZATION (called once from main.py)
# ═══════════════════════════════════════════════════════════════════════════

_initialized = False

def init_logging(level=DEFAULT_LEVEL, console=True):
    """
    Set up logging handlers. Call ONCE at app startup, before any
    other module imports get_logger().

    Args:
        level: logging level (DEBUG, INFO, WARNING, ERROR)
        console: also write to stdout (True) or file only (False)
    """
    global _initialized
    if _initialized:
        return

    log_path = _get_log_path()

    # Root logger (everything goes through here)
    root = logging.getLogger("fxmachine")
    root.setLevel(level)
    root.handlers.clear()  # in case re-init

    formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)

    # ─── File handler with rotation ───
    file_handler = logging.handlers.RotatingFileHandler(
        log_path,
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    # ─── Console handler ───
    if console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        root.addHandler(console_handler)

    # Prevent propagation to Python's default root logger
    # (otherwise messages would print twice)
    root.propagate = False

    _initialized = True

    # Log startup confirmation
    root.info("=" * 70)
    root.info("Logging initialized")
    root.info(f"  Log file:    {log_path}")
    root.info(f"  Max size:    {LOG_MAX_BYTES // (1024*1024)} MB / file")
    root.info(f"  Backups:     {LOG_BACKUP_COUNT}")
    root.info(f"  Level:       {logging.getLevelName(level)}")
    root.info(f"  Console:     {console}")
    root.info(f"  Running as:  {'EXE' if getattr(sys, 'frozen', False) else 'Script'}")
    root.info("=" * 70)

# ═══════════════════════════════════════════════════════════════════════════
#  MODULE LOGGER FACTORY
# ═══════════════════════════════════════════════════════════════════════════

def get_logger(module_name: str) -> logging.Logger:
    """
    Get a logger for a specific module.

    Usage:
        from src.log_setup import get_logger
        log = get_logger(__name__)

    The __name__ will be like "src.controller.buttons", which becomes
    "fxmachine.controller.buttons" in log output for clean readability.
    """
    # Strip the "src." prefix and replace with "fxmachine."
    if module_name.startswith("src."):
        clean_name = "fxmachine." + module_name[4:]
    elif module_name == "src":
        clean_name = "fxmachine"
    else:
        clean_name = "fxmachine." + module_name

    return logging.getLogger(clean_name)