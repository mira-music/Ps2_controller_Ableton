"""
================================================================================
  src/engine/polling.py — Background Polling + EQ Ramp Animation
================================================================================
  Two daemon threads:
    polling_loop()  — periodic queries to Ableton (BPM, transport, volume,
                      safety polls, session size detection at ~6.6 Hz)
    eq_ramp_loop()  — animates EQ value changes for double-flick actions
                      at ~60 Hz with cubic ease-out

  Tunable values from cfg:
    cfg.QUERY_DEFER_TIME        [LIVE]    deferred query delay
    cfg.FX_SAFETY_POLL_INTERVAL [LIVE]    safety re-query interval
    cfg.EQ_RAMP_MIN_MS          [LIVE]    fastest ramp duration
    cfg.EQ_RAMP_MAX_MS          [LIVE]    slowest ramp duration

  Note: EQ_RAMP_TICK_MS is read once at thread start (used in time.sleep).
        Changing it via TOML requires app restart.
================================================================================
"""

import math
import time
import threading

from src import state as st
from src.config import (
    # Architectural constant — thread tick rate read once at startup
    EQ_RAMP_TICK_MS,
)
from src.config_loader import cfg
from src.helpers import clamp
from src.osc.client import (
    osc_query_position, osc_query_fx_macro_values, osc_query_eq_macro_values,
    osc_set_eq_macro,
)
from src.log_setup import get_logger

log = get_logger(__name__)

# ═══════════════════════════════════════════════════════════════════════════
#  MODULE-LEVEL TRACKERS
# ═══════════════════════════════════════════════════════════════════════════

_last_known_track_count = 0
_last_known_scene_count = 0
_last_fx_safety_poll    = 0.0

# ═══════════════════════════════════════════════════════════════════════════
#  POLLING LOOP
# ═══════════════════════════════════════════════════════════════════════════

def polling_loop():
    """
    Background polling thread. Runs at ~6.6 Hz (150ms sleep).
    Periodically queries Ableton for state that doesn't push via listeners.

    Reads from cfg (hot-reloadable):
      cfg.QUERY_DEFER_TIME        — debounce for position queries
      cfg.FX_SAFETY_POLL_INTERVAL — re-sync FX/EQ values periodically
    """
    global _last_known_track_count, _last_known_scene_count, _last_fx_safety_poll
    from src.osc.discovery import fetch_all_names

    tick = 0

    while True:
        try:
            now = time.perf_counter()

            with st._lock:
                req = st.state["_query_requested_at"]
            if req > 0 and (now - req) >= cfg.QUERY_DEFER_TIME:
                osc_query_position()
                with st._lock:
                    st.state["_query_requested_at"] = 0.0

            if tick % 7 == 0:
                st.osc.send_message("/live/song/get/tempo",      [])
                time.sleep(0.02)
                st.osc.send_message("/live/song/get/is_playing", [])
                time.sleep(0.02)

            if tick % 5 == 0:
                with st._lock:
                    track = st.state["track"]
                st.osc.send_message("/live/track/get/volume", [track])
                time.sleep(0.02)

            if now - _last_fx_safety_poll >= cfg.FX_SAFETY_POLL_INTERVAL:
                with st._lock:
                    fx_idx = st.state["fx_track_index"]
                    eq_idx = st.state["eq_track_index"]
                if fx_idx >= 0:
                    osc_query_fx_macro_values()
                if eq_idx >= 0:
                    osc_query_eq_macro_values()
                _last_fx_safety_poll = now

            if tick % 50 == 0:
                st.osc.send_message("/live/song/get/num_tracks", [])
                st.osc.send_message("/live/song/get/num_scenes", [])
                time.sleep(0.1)

                with st._lock:
                    tc = st.state["_real_track_count"]
                    sc = st.state["_real_scene_count"]

                if tc != _last_known_track_count or sc != _last_known_scene_count:
                    if _last_known_track_count != 0:
                        log.info(
                            f"Session changed "
                            f"({tc} tracks, {sc} scenes) — rescanning…"
                        )
                        threading.Thread(
                            target=fetch_all_names, daemon=True
                        ).start()
                    _last_known_track_count = tc
                    _last_known_scene_count = sc

            tick += 1
            time.sleep(0.15)

        except Exception as e:
            log.error(f"Polling error: {e}")
            time.sleep(1.0)

# ═══════════════════════════════════════════════════════════════════════════
#  EQ RAMP ANIMATION — DEDICATED 60Hz THREAD
# ═══════════════════════════════════════════════════════════════════════════

def eq_ramp_loop():
    """
    Dedicated thread for EQ ramp animation at ~60 Hz.

    Note: EQ_RAMP_TICK_MS is read ONCE at thread start. Changing it via
    TOML requires app restart (which is why it's marked [RESTART]).
    """
    tick_interval = EQ_RAMP_TICK_MS / 1000.0

    while True:
        try:
            time.sleep(tick_interval)
            tick_eq_ramps()
        except Exception as e:
            log.error(f"EQ ramp loop error: {e}")
            time.sleep(0.5)

def tick_eq_ramps():
    """
    Update active EQ ramps at ~60 Hz.
    Cubic ease-out for smoother, click-free transitions.
    """
    with st._lock:
        active_any = any(st.state["_eq_ramp_active"])
    if not active_any:
        return

    now = time.perf_counter()
    writes = []

    with st._lock:
        for slot in range(3):
            if not st.state["_eq_ramp_active"][slot]:
                continue

            start_val   = st.state["_eq_ramp_start_val"][slot]
            target_val  = st.state["_eq_ramp_target_val"][slot]
            start_time  = st.state["_eq_ramp_start_time"][slot]
            duration    = st.state["_eq_ramp_duration"][slot]

            elapsed = now - start_time
            if elapsed >= duration:
                final_val = target_val
                st.state["_eq_ramp_active"][slot] = False
                st.state["eq_macro_values"][slot] = final_val
                writes.append((slot, final_val))
            else:
                progress = elapsed / duration
                eased = 1.0 - (1.0 - progress) ** 3
                current_val = start_val + (target_val - start_val) * eased
                st.state["eq_macro_values"][slot] = current_val
                writes.append((slot, current_val))

    for slot, val in writes:
        osc_set_eq_macro(slot, val)

def start_eq_ramp(slot, target_val, flick_duration_s):
    """
    Start an animated ramp for an EQ band.
    Duration scales linearly with flick speed:
      fast flick (30ms)  → cfg.EQ_RAMP_MIN_MS ramp
      slow flick (200ms) → cfg.EQ_RAMP_MAX_MS ramp

    Reads from cfg (hot-reloadable):
      cfg.EQ_RAMP_MIN_MS
      cfg.EQ_RAMP_MAX_MS
    """
    fd_ms = flick_duration_s * 1000.0
    fd_clamped = clamp(fd_ms, 30.0, 200.0)
    t = (fd_clamped - 30.0) / 170.0
    ramp_ms = cfg.EQ_RAMP_MIN_MS + t * (cfg.EQ_RAMP_MAX_MS - cfg.EQ_RAMP_MIN_MS)
    ramp_duration_s = ramp_ms / 1000.0

    with st._lock:
        current_val = st.state["eq_macro_values"][slot]
        st.state["_eq_ramp_active"][slot]     = True
        st.state["_eq_ramp_start_val"][slot]  = current_val
        st.state["_eq_ramp_target_val"][slot] = target_val
        st.state["_eq_ramp_start_time"][slot] = time.perf_counter()
        st.state["_eq_ramp_duration"][slot]   = ramp_duration_s