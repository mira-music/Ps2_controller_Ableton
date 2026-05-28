"""
================================================================================
  src/osc/client.py — OSC Send Functions
================================================================================
  All outbound OSC calls to Ableton (via AbletonOSC). Includes:
    - Transport (play, stop, position queries)
    - Track/scene navigation
    - FX rack parameter queries + writes + listeners
    - EQ rack parameter queries + writes + listeners
    - EQ track output meter listeners (v9.10)
================================================================================
"""

import time
from pythonosc import udp_client

from src import state as st
from src.config import (
    OSC_HOST, OSC_SEND_PORT,
    FX_RACK_DEVICE_INDEX, EQ_RACK_DEVICE_INDEX,
)
from src.log_setup import get_logger

log = get_logger(__name__)

# ═══════════════════════════════════════════════════════════════════════════
#  SETUP
# ═══════════════════════════════════════════════════════════════════════════

def setup_osc():
    st.osc = udp_client.SimpleUDPClient(OSC_HOST, OSC_SEND_PORT)
    log.info(f"OSC sender ready → {OSC_HOST}:{OSC_SEND_PORT}")

# ═══════════════════════════════════════════════════════════════════════════
#  NAVIGATION + VIEW
# ═══════════════════════════════════════════════════════════════════════════

def osc_select_track(track_idx):
    st.osc.send_message("/live/view/set/selected_track", [track_idx])

def osc_update_view():
    with st._lock:
        track = st.state["track"]
        scene = st.state["scene"]
    st.osc.send_message("/live/view/set/selected_track", [track])
    st.osc.send_message("/live/view/set/selected_scene", [scene])

# ═══════════════════════════════════════════════════════════════════════════
#  CLIP / SCENE / TRACK ACTIONS
# ═══════════════════════════════════════════════════════════════════════════

def osc_launch_clip():
    with st._lock:
        track = st.state["track"]
        scene = st.state["scene"]
    st.osc.send_message("/live/clip_slot/fire", [track, scene])

def osc_stop_clip():
    with st._lock:
        track = st.state["track"]
        scene = st.state["scene"]
    st.osc.send_message("/live/clip/stop", [track, scene])

def osc_stop_track():
    with st._lock:
        track = st.state["track"]
    st.osc.send_message("/live/track/stop_all_clips", [track])

def osc_launch_scene():
    with st._lock:
        scene = st.state["scene"]
    st.osc.send_message("/live/scene/fire", [scene])

def osc_arm_track():
    with st._lock:
        track = st.state["track"]
    st.osc.send_message("/live/track/set/arm", [track, 1])

def osc_set_volume(vol):
    with st._lock:
        track = st.state["track"]
    st.osc.send_message("/live/track/set/volume", [track, vol])

# ═══════════════════════════════════════════════════════════════════════════
#  TRANSPORT
# ═══════════════════════════════════════════════════════════════════════════

def osc_play():
    st.osc.send_message("/live/song/start_playing", [])

def osc_stop():
    st.osc.send_message("/live/song/stop_playing", [])

# ═══════════════════════════════════════════════════════════════════════════
#  POSITION QUERIES
# ═══════════════════════════════════════════════════════════════════════════

def osc_query_position():
    with st._lock:
        track = st.state["track"]
        scene = st.state["scene"]
    st.osc.send_message("/live/track/get/name",   [track])
    st.osc.send_message("/live/scene/get/name",   [scene])
    st.osc.send_message("/live/clip/get/name",    [track, scene])
    st.osc.send_message("/live/track/get/volume", [track])
    st.osc.send_message("/live/clip/get/color",   [track, scene])

def schedule_position_query():
    st.state["_query_requested_at"] = time.perf_counter()

def osc_query_group_previews():
    with st._lock:
        groups = list(st.state["groups"])
        gc     = st.state["group_cursor"]
    if not groups:
        return
    if gc + 1 < len(groups):
        st.osc.send_message("/live/track/get/name", [groups[gc + 1]["track_index"]])
    if gc - 1 >= 0:
        st.osc.send_message("/live/track/get/name", [groups[gc - 1]["track_index"]])

def osc_query_track_color(track_idx):
    st.osc.send_message("/live/track/get/color", [track_idx])

def osc_query_scene_color(scene_idx):
    st.osc.send_message("/live/scene/get/color", [scene_idx])

# ═══════════════════════════════════════════════════════════════════════════
#  FX RACK QUERIES
# ═══════════════════════════════════════════════════════════════════════════

def osc_query_fx_macro_names():
    with st._lock:
        track_idx = st.state["fx_track_index"]
    if track_idx < 0:
        return
    st.osc.send_message("/live/device/get/parameters/name",
                        [track_idx, FX_RACK_DEVICE_INDEX])

def osc_query_fx_macro_values():
    with st._lock:
        track_idx = st.state["fx_track_index"]
    if track_idx < 0:
        return
    st.osc.send_message("/live/device/get/parameters/value",
                        [track_idx, FX_RACK_DEVICE_INDEX])

def osc_query_fx_macro_mins():
    with st._lock:
        track_idx = st.state["fx_track_index"]
    if track_idx < 0:
        return
    st.osc.send_message("/live/device/get/parameters/min",
                        [track_idx, FX_RACK_DEVICE_INDEX])

def osc_query_fx_macro_maxs():
    with st._lock:
        track_idx = st.state["fx_track_index"]
    if track_idx < 0:
        return
    st.osc.send_message("/live/device/get/parameters/max",
                        [track_idx, FX_RACK_DEVICE_INDEX])

def osc_query_fx_macro_value_strings():
    with st._lock:
        track_idx = st.state["fx_track_index"]
        param_ids = list(st.state["fx_macro_param_ids"])
        ready     = st.state["fx_ready"]
    if track_idx < 0 or not ready:
        return
    for slot, pid in enumerate(param_ids):
        with st._lock:
            if not st.state["fx_macro_names"][slot]:
                continue
        st.osc.send_message("/live/device/get/parameter/value_string",
                            [track_idx, FX_RACK_DEVICE_INDEX, pid])

# ═══════════════════════════════════════════════════════════════════════════
#  FX LISTENERS
# ═══════════════════════════════════════════════════════════════════════════

def osc_register_fx_listeners():
    with st._lock:
        track_idx = st.state["fx_track_index"]
        param_ids = list(st.state["fx_macro_param_ids"])
        names     = list(st.state["fx_macro_names"])
    if track_idx < 0:
        return
    count = 0
    for slot, (pid, name) in enumerate(zip(param_ids, names)):
        if not name:
            continue
        st.osc.send_message("/live/device/start_listen/parameter/value",
                            [track_idx, FX_RACK_DEVICE_INDEX, pid])
        st.osc.send_message("/live/device/start_listen/parameter/value_string",
                            [track_idx, FX_RACK_DEVICE_INDEX, pid])
        count += 2
    st.FX_LISTEN_REGISTERED = True
    log.info(f"FX listeners registered: {count} listeners armed")

def osc_stop_fx_listeners():
    with st._lock:
        track_idx = st.state["fx_track_index"]
        param_ids = list(st.state["fx_macro_param_ids"])
        names     = list(st.state["fx_macro_names"])
    if track_idx < 0 or not st.FX_LISTEN_REGISTERED:
        return
    for slot, (pid, name) in enumerate(zip(param_ids, names)):
        if not name:
            continue
        try:
            st.osc.send_message("/live/device/stop_listen/parameter/value",
                                [track_idx, FX_RACK_DEVICE_INDEX, pid])
            st.osc.send_message("/live/device/stop_listen/parameter/value_string",
                                [track_idx, FX_RACK_DEVICE_INDEX, pid])
        except Exception:
            pass
    st.FX_LISTEN_REGISTERED = False
    log.info("FX listeners stopped")

# ═══════════════════════════════════════════════════════════════════════════
#  FX WRITES
# ═══════════════════════════════════════════════════════════════════════════

def osc_set_fx_macro(slot, value):
    with st._lock:
        track_idx = st.state["fx_track_index"]
        param_ids = list(st.state["fx_macro_param_ids"])
    if track_idx < 0:
        return
    if slot < 0 or slot >= len(param_ids):
        return
    param_id = param_ids[slot]
    st.osc.send_message("/live/device/set/parameter/value",
                        [track_idx, FX_RACK_DEVICE_INDEX, param_id, float(value)])

# ═══════════════════════════════════════════════════════════════════════════
#  EQ RACK QUERIES
# ═══════════════════════════════════════════════════════════════════════════

def osc_query_eq_macro_names():
    with st._lock:
        track_idx = st.state["eq_track_index"]
    if track_idx < 0:
        return
    st.osc.send_message("/live/device/get/parameters/name",
                        [track_idx, EQ_RACK_DEVICE_INDEX])

def osc_query_eq_macro_values():
    with st._lock:
        track_idx = st.state["eq_track_index"]
    if track_idx < 0:
        return
    st.osc.send_message("/live/device/get/parameters/value",
                        [track_idx, EQ_RACK_DEVICE_INDEX])

def osc_query_eq_macro_mins():
    with st._lock:
        track_idx = st.state["eq_track_index"]
    if track_idx < 0:
        return
    st.osc.send_message("/live/device/get/parameters/min",
                        [track_idx, EQ_RACK_DEVICE_INDEX])

def osc_query_eq_macro_maxs():
    with st._lock:
        track_idx = st.state["eq_track_index"]
    if track_idx < 0:
        return
    st.osc.send_message("/live/device/get/parameters/max",
                        [track_idx, EQ_RACK_DEVICE_INDEX])

def osc_query_eq_macro_value_strings():
    with st._lock:
        track_idx = st.state["eq_track_index"]
        param_ids = list(st.state["eq_macro_param_ids"])
        ready     = st.state["eq_ready"]
    if track_idx < 0 or not ready:
        return
    for slot, pid in enumerate(param_ids):
        with st._lock:
            if not st.state["eq_macro_names"][slot]:
                continue
        st.osc.send_message("/live/device/get/parameter/value_string",
                            [track_idx, EQ_RACK_DEVICE_INDEX, pid])

# ═══════════════════════════════════════════════════════════════════════════
#  EQ LISTENERS
# ═══════════════════════════════════════════════════════════════════════════

def osc_register_eq_listeners():
    with st._lock:
        track_idx = st.state["eq_track_index"]
        param_ids = list(st.state["eq_macro_param_ids"])
        names     = list(st.state["eq_macro_names"])
    if track_idx < 0:
        return
    count = 0
    for slot, (pid, name) in enumerate(zip(param_ids, names)):
        if not name:
            continue
        st.osc.send_message("/live/device/start_listen/parameter/value",
                            [track_idx, EQ_RACK_DEVICE_INDEX, pid])
        st.osc.send_message("/live/device/start_listen/parameter/value_string",
                            [track_idx, EQ_RACK_DEVICE_INDEX, pid])
        count += 2
    st.EQ_LISTEN_REGISTERED = True
    log.info(f"EQ listeners registered: {count} listeners armed")

def osc_stop_eq_listeners():
    with st._lock:
        track_idx = st.state["eq_track_index"]
        param_ids = list(st.state["eq_macro_param_ids"])
        names     = list(st.state["eq_macro_names"])
    if track_idx < 0 or not st.EQ_LISTEN_REGISTERED:
        return
    for slot, (pid, name) in enumerate(zip(param_ids, names)):
        if not name:
            continue
        try:
            st.osc.send_message("/live/device/stop_listen/parameter/value",
                                [track_idx, EQ_RACK_DEVICE_INDEX, pid])
            st.osc.send_message("/live/device/stop_listen/parameter/value_string",
                                [track_idx, EQ_RACK_DEVICE_INDEX, pid])
        except Exception:
            pass
    st.EQ_LISTEN_REGISTERED = False
    log.info("EQ listeners stopped")

# ═══════════════════════════════════════════════════════════════════════════
#  EQ WRITES
# ═══════════════════════════════════════════════════════════════════════════

def osc_set_eq_macro(slot, value):
    with st._lock:
        track_idx = st.state["eq_track_index"]
        param_ids = list(st.state["eq_macro_param_ids"])
    if track_idx < 0:
        return
    if slot < 0 or slot >= len(param_ids):
        return
    param_id = param_ids[slot]
    st.osc.send_message("/live/device/set/parameter/value",
                        [track_idx, EQ_RACK_DEVICE_INDEX, param_id, float(value)])

# ═══════════════════════════════════════════════════════════════════════════
#  EQ TRACK OUTPUT METER (DJM channel meter)
# ═══════════════════════════════════════════════════════════════════════════

def osc_register_eq_meter_listener():
    """Register listeners for EQ track output meter (L+R audio peak)."""
    with st._lock:
        track_idx = st.state["eq_track_index"]
    if track_idx < 0:
        return
    try:
        st.osc.send_message("/live/track/start_listen/output_meter_left",  [track_idx])
        st.osc.send_message("/live/track/start_listen/output_meter_right", [track_idx])
        log.info(f"EQ meter listeners armed on track {track_idx}")
    except Exception as e:
        log.warning(f"Meter listener register failed: {e}")

def osc_stop_eq_meter_listener():
    with st._lock:
        track_idx = st.state["eq_track_index"]
    if track_idx < 0:
        return
    try:
        st.osc.send_message("/live/track/stop_listen/output_meter_left",  [track_idx])
        st.osc.send_message("/live/track/stop_listen/output_meter_right", [track_idx])
    except Exception:
        pass