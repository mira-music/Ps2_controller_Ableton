"""
================================================================================
  src/controller/watchdog.py — Controller Health + Recovery
================================================================================
  Auto-detects gamepad connection state, reprobes after silent
  disconnects, and reconciles ghost button-up events.

  Tunable values from cfg:
    cfg.WATCHDOG_INTERVAL         [LIVE]    health check rate
    cfg.IDLE_REPROBE_AFTER        [LIVE]    idle threshold before deep check
    cfg.SELECT_RECONCILE_INTERVAL [LIVE]    ghost-event reconcile rate

  All three are [LIVE] — they're read on every loop iteration, so TOML
  changes take effect on the next tick (within 1-2 seconds of reload).
================================================================================
"""

import time
import pygame

from src import state as st
from src.config import (
    # Architectural constant — pygame button index
    BTN_SELECT,
)
from src.config_loader import cfg
from src.log_setup import get_logger

log = get_logger(__name__)

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
                log.warning(f"Controller LOST ({reason})")
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
            log.info(f"Controller FOUND: {name}  ({reason})")
        return ctrl

    except Exception as e:
        st._set_controller_handle(None)
        with st._lock:
            st.state["controller_connected"] = False
            st.state["controller_name"]      = "—"
            st.state["_last_reprobe"]        = time.perf_counter()
        log.error(f"Controller re-probe error ({reason}): {e}")
        return None

# ═══════════════════════════════════════════════════════════════════════════
#  WATCHDOG LOOP (1 Hz daemon thread)
# ═══════════════════════════════════════════════════════════════════════════

def watchdog_loop():
    """
    Background thread monitoring controller health.

    Reads from cfg (hot-reloadable):
      cfg.WATCHDOG_INTERVAL   — sleep between health checks
      cfg.IDLE_REPROBE_AFTER  — silence threshold before deep check
    """
    while True:
        try:
            time.sleep(cfg.WATCHDOG_INTERVAL)
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

            if idle_for >= cfg.IDLE_REPROBE_AFTER and since_last_probe >= cfg.IDLE_REPROBE_AFTER:
                if soft_check_controller():
                    with st._lock:
                        st.state["_last_reprobe"] = now
                else:
                    log.warning(f"Soft check failed after {idle_for:.1f}s idle — full reprobe")
                    reprobe_controller(reason=f"silent disconnect ({idle_for:.1f}s idle)")

        except Exception as e:
            log.error(f"Watchdog error: {e}")
            time.sleep(1.0)

# ═══════════════════════════════════════════════════════════════════════════
#  SELECT GHOST-EVENT RECONCILIATION
# ═══════════════════════════════════════════════════════════════════════════

def reconcile_select_state(controller):
    """
    Force-release SELECT if a ghost button-up event was dropped.
    Called from the controller_loop every frame.

    Reads from cfg (hot-reloadable):
      cfg.SELECT_RECONCILE_INTERVAL — rate-limit for this check
    """
    if controller is None:
        return
    now = time.perf_counter()
    with st._lock:
        last_check = st.state["_last_select_reconcile"]
    if now - last_check < cfg.SELECT_RECONCILE_INTERVAL:
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
        log.warning("SELECT ghost release detected — force-cleared")