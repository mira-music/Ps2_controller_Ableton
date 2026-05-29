"""
================================================================================
  src/main.py — Application Entry Point
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


def main():
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

    log.info(f"  FX track: '{FX_TRACK_NAME}'  EQ track: '{EQ_TRACK_NAME}'")
    log.info(f"  v{VERSION}: all systems starting")
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

        # Set explicit shutdown flag before stopping OSC server.
        # The controller loop checks this flag to distinguish clean shutdown
        # from transient pygame errors during normal operation.
        with st._lock:
            st.state["_shutting_down"] = True

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