"""
================================================================================
  src/controller/watchdog.py — Controller Health + Recovery
================================================================================
  Auto-detects gamepad connection state, reprobes after silent
  disconnects, and reconciles ghost button-up events (a common
  pygame issue where SELECT release events get dropped).

  Functions:
    soft_check_controller()       — non-disruptive health check
    reprobe_controller(reason)    — full re-init via pygame.joystick
    watchdog_loop()               — daemon thread (1 Hz) monitoring health
    reconcile_select_state(ctrl)  — force-release SELECT if ghost detected
================================================================================
"""

import time
import pygame

from src import state as st
from src.config import (
    WATCHDOG_INTERVAL, IDLE_REPROBE_AFTER,
    SELECT_RECONCILE_INTERVAL,
    BTN_SELECT,
)

# ═══════════════════════════════════════════════════════════════════════════
#  SOFT HEALTH CHECK
# ═══════════════════════════════════════════════════════════════════════════

def soft_check_controller():
    """Non-disruptive check — returns True if controller is still alive."""
    ctrl = st._get_controller_handle()
    if ctrl is None:
        return False
    try:
        if pygame.joystick.get_count() < 1:
            return False
        if not ctrl.get_init():
            return False
        _ = ctrl.get_numaxes()
        return True
    except Exception:
        return False

# ═══════════════════════════════════════════════════════════════════════════
#  REPROBE (full pygame re-init)
# ═══════════════════════════════════════════════════════════════════════════

def reprobe_controller(reason="watchdog"):
    """Full re-init of pygame.joystick subsystem. Returns the new handle or None."""
    try:
        pygame.joystick.quit()
        pygame.joystick.init()

        n = pygame.joystick.get_count()
        if n == 0:
            st._set_controller_handle(None)
            with st._lock:
                was_connected = st.state["controller_connected"]
                st.state["controller_connected"] = False
                st.state["controller_name"]      = "—"
                st.state["_last_reprobe"]        = time.perf_counter()
            if was_connected:
                print(f"  ⚠  Controller LOST ({reason})")
            return None

        ctrl = pygame.joystick.Joystick(0)
        ctrl.init()
        name = ctrl.get_name()
        st._set_controller_handle(ctrl)
        with st._lock:
            was_connected = st.state["controller_connected"]
            st.state["controller_connected"] = True
            st.state["controller_name"]      = name
            st.state["_last_input_at"]       = time.perf_counter()
            st.state["_last_reprobe"]        = time.perf_counter()

        if not was_connected:
            print(f"  ✅ Controller FOUND: {name}  ({reason})")
        return ctrl

    except Exception as e:
        st._set_controller_handle(None)
        with st._lock:
            st.state["controller_connected"] = False
            st.state["controller_name"]      = "—"
            st.state["_last_reprobe"]        = time.perf_counter()
        print(f"  ⚠  Controller re-probe error ({reason}): {e}")
        return None

# ═══════════════════════════════════════════════════════════════════════════
#  WATCHDOG LOOP (1 Hz daemon thread)
# ═══════════════════════════════════════════════════════════════════════════

def watchdog_loop():
    while True:
        try:
            time.sleep(WATCHDOG_INTERVAL)
            now = time.perf_counter()

            with st._lock:
                connected      = st.state["controller_connected"]
                last_input_at  = st.state["_last_input_at"]
                last_reprobe   = st.state["_last_reprobe"]

            if not connected:
                reprobe_controller(reason="auto-retry")
                continue

            if last_input_at == 0.0:
                continue

            idle_for         = now - last_input_at
            since_last_probe = now - last_reprobe

            if idle_for >= IDLE_REPROBE_AFTER and since_last_probe >= IDLE_REPROBE_AFTER:
                if soft_check_controller():
                    with st._lock:
                        st.state["_last_reprobe"] = now
                else:
                    print(f"  ⚠  Soft check failed after {idle_for:.1f}s idle — full reprobe")
                    reprobe_controller(reason=f"silent disconnect ({idle_for:.1f}s idle)")

        except Exception as e:
            print(f"  ⚠  Watchdog error: {e}")
            time.sleep(1.0)

# ═══════════════════════════════════════════════════════════════════════════
#  SELECT GHOST-EVENT RECONCILIATION
# ═══════════════════════════════════════════════════════════════════════════

def reconcile_select_state(controller):
    """Force-release SELECT if a ghost button-up event was dropped."""
    if controller is None:
        return
    now = time.perf_counter()
    with st._lock:
        last_check = st.state["_last_select_reconcile"]
    if now - last_check < SELECT_RECONCILE_INTERVAL:
        return
    with st._lock:
        st.state["_last_select_reconcile"] = now

    try:
        physical_select = bool(controller.get_button(BTN_SELECT))
    except Exception:
        return

    with st._lock:
        software_select = st.state["select_held"]

    if software_select and not physical_select:
        with st._lock:
            st.state["select_held"] = False
            st.state["last_action"] = "SELECT auto-released (ghost detected)"
        print("  ⚠  SELECT ghost release detected — force-cleared")