"""
================================================================================
  src/engine/eq.py — EQ Mode Engine
================================================================================
  Full EQ control system for v9.11:
    - Mode toggle (R3 in nav layer)
    - Band selection with wrap-around
    - Smart kill/normalize (double-flick X LEFT)
    - Smart restore/boost (double-flick X RIGHT)
    - Band navigation via double-flick Y (no borders)
    - Continuous encoder on X with sticky 0 dB detent
================================================================================
"""

import time

from src import state as st
from src.config import (
    EQ_NEUTRAL_MACRO, EQ_MACRO_MIN, EQ_MACRO_MAX, EQ_CUT_HALF_MACRO,
    EQ_BOOST_PCT, EQ_BASS_BOOST_CAP,
    EQ_SLOT_LOW, EQ_SLOT_MID, EQ_SLOT_HIGH,
    EQ_MACRO_NAMES_EXPECTED,
    EQ_AXIS_DEAD_ZONE, EQ_WRITE_THROTTLE,
    EQ_DETENT_RANGE, EQ_DETENT_MIN_FACTOR,
    EQ_FLICK_EXTREME, EQ_FLICK_RETURN, EQ_FLICK_TIMEOUT_MS,
)
from src.helpers import clamp, eq_encoder_delta
from src.osc.client import osc_set_eq_macro
from src.engine.polling import start_eq_ramp
from src.log_setup import get_logger

log = get_logger(__name__)

# ═══════════════════════════════════════════════════════════════════════════
#  MODE TOGGLE
# ═══════════════════════════════════════════════════════════════════════════

def action_toggle_eq_mode():
    """R3 in nav layer: toggle EQ mode on/off. Resets all gesture state."""
    with st._lock:
        if not st.state["eq_ready"]:
            st.state["last_action"] = "⚠ EQ not ready (track ~ EQ Macros not found)"
            return

        st.state["eq_mode_active"] = not st.state["eq_mode_active"]
        if st.state["eq_mode_active"]:
            st.state["_eq_flick_x_state"] = "idle"
            st.state["_eq_flick_x_dir"]   = 0
            st.state["_eq_flick_y_state"] = "idle"
            st.state["_eq_flick_y_dir"]   = 0
            st.state["eq_armed_band"]     = -1
            st.state["_eq_encoder_last_tick"] = time.perf_counter()
            band_name = EQ_MACRO_NAMES_EXPECTED[st.state["eq_selected_band"]]
            st.state["last_action"] = f"◇ EQ MODE ON — {band_name}  [X=value, Y=switch band]"
        else:
            st.state["last_action"] = "◇ EQ MODE OFF"

# ═══════════════════════════════════════════════════════════════════════════
#  BAND SWITCH
# ═══════════════════════════════════════════════════════════════════════════

def eq_switch_band(direction):
    """direction: +1 = next (toward HIGH), -1 = prev (toward LOW). Wraps."""
    with st._lock:
        cur = st.state["eq_selected_band"]
        new = (cur + direction) % 3
        st.state["eq_selected_band"] = new
        st.state["eq_armed_band"]    = -1
        st.state["_eq_encoder_last_tick"] = time.perf_counter()
        band_name = EQ_MACRO_NAMES_EXPECTED[new]
        st.state["last_action"] = f"◇ → {band_name}"
    log.info(f"EQ band switched to {band_name}")

def eq_arm_band(direction):
    """Visual armed state during first flick (kept for compat — unused in v9.11 nav)."""
    with st._lock:
        cur = st.state["eq_selected_band"]
        armed = (cur + direction) % 3
        st.state["eq_armed_band"]  = armed
        st.state["eq_armed_until"] = time.perf_counter() + (EQ_FLICK_TIMEOUT_MS / 1000.0)
        band_name = EQ_MACRO_NAMES_EXPECTED[armed]
        st.state["last_action"] = f"◇ → {band_name} armed (flick again)"

# ═══════════════════════════════════════════════════════════════════════════
#  VALUE ACTIONS
# ═══════════════════════════════════════════════════════════════════════════

def eq_action_kill(band, flick_duration_s):
    """
    Double-flick LEFT — SMART kill/normalize.
      - If value > 0 dB → normalize back to 0 dB
      - If value ≤ 0 dB → KILL (bass = -inf, mid/high = -19 dB)
    """
    with st._lock:
        current = st.state["eq_macro_values"][band]
        band_name = EQ_MACRO_NAMES_EXPECTED[band]

    if current > EQ_NEUTRAL_MACRO + 0.5:
        start_eq_ramp(band, EQ_NEUTRAL_MACRO, flick_duration_s)
        with st._lock:
            st.state["last_action"] = f"↓ {band_name} normalized (0 dB)"
    else:
        if band == EQ_SLOT_LOW:
            target = EQ_MACRO_MIN
            action_text = "💥 BASS KILLED"
        else:
            target = EQ_CUT_HALF_MACRO
            action_text = f"⬇ {band_name} cut (-19 dB)"

        start_eq_ramp(band, target, flick_duration_s)
        with st._lock:
            st.state["last_action"] = action_text

def eq_action_boost_or_restore(band, flick_duration_s):
    """
    Double-flick RIGHT — SMART restore/boost.
      - If value < 0 dB → restore to 0 dB
      - If value ≥ 0 dB + Mid/High → +15% of remaining headroom
      - If value ≥ 0 dB + LOW (bass) → BLOCKED (safety)
    """
    with st._lock:
        current = st.state["eq_macro_values"][band]
        band_name = EQ_MACRO_NAMES_EXPECTED[band]

    if current < EQ_NEUTRAL_MACRO - 0.5:
        start_eq_ramp(band, EQ_NEUTRAL_MACRO, flick_duration_s)
        with st._lock:
            st.state["last_action"] = f"↑ {band_name} restored (0 dB)"
    elif band == EQ_SLOT_LOW:
        with st._lock:
            st.state["last_action"] = "🚫 Bass boost blocked (use stick for safe +2 dB)"
    else:
        remaining = EQ_MACRO_MAX - current
        boost = remaining * EQ_BOOST_PCT
        target = clamp(current + boost, EQ_NEUTRAL_MACRO, EQ_MACRO_MAX)
        start_eq_ramp(band, target, flick_duration_s)
        with st._lock:
            st.state["last_action"] = f"↑ {band_name} boosted (+{boost:.2f} macro)"

# ═══════════════════════════════════════════════════════════════════════════
#  X GESTURE — VALUE ACTIONS (double-flick)
# ═══════════════════════════════════════════════════════════════════════════

def update_eq_x_gesture(stick_x, now):
    """
    v9.11 — X axis double-flick detection for VALUE actions.
    LEFT  → eq_action_kill (smart: normalize if above 0 dB, kill if at/below)
    RIGHT → eq_action_boost_or_restore

    Returns True if gesture in progress (caller pauses encoder).
    """
    with st._lock:
        gesture_state = st.state["_eq_flick_x_state"]
        gesture_dir   = st.state["_eq_flick_x_dir"]
        gesture_time  = st.state["_eq_flick_x_time"]
        selected_band = st.state["eq_selected_band"]
        timeout_s     = EQ_FLICK_TIMEOUT_MS / 1000.0

    abs_x = abs(stick_x)
    dir_x = 1 if stick_x > 0 else (-1 if stick_x < 0 else 0)

    if gesture_state == "idle":
        if abs_x >= EQ_FLICK_EXTREME:
            with st._lock:
                st.state["_eq_flick_x_state"] = "flicked"
                st.state["_eq_flick_x_dir"]   = dir_x
                st.state["_eq_flick_x_time"]  = now
                st.state["eq_armed_band"]     = selected_band
                st.state["eq_armed_until"]    = now + timeout_s
            band_name = EQ_MACRO_NAMES_EXPECTED[selected_band]
            arrow = "→ boost/restore" if dir_x > 0 else "← cut/normalize"
            with st._lock:
                st.state["last_action"] = f"◇ {band_name} {arrow} armed"
            return True

    elif gesture_state == "flicked":
        if abs_x < EQ_FLICK_RETURN:
            with st._lock:
                st.state["_eq_flick_x_state"] = "returned"
                st.state["_eq_flick_x_returned_time"] = now
            return True
        elif (now - gesture_time) > timeout_s:
            with st._lock:
                st.state["_eq_flick_x_state"] = "idle"
                st.state["_eq_flick_x_dir"]   = 0
                st.state["eq_armed_band"]     = -1
                st.state["last_action"] = "✗ EQ action timeout"
            return False
        return True

    elif gesture_state == "returned":
        if abs_x >= EQ_FLICK_EXTREME and dir_x == gesture_dir:
            flick_duration = now - gesture_time
            if gesture_dir < 0:
                eq_action_kill(selected_band, flick_duration)
            else:
                eq_action_boost_or_restore(selected_band, flick_duration)
            with st._lock:
                st.state["_eq_flick_x_state"] = "idle"
                st.state["_eq_flick_x_dir"]   = 0
                st.state["eq_armed_band"]     = -1
            return True
        elif (now - gesture_time) > timeout_s:
            with st._lock:
                st.state["_eq_flick_x_state"] = "idle"
                st.state["_eq_flick_x_dir"]   = 0
                st.state["eq_armed_band"]     = -1
                st.state["last_action"] = "✗ EQ action timeout"
            return False
        return True

    return False

# ═══════════════════════════════════════════════════════════════════════════
#  Y GESTURE — BAND NAVIGATION (double-flick)
# ═══════════════════════════════════════════════════════════════════════════

def update_eq_y_gesture_v911(stick_y, now):
    """
    v9.11 — Y axis double-flick BAND NAVIGATION.

    UP (positive Y)   → next band UP    (MID→HIGH→LOW→MID loop)
    DOWN (negative Y) → next band DOWN  (MID→LOW→HIGH→MID loop)

    Returns True if gesture in progress (caller freezes X encoder).
    """
    with st._lock:
        gesture_state = st.state["_eq_flick_y_state"]
        gesture_dir   = st.state["_eq_flick_y_dir"]
        gesture_time  = st.state["_eq_flick_y_time"]
        selected_band = st.state["eq_selected_band"]
        timeout_s     = EQ_FLICK_TIMEOUT_MS / 1000.0

    abs_y = abs(stick_y)
    dir_y = 1 if stick_y > 0 else (-1 if stick_y < 0 else 0)

    if gesture_state == "idle":
        if abs_y >= EQ_FLICK_EXTREME:
            target_band = (selected_band + dir_y) % 3
            with st._lock:
                st.state["_eq_flick_y_state"] = "flicked"
                st.state["_eq_flick_y_dir"]   = dir_y
                st.state["_eq_flick_y_time"]  = now
                st.state["eq_armed_band"]     = target_band
                st.state["eq_armed_until"]    = now + timeout_s
            band_name = EQ_MACRO_NAMES_EXPECTED[target_band]
            arrow = "↑" if dir_y > 0 else "↓"
            with st._lock:
                st.state["last_action"] = f"◇ {arrow} {band_name} armed (flick again)"
            return True

    elif gesture_state == "flicked":
        if abs_y < EQ_FLICK_RETURN:
            with st._lock:
                st.state["_eq_flick_y_state"] = "returned"
                st.state["_eq_flick_y_returned_time"] = now
            return True
        elif (now - gesture_time) > timeout_s:
            with st._lock:
                st.state["_eq_flick_y_state"] = "idle"
                st.state["_eq_flick_y_dir"]   = 0
                st.state["eq_armed_band"]     = -1
                st.state["last_action"] = "✗ Band switch timeout"
            return False
        return True

    elif gesture_state == "returned":
        if abs_y >= EQ_FLICK_EXTREME and dir_y == gesture_dir:
            eq_switch_band(gesture_dir)
            with st._lock:
                st.state["_eq_flick_y_state"] = "idle"
                st.state["_eq_flick_y_dir"]   = 0
                st.state["eq_armed_band"]     = -1
            return True
        elif (now - gesture_time) > timeout_s:
            with st._lock:
                st.state["_eq_flick_y_state"] = "idle"
                st.state["_eq_flick_y_dir"]   = 0
                st.state["eq_armed_band"]     = -1
                st.state["last_action"] = "✗ Band switch timeout"
            return False
        return True

    return False

# ═══════════════════════════════════════════════════════════════════════════
#  CONTINUOUS ENCODER — X axis (held)
# ═══════════════════════════════════════════════════════════════════════════

def eq_drive_continuous_encoder(stick_x, now):
    """
    Encoder-style EQ control via X axis.
    Right = boost, Left = cut, release = HOLD.
    Includes sticky 0 dB detent and bass safety cap.
    """
    with st._lock:
        selected_band = st.state["eq_selected_band"]
        current_val   = st.state["eq_macro_values"][selected_band]
        last_tick     = st.state["_eq_encoder_last_tick"]
        last_at       = st.state["_eq_last_write_at"][selected_band]
        last_val      = st.state["_eq_last_write_val"][selected_band]

    if last_tick <= 0.0:
        dt = 0.0
    else:
        dt = now - last_tick
        if dt > 0.1:
            dt = 0.0

    with st._lock:
        st.state["_eq_encoder_last_tick"] = now

    if abs(stick_x) < EQ_AXIS_DEAD_ZONE:
        return
    if dt <= 0.0:
        return

    delta = eq_encoder_delta(stick_x, dt)
    if delta == 0.0:
        return

    distance_from_neutral = abs(current_val - EQ_NEUTRAL_MACRO)
    if distance_from_neutral < EQ_DETENT_RANGE:
        detent_factor = distance_from_neutral / EQ_DETENT_RANGE
        delta *= max(EQ_DETENT_MIN_FACTOR, detent_factor)

    new_val = current_val + delta

    is_bass = (selected_band == EQ_SLOT_LOW)
    upper_cap = EQ_BASS_BOOST_CAP if is_bass else EQ_MACRO_MAX
    new_val = clamp(new_val, EQ_MACRO_MIN, upper_cap)

    if (now - last_at) < EQ_WRITE_THROTTLE:
        return
    if abs(new_val - last_val) < 0.3:
        return

    with st._lock:
        st.state["eq_macro_values"][selected_band]    = new_val
        st.state["_eq_last_write_at"][selected_band]  = now
        st.state["_eq_last_write_val"][selected_band] = new_val

    osc_set_eq_macro(selected_band, new_val)