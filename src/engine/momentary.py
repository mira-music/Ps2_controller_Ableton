"""
================================================================================
  src/engine/momentary.py — Momentary FX Buttons (L1 layer)
================================================================================
  Three momentary effects active while a button is held in FX mode:
    L1+X: STUTTER       (Beat Repeat on/off)
    L1+O: BASS CUT      (HP filter @ 200 Hz, snapshot-restore on release)
    L1+□: FX SEND THROW (jam to max, snapshot-restore on release)

  All three follow snapshot-restore pattern (v9.7+ behavior).
  is_macro_under_momentary_control() used by FX driver to prevent
  stick from fighting the momentary state.
================================================================================
"""

from src import state as st
from src.config import (
    FX_SLOT_STUTTER, FX_SLOT_FILTER_FREQ, FX_SLOT_FILTER_MODE, FX_SLOT_FX_SEND,
    BASS_CUT_FREQ_VALUE, BASS_CUT_MODE_VALUE,
)
from src.helpers import clamp
from src.osc.client import osc_set_fx_macro

# ═══════════════════════════════════════════════════════════════════════════
#  GUARD
# ═══════════════════════════════════════════════════════════════════════════

def is_macro_under_momentary_control(slot):
    with st._lock:
        if slot == FX_SLOT_STUTTER and st.state["_momentary_stutter_active"]:
            return True
        if slot in (FX_SLOT_FILTER_FREQ, FX_SLOT_FILTER_MODE) and st.state["_momentary_bass_cut_active"]:
            return True
        if slot == FX_SLOT_FX_SEND and st.state["_momentary_fx_throw_active"]:
            return True
    return False

# ═══════════════════════════════════════════════════════════════════════════
#  STUTTER (L1 + X)
# ═══════════════════════════════════════════════════════════════════════════

def momentary_stutter_on():
    with st._lock:
        if st.state["_momentary_stutter_active"]:
            return
        if not st.state["fx_ready"]:
            return
        st.state["_momentary_stutter_active"] = True
        st.state["last_action"] = "💥 STUTTER (held)"
        max_val = st.state["fx_macro_maxs"][FX_SLOT_STUTTER]
    osc_set_fx_macro(FX_SLOT_STUTTER, max_val)

def momentary_stutter_off():
    with st._lock:
        if not st.state["_momentary_stutter_active"]:
            return
        st.state["_momentary_stutter_active"] = False
        st.state["last_action"] = "Stutter released"
    osc_set_fx_macro(FX_SLOT_STUTTER, 0.0)

# ═══════════════════════════════════════════════════════════════════════════
#  BASS CUT (L1 + O)
# ═══════════════════════════════════════════════════════════════════════════

def momentary_bass_cut_on():
    with st._lock:
        if st.state["_momentary_bass_cut_active"]:
            return
        if not st.state["fx_ready"]:
            return
        st.state["_momentary_bass_cut_snapshot"] = {
            "freq": st.state["fx_macro_values"][FX_SLOT_FILTER_FREQ],
            "mode": st.state["fx_macro_values"][FX_SLOT_FILTER_MODE],
        }
        st.state["_momentary_bass_cut_active"] = True
        st.state["last_action"] = "🔻 BASS CUT (held)"
        min_f = st.state["fx_macro_mins"][FX_SLOT_FILTER_FREQ]
        max_f = st.state["fx_macro_maxs"][FX_SLOT_FILTER_FREQ]
    target_freq = clamp(BASS_CUT_FREQ_VALUE, min_f, max_f)
    osc_set_fx_macro(FX_SLOT_FILTER_MODE, BASS_CUT_MODE_VALUE)
    osc_set_fx_macro(FX_SLOT_FILTER_FREQ, target_freq)

def momentary_bass_cut_off():
    """Restore PRE-ENGAGE snapshot (v9.7+ behavior)."""
    with st._lock:
        if not st.state["_momentary_bass_cut_active"]:
            return
        st.state["_momentary_bass_cut_active"] = False
        snapshot = st.state["_momentary_bass_cut_snapshot"]
        restore_freq = snapshot["freq"]
        restore_mode = snapshot["mode"]
        st.state["last_action"] = (
            f"Bass cut released → restored to {restore_freq:.1f}/{restore_mode:.1f}"
        )
    osc_set_fx_macro(FX_SLOT_FILTER_FREQ, restore_freq)
    osc_set_fx_macro(FX_SLOT_FILTER_MODE, restore_mode)

# ═══════════════════════════════════════════════════════════════════════════
#  FX SEND THROW (L1 + □)
# ═══════════════════════════════════════════════════════════════════════════

def momentary_fx_throw_on():
    with st._lock:
        if st.state["_momentary_fx_throw_active"]:
            return
        if not st.state["fx_ready"]:
            return
        st.state["_momentary_fx_throw_snapshot"] = {
            "fx_send": st.state["fx_macro_values"][FX_SLOT_FX_SEND]
        }
        st.state["_momentary_fx_throw_active"] = True
        st.state["last_action"] = "🌫 FX THROW (held)"
        max_val = st.state["fx_macro_maxs"][FX_SLOT_FX_SEND]
    osc_set_fx_macro(FX_SLOT_FX_SEND, max_val)

def momentary_fx_throw_off():
    """Always restores to pre-engage value."""
    with st._lock:
        if not st.state["_momentary_fx_throw_active"]:
            return
        st.state["_momentary_fx_throw_active"] = False
        target = st.state["_momentary_fx_throw_snapshot"]["fx_send"]
        st.state["last_action"] = f"FX throw released → restored to {target:.2f}"
    osc_set_fx_macro(FX_SLOT_FX_SEND, target)

# ═══════════════════════════════════════════════════════════════════════════
#  PANIC RESET
# ═══════════════════════════════════════════════════════════════════════════

def force_off_all_momentaries():
    momentary_stutter_off()
    momentary_bass_cut_off()
    momentary_fx_throw_off()