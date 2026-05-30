"""
================================================================================
  src/engine/polling.py — Polling + EQ Ramp Animation
================================================================================
  Two daemon threads:

  1. polling_loop() — ~2 Hz (was 6.6 Hz)
       Reduced polling rate now that listener-based updates handle the
       fast-changing values. Polling now serves as a safety net to catch
       any state drift from missed listener events.

  2. eq_ramp_loop() — ~60 Hz
       Animates EQ value changes triggered by double-flick actions.
       Unchanged.

  Build B revisions:
    - Polling rate dropped from 150ms to 500ms. Session metadata
      (tempo, transport, counts) is now pushed via listeners rather
      than polled. Polling continues at lower rate as a safety net.
    - Removed polling for tempo, is_playing, num_tracks, num_scenes,
      track volume from each iteration. These are now listener-driven.
      Polling now only does the deferred position query and the
      periodic FX/EQ safety re-poll.
    - Heartbeat for diagnostics health monitor added in both loops.
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
#  POLLING LOOP — ~2 Hz (reduced from 6.6 Hz)
# ═══════════════════════════════════════════════════════════════════════════

def polling_loop():
    """
    Periodic OSC operations to Ableton.

    Most session-level values (tempo, transport, track count, scene count,
    track volume) are now pushed via listeners registered in discovery.py,
    so polling no longer needs to ask for them every iteration.

    What polling still does:
      - Triggers deferred position queries (debounced after navigation)
      - Periodic FX/EQ safety re-poll to catch drift from missed listener
        events (every cfg.FX_SAFETY_POLL_INTERVAL = 2s default)
      - Detects session size changes for bookmark/group rebuilds (the
        size will come in via the num_tracks/num_scenes listeners, but
        this loop still catches the comparison)

    Sleep is now 500ms instead of 150ms. This drops the iteration rate
    from ~6.6 Hz to ~2 Hz, reducing background OSC noise dramatically
    without affecting UI responsiveness (listeners push real-time changes).
    """
    from src.osc.client import (
        osc_query_position, osc_query_fx_macro_values, osc_query_eq_macro_values,
    )
    from src.osc.discovery import rebuild_bookmarks, rebuild_groups

    last_known_track_count = -1
    last_known_scene_count = -1
    last_fx_safety_poll    = 0.0

    while True:
        # ── Diagnostics heartbeat ──────────────────────────────────────
        try:
            from src.diagnostics import record_thread_tick
            record_thread_tick("polling")
        except Exception:
            pass

        try:
            # Polling rate reduced to 2 Hz from 6.6 Hz.
            # Listener-pushed updates handle real-time state changes;
            # this loop now only does safety re-polling and deferred queries.
            time.sleep(0.5)
            now = time.perf_counter()

            with st._lock:
                requested_at = st.state["_query_requested_at"]
                tc = st.state["_real_track_count"]
                sc = st.state["_real_scene_count"]

            # Deferred position query (debounced after navigation events)
            if requested_at > 0 and (now - requested_at) >= cfg.QUERY_DEFER_TIME:
                osc_query_position()
                with st._lock:
                    st.state["_query_requested_at"] = 0.0

            # Safety re-poll FX/EQ macro values periodically.
            # This catches the case where Ableton's listener somehow
            # missed an update (rare but possible during heavy load).
            if (now - last_fx_safety_poll) >= cfg.FX_SAFETY_POLL_INTERVAL:
                osc_query_fx_macro_values()
                osc_query_eq_macro_values()
                last_fx_safety_poll = now

            # Detect session size changes
            # (will trigger from num_tracks/num_scenes listener updates)
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


# ═══════════════════════════════════════════════════════════════════════════
#  EQ RAMP ANIMATION LOOP — ~60 Hz (unchanged)
# ═══════════════════════════════════════════════════════════════════════════

def eq_ramp_loop():
    """Animates EQ ramps via cubic ease-out. Unchanged."""
    tick_s = EQ_RAMP_TICK_MS / 1000.0

    while True:
        # ── Diagnostics heartbeat ──────────────────────────────────────
        try:
            from src.diagnostics import record_thread_tick
            record_thread_tick("eq_ramp")
        except Exception:
            pass

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
                    with st._lock:
                        st.state["_eq_ramp_active"][slot] = False
                        st.state["eq_macro_values"][slot] = target
                    osc_set_eq_macro(slot, target)
                else:
                    eased = 1.0 - (1.0 - progress) ** 3
                    current_val = start_val + (target - start_val) * eased
                    with st._lock:
                        st.state["eq_macro_values"][slot] = current_val
                    osc_set_eq_macro(slot, current_val)

        except Exception as e:
            log.warning(f"EQ ramp iteration error: {e}")
            time.sleep(0.1)


# ═══════════════════════════════════════════════════════════════════════════
#  RAMP STARTER
# ═══════════════════════════════════════════════════════════════════════════

def start_eq_ramp(band, target_value, flick_duration_s):
    """Start an animated ramp for the given band. Unchanged."""
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