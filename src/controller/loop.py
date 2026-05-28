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

        except Exception as e:
            log.error(f"Controller loop error: {e}")
            st._set_controller_handle(None)
            with st._lock:
                st.state["controller_connected"] = False
                st.state["controller_name"]      = "—"
            time.sleep(0.3)