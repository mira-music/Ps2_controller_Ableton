#!/usr/bin/env python3
"""
================================================================================
  THE FX MACHINE — Entry Point
================================================================================
  Run with: python run.py

  Future: this is also the entry point for PyInstaller / Nuitka to build
  a standalone .exe.

  Build B addition:
    The optional diagnostics layer is installed BEFORE main() runs.
    When cfg.DIAG_ENABLED is False in TOML (the default), this is a
    no-op — the diagnostics module isn't even imported beyond the
    initial install_if_enabled() check.
    When DIAG_ENABLED is True, the diagnostics layer wraps key functions,
    starts background monitoring threads, and writes detailed logs to
    logs/diagnostics.log and logs/diagnostics.jsonl.

    Failures during diagnostics install are caught and logged — they
    NEVER block the main app from starting.
================================================================================
"""

from src.main import main

if __name__ == "__main__":
    # ─── Optional diagnostics layer — fully opt-in via TOML config ───
    # When diagnostics.enabled = false in active.toml (the default),
    # this is a zero-cost no-op. When true, monkey-patches key functions
    # for profiling and starts background monitoring threads.
    #
    # Any failure here is swallowed so a broken diagnostics layer can
    # never prevent the real app from launching.
    try:
        # Import config_loader first so the diagnostics installer can
        # read cfg.DIAG_ENABLED.
        from src.config_loader import init_config
        init_config()

        from src.diagnostics import install_if_enabled
        install_if_enabled()
    except Exception as e:
        # Diagnostics failure must NEVER block the app
        print(f"[run.py] diagnostics setup failed (continuing without): {e}")

    main()