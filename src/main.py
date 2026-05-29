"""
================================================================================
  src/main.py — Application Entry Point
================================================================================
  Spawns 5 daemon threads:
    OSC server, polling, controller loop, watchdog, EQ ramp loop

  Then creates the Tkinter root window, builds the UI, and starts the
  main loop. On window close, cleanly stops OSC listeners and shuts
  down the server.

  Logging is initialized FIRST, before any other module can log.
  An uncaught-exception handler is installed so crashes get logged
  before the process dies.
================================================================================
"""

import sys
import time
import threading
import tkinter as tk

import pygame

from src import state as st
from src.config import (
    VERSION, UI_REFRESH_MS,
    FX_TRACK_NAME, EQ_TRACK_NAME,
)
from src.osc.client import (
    setup_osc, osc_update_view,
    osc_stop_fx_listeners, osc_stop_eq_listeners,
    osc_stop_eq_meter_listener,
)
from src.osc.server import start_osc_server
from src.osc.discovery import fetch_all_names
from src.engine.polling import polling_loop, eq_ramp_loop
from src.controller.loop import controller_loop
from src.controller.watchdog import watchdog_loop
from src.ui.builder import build_ui
from src.ui.updater import update_ui

# ═══════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main():
    # ─── INITIALIZE LOGGING FIRST (before anything else can log) ───
    from src.log_setup import init_logging, get_logger, install_crash_handler
    init_logging()
    install_crash_handler()
    log = get_logger(__name__)

    log.info("")
    log.info("╔" + "═" * 62 + "╗")
    log.info("║" + " " * 22 + "SESSION START" + " " * 27 + "║")
    log.info("╚" + "═" * 62 + "╝")
    log.info(f"  FX MACHINE v{VERSION}  —  MIRA___OFC / Modulated_OFC")
    log.info(f"  © Ayoub Agoujdad. Trademark registered. Non-commercial only.")
    log.info("=" * 64)

    # ─── LOAD TOML CONFIG (after logging, before anything else) ───
    from src.config_loader import init_config
    init_config()

    setup_osc()

    threading.Thread(target=start_osc_server, daemon=True).start()
    threading.Thread(target=polling_loop,     daemon=True).start()
    threading.Thread(target=controller_loop,  daemon=True).start()
    threading.Thread(target=watchdog_loop,    daemon=True).start()
    threading.Thread(target=eq_ramp_loop,     daemon=True).start()

    time.sleep(0.5)
    threading.Thread(target=fetch_all_names,  daemon=True).start()
    osc_update_view()

    log.info("  Controls:")
    log.info("    NAV LAYER (default):")
    log.info("      L-stick: Scene/Track   D-pad U/D: Bookmarks  L/R: Groups")
    log.info("      X=Launch  O=Stop  △=Scene  □=Arm  L2=Stop track")
    log.info("      R3 = Toggle EQ mode    START=Play/Stop")
    log.info("      SELECT+R3=Volume mute  SELECT+START=Refresh")
    log.info("      SELECT+R1=Save baseline  SELECT+R-stick=Volume")
    log.info("    FX LAYER (hold L1):")
    log.info("      L-stick: Filter Freq/Res     R-stick: FX Send/Reverb Size")
    log.info("      D-pad U/D: Bookmarks         D-pad L/R: Delay FB step")
    log.info("      L3: filter lock  R3: wet lock")
    log.info("      L1+X: STUTTER  L1+O: BASS CUT  L1+△: LAUNCH SCENE  L1+□: FX THROW")
    log.info("    EQ MODE (R3 to toggle on/off):")
    log.info("      R-stick X (ENCODER): push RIGHT to boost, LEFT to cut, release = HOLD")
    log.info("      R-stick Y double-flick UP: switch band UP   (MID→HIGH→LOW→MID, no borders)")
    log.info("      R-stick Y double-flick DOWN: switch band DOWN (MID→LOW→HIGH→MID, no borders)")
    log.info("      R-stick X double-flick LEFT: kill (if ≤0dB) / normalize to 0 (if >0dB)")
    log.info("      R-stick X double-flick RIGHT: restore (if <0dB) / +15% headroom (mid/high) / blocked (bass)")
    log.info(f"  FX track: '{FX_TRACK_NAME}'  EQ track: '{EQ_TRACK_NAME}'")
    log.info(f"  v{VERSION}: dual-axis double-flick gestures + DJM channel meter")
    log.info("=" * 64)

    root = tk.Tk()
    root.geometry("760x900")
    lbl = build_ui(root)
    root.after(UI_REFRESH_MS, update_ui, root, lbl)

    def on_close():
        log.info("")
        log.info("╔" + "═" * 62 + "╗")
        log.info("║" + " " * 23 + "SESSION END" + " " * 28 + "║")
        log.info("╚" + "═" * 62 + "╝")
        log.info("Shutting down…")
        try:
            osc_stop_fx_listeners()
            osc_stop_eq_listeners()
            osc_stop_eq_meter_listener()
        except Exception as e:
            log.warning(f"Listener stop error: {e}")
        if st._osc_server is not None:
            st._osc_server.shutdown()
            st._osc_server = None
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()

    log.info("👋 Stopped.")
    pygame.quit()
    sys.exit(0)