"""
================================================================================
  src/engine/actions.py — Discrete User Actions
================================================================================
  Button-triggered actions. Pure side-effect functions that update
  state and dispatch OSC. No input handling — that's controller.buttons.
================================================================================
"""

import time
import threading

from src import state as st
from src.config import (
    R3_DOUBLE_CLICK_WINDOW, ABLETON_UNITY,
    FX_RECOVERY_BEHAVIOUR, FX_SLOT_FX_SEND, FX_SEND_DRY_VALUE,
    FX_RECOVERY_FLASH_S,
)
from src.osc.client import (
    osc_launch_clip, osc_stop_clip, osc_stop_track, osc_launch_scene,
    osc_arm_track, osc_play, osc_stop, osc_set_volume, osc_set_fx_macro,
)
from src.log_setup import get_logger

log = get_logger(__name__)

# ═══════════════════════════════════════════════════════════════════════════
#  CLIP / SCENE / TRACK
# ═══════════════════════════════════════════════════════════════════════════

def action_launch_clip():
    with st._lock:
        if st.state["r2_held"]:
            st.state["last_action"] = "🔒 Safety gate ON"
            return
        st.state["last_action"] = "▶  Launch Clip"
    osc_launch_clip()

def action_stop_clip():
    with st._lock:
        st.state["last_action"] = "■  Stop Clip"
    osc_stop_clip()

def action_stop_track():
    with st._lock:
        st.state["last_action"] = "⏹  Stop Track"
    osc_stop_track()

def action_launch_scene():
    with st._lock:
        if st.state["r2_held"]:
            st.state["last_action"] = "🔒 Safety gate ON"
            return
        st.state["last_action"] = "▶▶ Launch Scene"
    osc_launch_scene()

def action_arm_track():
    with st._lock:
        st.state["last_action"] = "●  Arm Track"
    osc_arm_track()

# ═══════════════════════════════════════════════════════════════════════════
#  TRANSPORT
# ═══════════════════════════════════════════════════════════════════════════

def action_transport_toggle():
    with st._lock:
        playing = st.ableton["is_playing"]
    if playing:
        osc_stop()
        with st._lock:
            st.state["last_action"] = "⏹  Transport Stop"
    else:
        osc_play()
        with st._lock:
            st.state["last_action"] = "▶  Transport Play"

# ═══════════════════════════════════════════════════════════════════════════
#  VOLUME MUTE (SELECT+R3)
# ═══════════════════════════════════════════════════════════════════════════

def action_volume_mute_toggle():
    """SELECT+R3 = volume mute toggle. Single click resets to unity,
    double click within 400ms mutes."""
    now = time.perf_counter()
    with st._lock:
        last = st.state["_r3_last_click"]
        if (now - last) <= R3_DOUBLE_CLICK_WINDOW and last > 0:
            st.ableton["track_volume"] = 0.0
            st.state["last_action"]    = "🔇 Muted  (SELECT+R3 once to reset)"
            st.state["_r3_last_click"] = 0.0
            vol = 0.0
        else:
            st.ableton["track_volume"] = ABLETON_UNITY
            st.state["last_action"]    = "↺  Volume reset  0 dB"
            st.state["_r3_last_click"] = now
            vol = ABLETON_UNITY
    osc_set_volume(vol)

# ═══════════════════════════════════════════════════════════════════════════
#  FORCE REFRESH (SELECT+START)
# ═══════════════════════════════════════════════════════════════════════════

def action_force_refresh():
    from src.osc.discovery import fetch_all_names
    from src.controller.watchdog import reprobe_controller

    with st._lock:
        st.state["last_action"] = "🔄 Full refresh (Ableton + colours + controller)…"
    threading.Thread(target=fetch_all_names,    daemon=True).start()
    threading.Thread(target=reprobe_controller, daemon=True,
                     kwargs={"reason": "manual refresh"}).start()

# ═══════════════════════════════════════════════════════════════════════════
#  BASELINE & LOCKS
# ═══════════════════════════════════════════════════════════════════════════

def action_save_baseline():
    with st._lock:
        if not st.state["fx_ready"]:
            st.state["last_action"] = "⚠ Baseline: FX not ready yet"
            return
        current = list(st.state["fx_macro_values"])
        st.state["fx_baseline"]             = current
        st.state["fx_baseline_ready"]       = True
        st.state["fx_baseline_captured_at"] = time.perf_counter()
        st.state["last_action"]             = "✓ Baseline SAVED"
    log.info(f"Baseline manually saved: {[round(v,2) for v in current]}")

def action_toggle_filter_lock():
    with st._lock:
        st.state["fx_filter_locked"] = not st.state["fx_filter_locked"]
        locked = st.state["fx_filter_locked"]
        st.state["last_action"] = "🔒 Filter LOCKED" if locked else "🔓 Filter unlocked"
    log.info(f"{'FILTER LOCK ON' if locked else 'FILTER LOCK OFF'}")

def action_toggle_wet_lock():
    with st._lock:
        st.state["fx_wet_locked"] = not st.state["fx_wet_locked"]
        locked = st.state["fx_wet_locked"]
        st.state["last_action"] = "🔒 Wet LOCKED" if locked else "🔓 Wet unlocked"
    log.info(f"{'WET LOCK ON' if locked else 'WET LOCK OFF'}")

# ═══════════════════════════════════════════════════════════════════════════
#  FX RECOVERY ON L1 RELEASE
# ═══════════════════════════════════════════════════════════════════════════

def fx_recover_on_l1_release():
    """
    Applies the FX_RECOVERY_BEHAVIOUR table when L1 is released.
    Respects filter_locked and wet_locked guards.
    """
    with st._lock:
        if not st.state["fx_ready"]:
            return
        if not st.state["fx_baseline_ready"]:
            st.state["last_action"] = "⚠ Recovery skipped — no baseline captured"
            return

        baseline      = list(st.state["fx_baseline"])
        current       = list(st.state["fx_macro_values"])
        wet_locked    = st.state["fx_wet_locked"]
        filter_locked = st.state["fx_filter_locked"]

    writes = []

    for slot in range(8):
        behaviour = FX_RECOVERY_BEHAVIOUR.get(slot, "skip")

        if behaviour == "skip":
            continue

        if behaviour.startswith("fixed:"):
            try:
                target = float(behaviour.split(":", 1)[1])
            except ValueError:
                continue

        elif behaviour == "wet":
            if wet_locked:
                continue
            if slot == FX_SLOT_FX_SEND:
                target = FX_SEND_DRY_VALUE
            else:
                target = baseline[slot]

        elif behaviour == "filter":
            if filter_locked:
                continue
            target = baseline[slot]

        else:
            continue

        if abs(target - current[slot]) < 0.0001:
            continue

        writes.append((slot, target))

    now = time.perf_counter()
    with st._lock:
        for slot, target in writes:
            st.state["fx_macro_values"][slot] = target
            st.state["_fx_last_write_at"][slot]  = now
            st.state["_fx_last_write_val"][slot] = target
            st.state["_fx_recovery_until"][slot] = now + FX_RECOVERY_FLASH_S

        if filter_locked and wet_locked:
            tag = "filter+wet HELD"
        elif filter_locked:
            tag = "filter HELD"
        elif wet_locked:
            tag = "wet HELD"
        else:
            tag = "full reset"
        st.state["last_action"] = f"⬇ FX recovered  ({tag}, {len(writes)} writes)"

    for slot, target in writes:
        osc_set_fx_macro(slot, target)