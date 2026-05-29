"""
================================================================================
  src/controller/buttons.py — Button Press/Release Handlers
================================================================================
"""

from src import state as st
from src.config import (
    BTN_CROSS, BTN_CIRCLE, BTN_TRIANGLE, BTN_SQUARE,
    BTN_L1, BTN_R1, BTN_L2, BTN_R2, BTN_L3, BTN_R3,
    BTN_SELECT, BTN_START,
)
from src.engine.actions import (
    action_launch_clip, action_stop_clip, action_stop_track,
    action_launch_scene, action_arm_track,
    action_transport_toggle, action_volume_mute_toggle,
    action_force_refresh, action_save_baseline,
    action_toggle_filter_lock, action_toggle_wet_lock,
    fx_recover_on_l1_release,
)
from src.engine.momentary import (
    momentary_stutter_on, momentary_stutter_off,
    momentary_bass_cut_on, momentary_bass_cut_off,
    momentary_fx_throw_on, momentary_fx_throw_off,
    force_off_all_momentaries,
)
from src.engine.eq import action_toggle_eq_mode
from src.helpers import reset_accel_state
from src.osc.client import osc_select_track


def handle_button_down(button):
    with st._lock:
        l1_held     = st.state["l1_held"]
        select_held = st.state["select_held"]
        fx_track    = st.state["fx_track_index"]

    if l1_held:
        if button == BTN_CROSS:
            momentary_stutter_on()
            return
        if button == BTN_CIRCLE:
            momentary_bass_cut_on()
            return
        if button == BTN_TRIANGLE:
            action_launch_scene()
            return
        if button == BTN_SQUARE:
            momentary_fx_throw_on()
            return
        if button == BTN_L3:
            action_toggle_filter_lock()
            return
        if button == BTN_R3:
            action_toggle_wet_lock()
            return

    if select_held and button == BTN_R1:
        action_save_baseline()
        return

    if select_held and button == BTN_R3:
        action_volume_mute_toggle()
        return

    if not l1_held and not select_held and button == BTN_R3:
        action_toggle_eq_mode()
        return

    if   button == BTN_CROSS:    action_launch_clip()
    elif button == BTN_CIRCLE:   action_stop_clip()
    elif button == BTN_TRIANGLE: action_launch_scene()
    elif button == BTN_SQUARE:   action_arm_track()
    elif button == BTN_L2:       action_stop_track()
    elif button == BTN_L1:
        with st._lock:
            # Guard: ignore re-press if already held (hardware bounce protection).
            # Without this, _pre_l1_track gets overwritten with the current track
            # instead of the pre-FX-mode track on controller bounce.
            if st.state["l1_held"]:
                return
            st.state["l1_held"]       = True
            st.state["_pre_l1_track"] = st.state["track"]
            st.state["last_action"]   = "⚡ FX mode ON  →  view: ~ FX Macros"
        if fx_track >= 0:
            osc_select_track(fx_track)
    elif button == BTN_R2:
        with st._lock:
            st.state["r2_held"]     = True
            st.state["last_action"] = "🔒 Safety ON"
    elif button == BTN_SELECT:
        with st._lock:
            st.state["select_held"] = True
            st.state["last_action"] = "SELECT held"
    elif button == BTN_START:
        if select_held:
            action_force_refresh()
        else:
            action_transport_toggle()


def handle_button_up(button):
    if button == BTN_CROSS:
        momentary_stutter_off()
        return
    if button == BTN_CIRCLE:
        momentary_bass_cut_off()
        return
    if button == BTN_SQUARE:
        momentary_fx_throw_off()
        return

    if button == BTN_R2:
        with st._lock:
            st.state["r2_held"]     = False
            st.state["last_action"] = "🔒 Safety OFF"
    elif button == BTN_SELECT:
        with st._lock:
            st.state["select_held"] = False
            st.state["last_action"] = "SELECT off"
    elif button == BTN_L1:
        with st._lock:
            st.state["l1_held"]     = False
            return_to = st.state["_pre_l1_track"]
            st.state["_pre_l1_track"] = -1
            st.state["last_action"] = "⚡ FX mode OFF — recovering…"

        force_off_all_momentaries()
        reset_accel_state()
        fx_recover_on_l1_release()

        if return_to >= 0:
            osc_select_track(return_to)