"""
================================================================================
  src/main.py — Application Entry Point
================================================================================
  Spawns 5 daemon threads:
    OSC server, polling, controller loop, watchdog, EQ ramp loop

  Then creates the Tkinter root window, builds the UI, and starts the
  main loop. On window close, runs a strict shutdown sequence:

    1. Idempotency guard prevents on_close from running twice
    2. Set _shutting_down flag so threads can exit their loops cleanly
    3. Stop diagnostics layer FIRST so background threads die before
       resources they depend on are torn down
    4. Stop OSC listeners (tells Ableton to stop sending updates)
    5. Shut down the OSC server
    6. Destroy the Tkinter window ONLY if it still exists
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

    log.info(f"  FX track: '{FX_TRACK_NAME}'  EQ track: '{EQ_TRACK_NAME}'")
    log.info(f"  v{VERSION}: all systems starting")
    log.info("=" * 64)

    root = tk.Tk()
    root.geometry("760x900")
    lbl = build_ui(root)
    root.after(UI_REFRESH_MS, update_ui, root, lbl)

    # ═══════════════════════════════════════════════════════════════════
    #  WINDOW CLOSE HANDLER
    #
    #  Strict shutdown sequence with multiple layers of safety:
    #    1. Idempotency guard via mutable list (closure-safe)
    #    2. Shutdown flag is set first so threads see it
    #    3. Diagnostics stopped BEFORE OSC tear-down so its background
    #       threads aren't reading torn-down state during finalization
    #    4. root.destroy() is guarded by winfo_exists() check AND
    #       wrapped in try/except in case Tkinter is already gone
    # ═══════════════════════════════════════════════════════════════════

    # Mutable flag for idempotency guard. We use a list (not a bool)
    # because closures can mutate but not reassign outer-scope variables
    # without 'nonlocal'. List mutation works without that keyword and
    # is bulletproof across re-entry from any source.
    _close_state = [False]

    def on_close():
        # ── Idempotency guard ──
        # Tkinter can fire WM_DELETE_WINDOW multiple times in fast
        # succession (e.g. user clicks X twice, or OS sends a close
        # event during a window manager interaction). Without this guard,
        # the second call would try to destroy an already-destroyed root.
        if _close_state[0]:
            return
        _close_state[0] = True

        log.info("")
        log.info("╔" + "═" * 62 + "╗")
        log.info("║" + " " * 23 + "SESSION END" + " " * 28 + "║")
        log.info("╚" + "═" * 62 + "╝")
        log.info("Shutting down…")

        # ── Step 1: Tell other threads we're shutting down ──
        # Sets the explicit _shutting_down flag in shared state. The
        # controller loop checks this flag when handling pygame errors
        # to distinguish a normal shutdown from a transient pygame issue.
        # Must happen FIRST so threads can begin orderly exit.
        with st._lock:
            st.state["_shutting_down"] = True

        # ── Step 2: Stop diagnostics layer FIRST ──
        # Critical ordering: the diagnostics layer runs background threads
        # (sampler, reporter) that read state and write to log files.
        # If we let them keep running while we destroy Tkinter and shut
        # down the OSC server, they'll crash on torn-down state. Worse,
        # Python's interpreter finalizer can deadlock on stdout locks
        # when daemon threads are still doing I/O at exit time
        # (the "_enter_buffered_busy" error). Stopping diagnostics here
        # ensures all its threads have joined before later steps run.
        try:
            from src.diagnostics import shutdown_diagnostics, is_enabled
            if is_enabled():
                log.info("Stopping diagnostics layer…")
                shutdown_diagnostics()
        except Exception as e:
            log.warning(f"Diagnostics shutdown error: {e}")

        # ── Step 3: Stop OSC listeners ──
        # Tells Ableton to stop pushing parameter updates to us. After
        # this, no more "/live/device/get/parameter/value" callbacks
        # will fire on our server thread. Wrapped in try/except so a
        # failure for one listener doesn't prevent the others from
        # being unregistered.
        #........................................................
        try:
            from src.osc.client import osc_stop_session_listeners
            osc_stop_session_listeners()
            osc_stop_fx_listeners()
            osc_stop_eq_listeners()
            osc_stop_eq_meter_listener()
        except Exception as e:
            log.warning(f"Listener stop error: {e}")

        # ── Step 4: Shut down the OSC server ──
        # ThreadingOSCUDPServer.shutdown() blocks until the server thread
        # exits its serve_forever loop. After this returns, no more
        # incoming OSC packets are processed and the server socket is
        # closed. Setting _osc_server = None signals "fully torn down".
        if st._osc_server is not None:
            try:
                st._osc_server.shutdown()
            except Exception as e:
                log.warning(f"OSC server shutdown error: {e}")
            st._osc_server = None

        # ── Step 5: Destroy the Tkinter window ──
        # winfo_exists() returns 1 if the widget still exists, 0 if
        # destroyed. The check itself raises TclError if Tk is fully
        # torn down — we catch that as "already gone, nothing to do".
        # This is the final fallback if Tkinter has already cleaned
        # up its own state during the OSC shutdown blocking call.
        try:
            if root.winfo_exists():
                root.destroy()
        except Exception:
            # Already destroyed by Tkinter's own cleanup path during
            # the OSC server shutdown. Benign — we're exiting anyway.
            pass

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()

    log.info("👋 Stopped.")
    pygame.quit()
    sys.exit(0)