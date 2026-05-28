"""
================================================================================
  src/helpers.py — Utility Functions
================================================================================
  Stateless helpers used across multiple modules. Math, formatting,
  smoothing, EQ-specific math helpers.
================================================================================
"""

import math
import time

from src import state as st
from src.config import (
    ABLETON_UNITY,
    SMOOTHING_FACTOR,
    FX_ACCEL_RAMP_S, FX_ACCEL_MAX_MULT,
    EQ_AXIS_DEAD_ZONE, EQ_SWEEP_SECONDS, EQ_ENCODER_CURVE_EXP,
    EQ_MACRO_MIN, EQ_MACRO_MAX, EQ_NEUTRAL_MACRO,
)

# ═══════════════════════════════════════════════════════════════════════════
#  BASIC HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def db_from_vol(vol):
    if vol <= 0:
        return "-∞ dB"
    db = 20 * math.log10(vol / ABLETON_UNITY)
    return f"{db:+.1f} dB"

def clamp(val, lo, hi):
    return max(lo, min(hi, val))

def flash(key):
    with st._lock:
        st.state[key]           = True
        st.state["flash_until"] = time.perf_counter() + 0.6

def clear_flashes_if_expired():
    with st._lock:
        if time.perf_counter() > st.state["flash_until"]:
            st.state["flash_scene"] = False
            st.state["flash_track"] = False
            st.state["flash_bmark"] = False
            st.state["flash_group"] = False

def hybrid_curve(value):
    if value == 0:
        return 0.0
    return (abs(value) ** 1.8) * (1.0 if value > 0 else -1.0)

def smooth_axis(previous, current, factor=None):
    f = factor if factor is not None else SMOOTHING_FACTOR
    return previous * (1.0 - f) + current * f

def mark_controller_input():
    with st._lock:
        st.state["_last_input_at"] = time.perf_counter()

def int_to_hex_color(color_int, fallback="#666666"):
    if color_int is None:
        return fallback
    try:
        color_int = int(color_int) & 0xFFFFFF
    except (TypeError, ValueError):
        return fallback
    if color_int == 0:
        return fallback
    return f"#{color_int:06x}"

# ═══════════════════════════════════════════════════════════════════════════
#  FX ACCELERATION
# ═══════════════════════════════════════════════════════════════════════════

def reset_accel_state():
    with st._lock:
        for k in st.state["_accel_since"]:
            st.state["_accel_since"][k]    = 0.0
            st.state["_accel_last_dir"][k] = 0

def compute_accel_multiplier(axis_key, current_dir, now):
    with st._lock:
        last_dir = st.state["_accel_last_dir"][axis_key]
        since    = st.state["_accel_since"][axis_key]

        if current_dir == 0:
            st.state["_accel_since"][axis_key]    = 0.0
            st.state["_accel_last_dir"][axis_key] = 0
            return 1.0

        if current_dir != last_dir:
            st.state["_accel_since"][axis_key]    = now
            st.state["_accel_last_dir"][axis_key] = current_dir
            return 1.0

        elapsed = now - since

    mult = 1.0 + (elapsed / FX_ACCEL_RAMP_S)
    return min(mult, FX_ACCEL_MAX_MULT)

# ═══════════════════════════════════════════════════════════════════════════
#  EQ HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def eq_visual_position(macro_value):
    """
    Convert macro value (0-127) to a visual knob position (0.0-1.0).
    0.0 = far left (-inf dB), 0.5 = top (0 dB), 1.0 = far right (+6 dB).
    """
    if macro_value <= EQ_NEUTRAL_MACRO:
        return (macro_value / EQ_NEUTRAL_MACRO) * 0.5
    else:
        boost_range = EQ_MACRO_MAX - EQ_NEUTRAL_MACRO
        return 0.5 + ((macro_value - EQ_NEUTRAL_MACRO) / boost_range) * 0.5

def eq_encoder_delta(stick_value, dt):
    """
    Convert stick deflection + frame dt → signed macro value delta.
    Curve: see EQ_ENCODER_CURVE_EXP (1.2 = slight start easing).
    """
    abs_v = abs(stick_value)
    if abs_v < EQ_AXIS_DEAD_ZONE:
        return 0.0
    normalized = (abs_v - EQ_AXIS_DEAD_ZONE) / (1.0 - EQ_AXIS_DEAD_ZONE)
    normalized = clamp(normalized, 0.0, 1.0)
    shaped = normalized ** EQ_ENCODER_CURVE_EXP
    macro_range = EQ_MACRO_MAX - EQ_MACRO_MIN
    velocity = (macro_range / EQ_SWEEP_SECONDS) * shaped
    sign = 1.0 if stick_value > 0 else -1.0
    return velocity * sign * dt