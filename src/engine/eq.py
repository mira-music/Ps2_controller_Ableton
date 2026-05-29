"""
================================================================================
  src/engine/eq.py — EQ Mode Engine (Build B: 4 bands incl. TRIM)
================================================================================

  Y-axis double-flick rotation (4 positions, no borders):
    Y up:   MID → HIGH → TRIM → LOW → MID → ...
    Y down: MID → LOW → TRIM → HIGH → MID → ...

  X-axis double-flick on EQ bands (Low/Mid/High):
    LEFT  → smart kill / normalize
    RIGHT → smart restore / boost

  X-axis double-flick on TRIM (conditional — always toward 0 dB):
    When TRIM > 0 dB:   LEFT normalizes to 0 dB,  RIGHT does nothing
    When TRIM ≤ 0 dB:   RIGHT normalizes to 0 dB, LEFT does nothing
    When TRIM = 0 dB:   both do nothing

  X-axis continuous (encoder):
    On EQ bands: cfg.EQ_* values, sticky 0dB detent, bass safety cap
    On TRIM:     cfg.TRIM_* values (fluid, slightly slower), hard cap at +9dB

  CALIBRATION NOTE:
    EQ Three macros: macro 107.9 = 0 dB (logarithmic curve, asymmetric)
    TRIM (Utility Gain): macro 64.0 = 0 dB (linear above neutral)
    These are TWO DIFFERENT calibrations. Don't mix them up.
================================================================================
"""

import time
import math
from src import state as st
from src.config import (
    # EQ Three (bands)
    EQ_NEUTRAL_MACRO, EQ_MACRO_MIN, EQ_MACRO_MAX, EQ_CUT_HALF_MACRO,
    # Slot indices + names
    EQ_SLOT_LOW, EQ_SLOT_MID, EQ_SLOT_HIGH, EQ_SLOT_TRIM,
    EQ_MACRO_NAMES_EXPECTED,
    EQ_MACRO_COUNT,
    # Build B: TRIM has its OWN calibration (Utility Gain ≠ EQ Three)
    TRIM_NEUTRAL_MACRO, TRIM_DB_PER_MACRO,
)
from src.config_loader import cfg
from src.helpers import clamp, eq_encoder_delta
from src.osc.client import osc_set_eq_macro
from src.engine.polling import start_eq_ramp
from src.log_setup import get_logger

log = get_logger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def _is_trim(band):
    """True if the given band index is the TRIM slot."""
    return band == EQ_SLOT_TRIM


def _trim_max_macro():
    """
    Convert cfg.TRIM_MAX_DB to a macro value using TRIM's actual calibration.

    Empirical TRIM curve (NOT same as EQ Three!):
      macro 64.0  → 0 dB neutral
      macro 80.2  → +9 dB (default cap with TRIM_MAX_DB=9.0)
      macro 127.0 → +35 dB (Utility Gain max)

    Linear conversion in the boost zone:
      macro = TRIM_NEUTRAL_MACRO + (target_dB / TRIM_DB_PER_MACRO)
    """
    if cfg.TRIM_MAX_DB <= 0.0:
        return TRIM_NEUTRAL_MACRO
    macro = TRIM_NEUTRAL_MACRO + (cfg.TRIM_MAX_DB / TRIM_DB_PER_MACRO)
    return clamp(macro, TRIM_NEUTRAL_MACRO, EQ_MACRO_MAX)


# ═══════════════════════════════════════════════════════════════════════════
#  MODE TOGGLE
# ═══════════════════════════════════════════════════════════════════════════

def action_toggle_eq_mode():
    """Toggle EQ mode on/off. Called by R3 button (alone) in nav layer."""
    with st._lock:
        active = not st.state["eq_mode_active"]
        st.state["eq_mode_active"] = active
        st.state["_eq_flick_x_state"] = "idle"
        st.state["_eq_flick_x_dir"]   = 0
        st.state["_eq_flick_y_state"] = "idle"
        st.state["_eq_flick_y_dir"]   = 0
        st.state["eq_armed_band"]     = -1
        st.state["last_action"]       = "EQ MODE: ON" if active else "EQ MODE: OFF"

    if active:
        log.info("EQ mode ON")
    else:
        log.info("EQ mode OFF")


# ═══════════════════════════════════════════════════════════════════════════
#  BAND SWITCH — uses EQ_MACRO_COUNT (4) for rotation modulus
# ═══════════════════════════════════════════════════════════════════════════

def eq_switch_band(direction):
    """
    Switch to next/prev band. 4-position rotation including TRIM.

    Rotation order (slot indices):
      LOW=0, MID=1, HIGH=2, TRIM=3

    Y up   (direction=+1): MID → HIGH → TRIM → LOW → MID → ...
    Y down (direction=-1): reverse
    """
    with st._lock:
        cur = st.state["eq_selected_band"]
        new = (cur + direction) % EQ_MACRO_COUNT
        st.state["eq_selected_band"] = new
        st.state["eq_armed_band"]    = -1
        st.state["_eq_encoder_last_tick"] = time.perf_counter()
        band_name = EQ_MACRO_NAMES_EXPECTED[new]
        st.state["last_action"] = f"◇ → {band_name}"
    log.info(f"EQ band switched to {band_name}")


def eq_arm_band(direction):
    """Visual armed state during first flick."""
    with st._lock:
        cur = st.state["eq_selected_band"]
        armed = (cur + direction) % EQ_MACRO_COUNT
        st.state["eq_armed_band"]  = armed
        st.state["eq_armed_until"] = time.perf_counter() + (cfg.EQ_FLICK_TIMEOUT_MS / 1000.0)
        band_name = EQ_MACRO_NAMES_EXPECTED[armed]
        st.state["last_action"] = f"◇ → {band_name} armed (flick again)"


# ═══════════════════════════════════════════════════════════════════════════
#  VALUE ACTIONS — kill / normalize / boost / restore
# ═══════════════════════════════════════════════════════════════════════════

def eq_action_kill(band, flick_duration_s):
    """
    Double-flick LEFT — context-aware.

    EQ bands (Low/Mid/High):
      if value > 0 dB → normalize to 0 dB
      if value ≤ 0 dB → KILL (Low = -∞, Mid/High = -19 dB)

    TRIM (conditional — flick toward center only):
      if value > 0 dB → normalize to 0 dB
      if value ≤ 0 dB → does NOTHING (already at/below center, LEFT makes no sense)
    """
    with st._lock:
        current = st.state["eq_macro_values"][band]
        band_name = EQ_MACRO_NAMES_EXPECTED[band]

    # ── TRIM-specific logic ──
    if _is_trim(band):
        if current > TRIM_NEUTRAL_MACRO + 0.5:
            # Above 0 dB → LEFT normalizes back to 0
            start_eq_ramp(band, TRIM_NEUTRAL_MACRO, flick_duration_s)
            with st._lock:
                st.state["last_action"] = f"↓ {band_name} → 0 dB"
        else:
            # At or below 0 dB → LEFT does nothing
            with st._lock:
                st.state["last_action"] = f"✗ {band_name} already at/below 0 dB"
        return

    # ── EQ band logic ──
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
    Double-flick RIGHT — context-aware.

    EQ bands (Low/Mid/High):
      if value < 0 dB → restore to 0 dB
      if value ≥ 0 dB + Mid/High → asymptotic +15% headroom boost
      if value ≥ 0 dB + LOW → 🚫 BLOCKED (sub safety)

    TRIM (conditional — flick toward center only):
      if value < 0 dB → normalize to 0 dB
      if value ≥ 0 dB → does NOTHING (already at/above center, RIGHT makes no sense)
    """
    with st._lock:
        current = st.state["eq_macro_values"][band]
        band_name = EQ_MACRO_NAMES_EXPECTED[band]

    # ── TRIM-specific logic ──
    if _is_trim(band):
        if current < TRIM_NEUTRAL_MACRO - 0.5:
            # Below 0 dB → RIGHT normalizes back to 0
            start_eq_ramp(band, TRIM_NEUTRAL_MACRO, flick_duration_s)
            with st._lock:
                st.state["last_action"] = f"↑ {band_name} → 0 dB"
        else:
            # At or above 0 dB → RIGHT does nothing
            with st._lock:
                st.state["last_action"] = f"✗ {band_name} already at/above 0 dB"
        return

    # ── EQ band logic ──
    if current < EQ_NEUTRAL_MACRO - 0.5:
        start_eq_ramp(band, EQ_NEUTRAL_MACRO, flick_duration_s)
        with st._lock:
            st.state["last_action"] = f"↑ {band_name} restored (0 dB)"
    elif band == EQ_SLOT_LOW:
        with st._lock:
            st.state["last_action"] = "🚫 Bass boost blocked (use stick for safe +2 dB)"
    else:
        remaining = EQ_MACRO_MAX - current
        boost = remaining * cfg.EQ_BOOST_PCT
        target = clamp(current + boost, EQ_NEUTRAL_MACRO, EQ_MACRO_MAX)
        start_eq_ramp(band, target, flick_duration_s)
        with st._lock:
            st.state["last_action"] = f"↑ {band_name} boosted (+{boost:.2f} macro)"


# ═══════════════════════════════════════════════════════════════════════════
#  X GESTURE — VALUE ACTIONS (double-flick)
# ═══════════════════════════════════════════════════════════════════════════

def update_eq_x_gesture(stick_x, now):
    """
    X axis double-flick detection for VALUE actions.
    LEFT  → eq_action_kill
    RIGHT → eq_action_boost_or_restore

    On TRIM: conditional — only the direction TOWARD 0 dB works.

    Returns True if gesture in progress (caller pauses encoder).
    """
    with st._lock:
        gesture_state = st.state["_eq_flick_x_state"]
        gesture_dir   = st.state["_eq_flick_x_dir"]
        gesture_time  = st.state["_eq_flick_x_time"]
        selected_band = st.state["eq_selected_band"]
        timeout_s     = cfg.EQ_FLICK_TIMEOUT_MS / 1000.0

    abs_x = abs(stick_x)
    dir_x = 1 if stick_x > 0 else (-1 if stick_x < 0 else 0)

    if gesture_state == "idle":
        if abs_x >= cfg.EQ_FLICK_EXTREME:
            with st._lock:
                st.state["_eq_flick_x_state"] = "flicked"
                st.state["_eq_flick_x_dir"]   = dir_x
                st.state["_eq_flick_x_time"]  = now
                st.state["eq_armed_band"]     = selected_band
                st.state["eq_armed_until"]    = now + timeout_s
            band_name = EQ_MACRO_NAMES_EXPECTED[selected_band]
            # TRIM hint depends on direction AND current value
            if _is_trim(selected_band):
                arrow = "→ → 0 dB?" if dir_x > 0 else "← → 0 dB?"
            else:
                arrow = "→ boost/restore" if dir_x > 0 else "← cut/normalize"
            with st._lock:
                st.state["last_action"] = f"◇ {band_name} {arrow} armed"
            return True

    elif gesture_state == "flicked":
        if abs_x < cfg.EQ_FLICK_RETURN:
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
        if abs_x >= cfg.EQ_FLICK_EXTREME and dir_x == gesture_dir:
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
#  Uses EQ_MACRO_COUNT (4) for rotation modulus
# ═══════════════════════════════════════════════════════════════════════════

def update_eq_y_gesture_v911(stick_y, now):
    """
    Y axis double-flick BAND NAVIGATION.
    4-position rotation (Low, Mid, High, TRIM).
    UP (positive Y)   → next band UP
    DOWN (negative Y) → next band DOWN
    """
    with st._lock:
        gesture_state = st.state["_eq_flick_y_state"]
        gesture_dir   = st.state["_eq_flick_y_dir"]
        gesture_time  = st.state["_eq_flick_y_time"]
        selected_band = st.state["eq_selected_band"]
        timeout_s     = cfg.EQ_FLICK_TIMEOUT_MS / 1000.0

    abs_y = abs(stick_y)
    dir_y = 1 if stick_y > 0 else (-1 if stick_y < 0 else 0)

    if gesture_state == "idle":
        if abs_y >= cfg.EQ_FLICK_EXTREME:
            target_band = (selected_band + dir_y) % EQ_MACRO_COUNT
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
        if abs_y < cfg.EQ_FLICK_RETURN:
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
        if abs_y >= cfg.EQ_FLICK_EXTREME and dir_y == gesture_dir:
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
#  CONTINUOUS ENCODER — routes by selected band
# ═══════════════════════════════════════════════════════════════════════════

def eq_drive_continuous_encoder(stick_x, now):
    """
    Routes to band-specific encoder. TRIM uses its own faster, separately-
    tuned encoder function. All other bands use the shared EQ encoder.
    """
    with st._lock:
        selected_band = st.state["eq_selected_band"]

    if _is_trim(selected_band):
        _eq_drive_trim_encoder(stick_x, now)
    else:
        _eq_drive_band_encoder(stick_x, now, selected_band)


def _eq_drive_band_encoder(stick_x, now, band):
    """
    Encoder for EQ bands (Low/Mid/High). Uses cfg.EQ_* values.
    Sticky 0 dB detent at EQ_NEUTRAL_MACRO (107.9).
    Bass safety cap on the Low band.
    """
    with st._lock:
        current_val = st.state["eq_macro_values"][band]
        last_tick   = st.state["_eq_encoder_last_tick"]
        last_at     = st.state["_eq_last_write_at"][band]
        last_val    = st.state["_eq_last_write_val"][band]

    if last_tick <= 0.0:
        dt = 0.0
    else:
        dt = now - last_tick
        if dt > 0.1:
            dt = 0.0

    with st._lock:
        st.state["_eq_encoder_last_tick"] = now

    if abs(stick_x) < cfg.EQ_AXIS_DEAD_ZONE:
        return
    if dt <= 0.0:
        return

    delta = eq_encoder_delta(stick_x, dt)
    if delta == 0.0:
        return

    # Sticky 0 dB detent — uses EQ's neutral (107.9)
    distance_from_neutral = abs(current_val - EQ_NEUTRAL_MACRO)
    if distance_from_neutral < cfg.EQ_DETENT_RANGE:
        detent_factor = distance_from_neutral / cfg.EQ_DETENT_RANGE
        delta *= max(cfg.EQ_DETENT_MIN_FACTOR, detent_factor)

    new_val = current_val + delta

    # Bass safety cap
    is_bass = (band == EQ_SLOT_LOW)
    upper_cap = cfg.EQ_BASS_BOOST_CAP if is_bass else EQ_MACRO_MAX
    new_val = clamp(new_val, EQ_MACRO_MIN, upper_cap)

    # Throttle + epsilon
    if (now - last_at) < cfg.EQ_WRITE_THROTTLE:
        return
    if abs(new_val - last_val) < cfg.EQ_WRITE_EPSILON:
        return

    with st._lock:
        st.state["eq_macro_values"][band]    = new_val
        st.state["_eq_last_write_at"][band]  = now
        st.state["_eq_last_write_val"][band] = new_val

    osc_set_eq_macro(band, new_val)


def _eq_drive_trim_encoder(stick_x, now):
    """
    TRIM-specific encoder. Uses cfg.TRIM_* values.
    Hard cap at TRIM_MAX_DB (+9 dB default).
    Sticky 0 dB detent at TRIM_NEUTRAL_MACRO (64.0).
    """
    band = EQ_SLOT_TRIM
    with st._lock:
        current_val = st.state["eq_macro_values"][band]
        last_tick   = st.state["_eq_encoder_last_tick"]
        last_at     = st.state["_eq_last_write_at"][band]
        last_val    = st.state["_eq_last_write_val"][band]

    if last_tick <= 0.0:
        dt = 0.0
    else:
        dt = now - last_tick
        if dt > 0.1:
            dt = 0.0

    with st._lock:
        st.state["_eq_encoder_last_tick"] = now

    if abs(stick_x) < cfg.TRIM_DEAD_ZONE:
        return
    if dt <= 0.0:
        return

    # TRIM-specific delta calc
    abs_x = abs(stick_x)
    normalized = (abs_x - cfg.TRIM_DEAD_ZONE) / (1.0 - cfg.TRIM_DEAD_ZONE)
    normalized = clamp(normalized, 0.0, 1.0)
    shaped = normalized ** cfg.TRIM_CURVE_EXP
    macro_range = EQ_MACRO_MAX - EQ_MACRO_MIN
    velocity = (macro_range / cfg.TRIM_SWEEP_SECONDS) * shaped
    sign = 1.0 if stick_x > 0 else -1.0
    delta = velocity * sign * dt

    if delta == 0.0:
        return

    # Sticky 0 dB detent — TRIM uses its OWN neutral position (64.0)
    distance_from_neutral = abs(current_val - TRIM_NEUTRAL_MACRO)
    if distance_from_neutral < cfg.TRIM_DETENT_RANGE:
        detent_factor = distance_from_neutral / cfg.TRIM_DETENT_RANGE
        delta *= max(cfg.TRIM_DETENT_MIN_FACTOR, detent_factor)

    new_val = current_val + delta

    # TRIM hard cap at +9 dB
    new_val = clamp(new_val, EQ_MACRO_MIN, _trim_max_macro())

    # Throttle + epsilon
    if (now - last_at) < cfg.TRIM_WRITE_THROTTLE:
        return
    if abs(new_val - last_val) < cfg.TRIM_WRITE_EPSILON:
        return

    with st._lock:
        st.state["eq_macro_values"][band]    = new_val
        st.state["_eq_last_write_at"][band]  = now
        st.state["_eq_last_write_val"][band] = new_val

    osc_set_eq_macro(band, new_val)