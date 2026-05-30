"""
================================================================================
  src/controller/loop.py — Main Controller Thread
================================================================================
  Daemon thread (~125 Hz) that:
    1. Reads pygame events (buttons, axes, device removed)
    2. Dispatches button events to handlers
    3. Reconciles ghost SELECT events
    4. Routes right stick by modifier priority (L1 > SELECT > EQ > idle)
    5. Left stick always drives navigation
    6. D-pad routed by current layer
    7. Sleeps 8ms → ~125 Hz polling rate

  Error handling distinguishes:
    - pygame.error "not initialized" → app is shutting down, exit cleanly
    - All other errors → log and recover (reset controller state, sleep, retry)

  Build B integrations:
    - Diagnostics heartbeat (record_thread_tick) each iteration. No-op
      when diagnostics is disabled.
    - Shutdown flag check at the TOP of each iteration. This prevents
      the "_enter_buffered_busy" stdout lock error during interpreter
      finalization. The controller thread sleeps in pygame.time.wait(8)
      and would otherwise wake up during shutdown, try to log "exiting
      cleanly", and find stdout in a half-torn-down state. Checking
      _shutting_down at the top of the loop ensures we exit BEFORE
      doing any work that could log to a destroyed stdout.
================================================================================
"""

import time
import pygame

from src import state as st
from src.helpers import mark_controller_input, clear_flashes_if_expired
from src.controller.watchdog import reprobe_controller, reconcile_select_state
from src.controller.buttons import handle_button_down, handle_button_up
from src.controller.axes import (
    handle_axes_navigation, handle_axes_fx, handle_axes_eq,
    handle_right_joystick_volume, handle_dpad,
)
from src.log_setup import get_logger

log = get_logger(__name__)

# ═══════════════════════════════════════════════════════════════════════════
#  MODULE-LEVEL TIMING
# ═══════════════════════════════════════════════════════════════════════════

_axis_last_tick = 0.0

# ═══════════════════════════════════════════════════════════════════════════
#  MAIN CONTROLLER LOOP
# ═══════════════════════════════════════════════════════════════════════════

def controller_loop():
    global _axis_last_tick
    try:
        pygame.init()
    except Exception as e:
        log.error(f"pygame init error: {e}")

    reprobe_controller(reason="startup")
    _axis_last_tick = time.perf_counter()

    while True:
        # ── Shutdown check at the TOP of each iteration ─────────────────
        # This must be the FIRST thing in the loop body. The controller
        # thread sleeps in pygame.time.wait(8) at the end of each iteration
        # and wakes up to run again. If the main thread is shutting down,
        # we need to exit BEFORE doing any work — otherwise we risk:
        #   - Logging to a stdout that's mid-finalization (_enter_buffered_busy)
        #   - Reading state that's been torn down
        #   - Calling pygame APIs on an uninitialized subsystem
        # Returning here lets the thread die quietly so the process can finalize.
        with st._lock:
            if st.state["_shutting_down"]:
                return

        # ── Diagnostics heartbeat ───────────────────────────────────────
        # Reports one tick per loop iteration to the thread health monitor.
        # Lets the analyzer verify this thread is running at its target
        # ~125 Hz. Wrapped in try/except so a diagnostics failure never
        # breaks the controller loop. No-op when diagnostics is disabled.
        try:
            from src.diagnostics import record_thread_tick
            record_thread_tick("controller")
        except Exception:
            pass

        ctrl = st._get_controller_handle()

        if ctrl is None:
            time.sleep(0.2)
            _axis_last_tick = time.perf_counter()
            continue

        try:
            for event in pygame.event.get():
                if event.type in (pygame.JOYBUTTONDOWN,
                                  pygame.JOYBUTTONUP,
                                  pygame.JOYHATMOTION,
                                  pygame.JOYAXISMOTION,
                                  pygame.JOYBALLMOTION):
                    mark_controller_input()

                if event.type == pygame.JOYBUTTONDOWN:
                    handle_button_down(event.button)
                elif event.type == pygame.JOYBUTTONUP:
                    handle_button_up(event.button)
                elif event.type == pygame.JOYDEVICEREMOVED:
                    st._set_controller_handle(None)
                    with st._lock:
                        st.state["controller_connected"] = False
                        st.state["controller_name"]      = "—"

            ctrl = st._get_controller_handle()
            if ctrl is None:
                continue

            reconcile_select_state(ctrl)

            now = time.perf_counter()
            dt = now - _axis_last_tick
            _axis_last_tick = now
            if dt > 0.5:
                dt = 0.0

            with st._lock:
                l1 = st.state["l1_held"]
                select_held = st.state["select_held"]
                eq_mode = st.state["eq_mode_active"]

            # Right-stick priority:
            # 1. L1 → FX layer
            # 2. SELECT → volume control
            # 3. EQ mode → EQ control
            # 4. Default → nothing

            if l1:
                handle_axes_fx(ctrl, dt)
            else:
                handle_axes_navigation(ctrl)

                if select_held:
                    handle_right_joystick_volume(ctrl)
                elif eq_mode:
                    handle_axes_eq(ctrl, dt)

            handle_dpad(ctrl)
            clear_flashes_if_expired()
            pygame.time.wait(8)

        except pygame.error as e:
            # pygame.error usually means the joystick was momentarily quit
            # by a reprobe in another thread. Don't exit — recover by clearing
            # the handle so the next loop iteration triggers a reprobe via the
            # watchdog. Only exit if we detect a true shutdown.
            err_msg = str(e)
            # Use the explicit shutdown flag rather than _osc_server is None.
            # _osc_server is None is ambiguous: it's also None when the OSC
            # server fails to start, which would cause premature loop exit.
            with st._lock:
                shutting_down = st.state["_shutting_down"]
            if shutting_down:
                # Don't log here — stdout may already be torn down.
                # Just return silently to let the thread die cleanly.
                return
            log.warning(f"Controller transient error (will recover): {err_msg}")
            st._set_controller_handle(None)
            with st._lock:
                st.state["controller_connected"] = False
                st.state["controller_name"]      = "—"
            time.sleep(0.5)