"""
================================================================================
  src/engine/polling.py — Polling + EQ Ramp Animation
================================================================================
  Two daemon threads:

  1. polling_loop() — ~6.6 Hz
       Periodic OSC queries (BPM, transport, volume, FX/EQ safety polls).
       Detects session size changes and triggers rebuild.

  2. eq_ramp_loop() — ~60 Hz
       Animates EQ value changes triggered by double-flick actions
       (kill, normalize, boost, restore). Cubic ease-out curve.

  Build B: ramp arrays now sized for 4 macros (Low, Mid, High, TRIM).
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


# ═══════════════════════════════════════════════════════════════════════════
#  POLLING LOOP
# ═══════════════════════════════════════════════════════════════════════════

def polling_loop():
    """
    Periodic OSC queries to Ableton.
    - BPM, transport state: every poll (~150 ms)
    - Track volume: every poll
    - FX/EQ safety polls: every cfg.FX_SAFETY_POLL_INTERVAL (default 2s)
    - Session size: every poll (cheap)

    Defers position queries via _query_requested_at to debounce navigation.
    """
    from src.osc.client import (
        osc_query_position, osc_query_fx_macro_values, osc_query_eq_macro_values,
    )
    from src.osc.discovery import rebuild_bookmarks, rebuild_groups

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

            # Always poll BPM + transport + volume + session counts
            st.osc.send_message("/live/song/get/tempo", [])
            st.osc.send_message("/live/song/get/is_playing", [])
            st.osc.send_message("/live/song/get/num_tracks", [])
            st.osc.send_message("/live/song/get/num_scenes", [])

            with st._lock:
                track_idx = st.state["track"]
            st.osc.send_message("/live/track/get/volume", [track_idx])

            # Deferred position query (debounced after navigation)
            if requested_at > 0 and (now - requested_at) >= cfg.QUERY_DEFER_TIME:
                osc_query_position()
                with st._lock:
                    st.state["_query_requested_at"] = 0.0

            # Safety re-poll FX/EQ macro values (catches manual Ableton changes)
            if (now - last_fx_safety_poll) >= cfg.FX_SAFETY_POLL_INTERVAL:
                osc_query_fx_macro_values()
                osc_query_eq_macro_values()
                last_fx_safety_poll = now

            # Detect session size changes
            if tc != last_known_track_count or sc != last_known_scene_count:
                if last_known_track_count > 0 or last_known_scene_count > 0:
                    log.info(f"Session size changed: {tc} tracks, {sc} scenes")
                    # Rebuild bookmarks/groups in case track/scene order changed
                    rebuild_bookmarks()
                    rebuild_groups()
                last_known_track_count = tc
                last_known_scene_count = sc

        except Exception as e:
            log.warning(f"Polling iteration error: {e}")
            time.sleep(0.5)


# ═══════════════════════════════════════════════════════════════════════════
#  EQ RAMP ANIMATION LOOP
# ═══════════════════════════════════════════════════════════════════════════

def eq_ramp_loop():
    """
    Background thread that animates active EQ value ramps.
    Runs at ~60 Hz (EQ_RAMP_TICK_MS = 16ms).

    For each active ramp:
      - Computes progress (0.0 → 1.0) based on elapsed time
      - Applies cubic ease-out: eased = 1 - (1 - progress)^3
      - Interpolates start → target by eased fraction
      - Writes to state + sends OSC

    When progress reaches 1.0, the ramp is marked inactive.

    Build B: iterates over EQ_MACRO_COUNT slots (4 instead of 3).
    """
    tick_s = EQ_RAMP_TICK_MS / 1000.0

    while True:
        try:
            time.sleep(tick_s)
            now = time.perf_counter()

            # Snapshot ramp state under lock
            with st._lock:
                active_flags = list(st.state["_eq_ramp_active"])

            # Process each active ramp
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

                # Cubic ease-out
                eased = 1.0 - (1.0 - progress) ** 3
                current_val = start_val + (target - start_val) * eased

                # Write to state + OSC
                with st._lock:
                    st.state["eq_macro_values"][slot] = current_val

                osc_set_eq_macro(slot, current_val)

                # End ramp on completion
                if progress >= 1.0:
                    with st._lock:
                        st.state["_eq_ramp_active"][slot] = False
                        st.state["eq_macro_values"][slot] = target
                    osc_set_eq_macro(slot, target)

        except Exception as e:
            log.warning(f"EQ ramp iteration error: {e}")
            time.sleep(0.1)


# ═══════════════════════════════════════════════════════════════════════════
#  RAMP STARTER (called from engine/eq.py kill/normalize/boost/restore actions)
# ═══════════════════════════════════════════════════════════════════════════

def start_eq_ramp(band, target_value, flick_duration_s):
    """
    Start an animated ramp for the given band.

    Ramp duration scales with how fast you flicked:
      Fast flick (30 ms between extremes) → cfg.EQ_RAMP_MIN_MS ramp (snappy)
      Slow flick (200 ms between extremes) → cfg.EQ_RAMP_MAX_MS ramp (smooth)
      Linear interpolation in between.
    """
    # Clamp flick duration to a sensible range
    flick_ms = clamp(flick_duration_s * 1000.0, 30.0, 200.0)

    # Linear interpolation: flick_ms 30→200 maps to ramp MIN→MAX
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