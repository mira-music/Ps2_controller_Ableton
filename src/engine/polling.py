"""
================================================================================
  src/engine/polling.py — Polling + EQ Ramp Animation
================================================================================
"""

import time
import threading
from src import state as st
from src.config import (
    EQ_RAMP_TICK_MS,
    EQ_MACRO_COUNT,
)
from src.config_loader import cfg
from src.helpers import clamp
from src.osc.client import osc_set_eq_macro
from src.log_setup import get_logger

log = get_logger(__name__)


def polling_loop():
    """
    Periodic OSC queries to Ableton (~6.6 Hz).

    Session size change detection uses >= 0 as the "first poll done"
    sentinel (was > 0, which missed the empty → populated transition).
    """
    from src.osc.client import (
        osc_query_position, osc_query_fx_macro_values, osc_query_eq_macro_values,
    )
    from src.osc.discovery import rebuild_bookmarks, rebuild_groups

    # -1 = not yet seen any count from Ableton
    last_known_track_count = -1
    last_known_scene_count = -1
    last_fx_safety_poll    = 0.0

    while True:
        try:
            time.sleep(0.15)
            now = time.perf_counter()

            with st._lock:
                requested_at = st.state["_query_requested_at"]
                tc = st.state["_real_track_count"]
                sc = st.state["_real_scene_count"]

            st.osc.send_message("/live/song/get/tempo", [])
            st.osc.send_message("/live/song/get/is_playing", [])
            st.osc.send_message("/live/song/get/num_tracks", [])
            st.osc.send_message("/live/song/get/num_scenes", [])

            with st._lock:
                track_idx = st.state["track"]
            st.osc.send_message("/live/track/get/volume", [track_idx])

            if requested_at > 0 and (now - requested_at) >= cfg.QUERY_DEFER_TIME:
                osc_query_position()
                with st._lock:
                    st.state["_query_requested_at"] = 0.0

            if (now - last_fx_safety_poll) >= cfg.FX_SAFETY_POLL_INTERVAL:
                osc_query_fx_macro_values()
                osc_query_eq_macro_values()
                last_fx_safety_poll = now

            # Detect session size changes.
            # Condition: >= 0 (not -1) means we've received at least one
            # count response from Ableton. This correctly catches the
            # empty (0 tracks) → populated transition that > 0 missed.
            if tc != last_known_track_count or sc != last_known_scene_count:
                if last_known_track_count >= 0 or last_known_scene_count >= 0:
                    log.info(f"Session size changed: {tc} tracks, {sc} scenes")
                    rebuild_bookmarks()
                    rebuild_groups()
                last_known_track_count = tc
                last_known_scene_count = sc

        except Exception as e:
            log.warning(f"Polling iteration error: {e}")
            time.sleep(0.5)


def eq_ramp_loop():
    """
    Background thread animating active EQ value ramps at ~60 Hz.
    Cubic ease-out curve. On completion, writes target value exactly once
    to prevent a race where the interpolated value and the target value
    are both written to state in the same frame.
    """
    tick_s = EQ_RAMP_TICK_MS / 1000.0

    while True:
        try:
            time.sleep(tick_s)
            now = time.perf_counter()

            with st._lock:
                active_flags = list(st.state["_eq_ramp_active"])

            for slot in range(EQ_MACRO_COUNT):
                if not active_flags[slot]:
                    continue

                with st._lock:
                    start_val = st.state["_eq_ramp_start_val"][slot]
                    target    = st.state["_eq_ramp_target_val"][slot]
                    start_t   = st.state["_eq_ramp_start_time"][slot]
                    duration  = st.state["_eq_ramp_duration"][slot]

                if duration <= 0:
                    with st._lock:
                        st.state["_eq_ramp_active"][slot] = False
                    continue

                elapsed = now - start_t
                progress = clamp(elapsed / duration, 0.0, 1.0)

                if progress >= 1.0:
                    # Completion: write target exactly once, then deactivate.
                    # This avoids a two-write race (interpolated then target)
                    # that could let the controller thread read a non-final value.
                    with st._lock:
                        st.state["_eq_ramp_active"][slot] = False
                        st.state["eq_macro_values"][slot] = target
                    osc_set_eq_macro(slot, target)
                else:
                    # Cubic ease-out interpolation
                    eased = 1.0 - (1.0 - progress) ** 3
                    current_val = start_val + (target - start_val) * eased

                    with st._lock:
                        st.state["eq_macro_values"][slot] = current_val

                    osc_set_eq_macro(slot, current_val)

        except Exception as e:
            log.warning(f"EQ ramp iteration error: {e}")
            time.sleep(0.1)


def start_eq_ramp(band, target_value, flick_duration_s):
    """
    Start an animated ramp for the given band.
    Ramp duration scales linearly with flick speed.
    """
    flick_ms = clamp(flick_duration_s * 1000.0, 30.0, 200.0)
    fraction = (flick_ms - 30.0) / (200.0 - 30.0)
    fraction = clamp(fraction, 0.0, 1.0)
    ramp_ms = cfg.EQ_RAMP_MIN_MS + fraction * (cfg.EQ_RAMP_MAX_MS - cfg.EQ_RAMP_MIN_MS)
    ramp_s = ramp_ms / 1000.0

    now = time.perf_counter()
    with st._lock:
        start_val = st.state["eq_macro_values"][band]
        st.state["_eq_ramp_active"][band]     = True
        st.state["_eq_ramp_start_val"][band]  = start_val
        st.state["_eq_ramp_target_val"][band] = target_value
        st.state["_eq_ramp_start_time"][band] = now
        st.state["_eq_ramp_duration"][band]   = ramp_s