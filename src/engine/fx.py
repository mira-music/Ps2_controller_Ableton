"""
================================================================================
  src/engine/fx.py — FX Macro Stick Control + Delay FB Stepping
================================================================================
  fx_drive_macro()    — integrator-style stick driver (used by L1+stick handlers)
                        Adds delta per frame to current macro value.
                        Respects momentary control (won't fight stutter, bass cut,
                        FX throw while held).
  
  fx_step_delay_fb()  — discrete D-pad stepping for Delay FB.
                        20 steps across the range, with debounce, and a 92%
                        clamp so the delay never goes into infinite feedback.
================================================================================
"""

import time

from src import state as st
from src.config import (
    FX_AXIS_DEAD_ZONE, FX_WRITE_THROTTLE, FX_WRITE_EPSILON_FRAC,
    FX_SWEEP_SECONDS,
    FX_SLOT_DELAY_FB,
    FX_DELAY_FB_DEBOUNCE, FX_DELAY_FB_STEPS, FX_DELAY_FB_CLAMP_FRAC,
)
from src.helpers import clamp
from src.osc.client import osc_set_fx_macro
from src.engine.momentary import is_macro_under_momentary_control

# ═══════════════════════════════════════════════════════════════════════════
#  SLOT INFO HELPER
# ═══════════════════════════════════════════════════════════════════════════

def _fx_get_slot_info(slot):
    """Returns (name, current_val, min_val, max_val, sweep_seconds) or None."""
    with st._lock:
        if not st.state["fx_ready"]:
            return None
        if slot < 0 or slot >= 8:
            return None
        name = st.state["fx_macro_names"][slot]
        if not name:
            return None
        val      = st.state["fx_macro_values"][slot]
        min_val  = st.state["fx_macro_mins"][slot]
        max_val  = st.state["fx_macro_maxs"][slot]
    sweep = FX_SWEEP_SECONDS.get(name, 3.0)
    return name, val, min_val, max_val, sweep

# ═══════════════════════════════════════════════════════════════════════════
#  FX MACRO STICK DRIVER (integrator)
# ═══════════════════════════════════════════════════════════════════════════

def fx_drive_macro(slot, stick_value, dt, accel_mult=1.0):
    """
    Integrator-style stick driver.
    delta = stick * (range / sweep) * dt * accel_mult
    Throttled + epsilon-culled. Skips if a momentary owns this slot.
    """
    if abs(stick_value) < FX_AXIS_DEAD_ZONE:
        return
    if is_macro_under_momentary_control(slot):
        return

    info = _fx_get_slot_info(slot)
    if info is None:
        return
    name, current, min_val, max_val, sweep_s = info

    macro_range = max_val - min_val
    if macro_range <= 0 or sweep_s <= 0:
        return

    delta = stick_value * (macro_range / sweep_s) * dt * accel_mult
    target = clamp(current + delta, min_val, max_val)

    now = time.perf_counter()
    with st._lock:
        last_at  = st.state["_fx_last_write_at"][slot]
        last_val = st.state["_fx_last_write_val"][slot]

    if abs(target - last_val) < macro_range * FX_WRITE_EPSILON_FRAC:
        return
    if (now - last_at) < FX_WRITE_THROTTLE:
        return

    with st._lock:
        st.state["fx_macro_values"][slot]    = target
        st.state["_fx_last_write_at"][slot]  = now
        st.state["_fx_last_write_val"][slot] = target
        st.state["_fx_active_slot"]          = slot
        st.state["_fx_active_until"]         = now + 0.4
        st.state["last_action"] = f"⚡ {name}"

    osc_set_fx_macro(slot, target)

# ═══════════════════════════════════════════════════════════════════════════
#  DELAY FB DISCRETE STEPPING (D-pad in FX mode)
# ═══════════════════════════════════════════════════════════════════════════

def fx_step_delay_fb(direction):
    """
    Discrete D-pad stepping for Delay FB.
    Range divided into FX_DELAY_FB_STEPS (20) steps.
    Capped at FX_DELAY_FB_CLAMP_FRAC (92%) to prevent runaway feedback.
    Debounced via FX_DELAY_FB_DEBOUNCE.
    """
    now = time.perf_counter()
    with st._lock:
        if now - st.state["_fx_last_dpad_h"] < FX_DELAY_FB_DEBOUNCE:
            return
        st.state["_fx_last_dpad_h"] = now

    info = _fx_get_slot_info(FX_SLOT_DELAY_FB)
    if info is None:
        return
    name, current, min_val, max_val, _ = info

    macro_range = max_val - min_val
    if macro_range <= 0:
        return

    step_size = macro_range / FX_DELAY_FB_STEPS
    current_step = round((current - min_val) / step_size)
    new_step     = clamp(current_step + direction, 0, FX_DELAY_FB_STEPS)
    target       = min_val + new_step * step_size

    cap = min_val + macro_range * FX_DELAY_FB_CLAMP_FRAC
    capped = False
    if target > cap:
        target = cap
        capped = True

    target = clamp(target, min_val, max_val)

    if abs(target - current) < macro_range * FX_WRITE_EPSILON_FRAC:
        with st._lock:
            st.state["last_action"] = f"⚠ Delay FB at {'MAX (capped 92%)' if direction > 0 else 'MIN'}"
        return

    with st._lock:
        st.state["fx_macro_values"][FX_SLOT_DELAY_FB]    = target
        st.state["_fx_last_write_at"][FX_SLOT_DELAY_FB]  = now
        st.state["_fx_last_write_val"][FX_SLOT_DELAY_FB] = target
        st.state["_fx_active_slot"]                      = FX_SLOT_DELAY_FB
        st.state["_fx_active_until"]                     = now + 0.4
        cap_note = "  (capped 92%)" if capped else ""
        st.state["last_action"] = (
            f"⚡ Delay FB {'→' if direction > 0 else '←'}  "
            f"step {new_step}/{FX_DELAY_FB_STEPS}{cap_note}"
        )

    osc_set_fx_macro(FX_SLOT_DELAY_FB, target)