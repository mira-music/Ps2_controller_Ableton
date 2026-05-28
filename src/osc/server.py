"""
================================================================================
  src/osc/server.py — OSC Receive Handlers + Dispatcher
================================================================================
  All inbound OSC handlers (on_*). Dispatcher mapping in start_osc_server().
  Combined param dispatchers route by track_id to FX or EQ subsystem.
================================================================================
"""

import time
from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import ThreadingOSCUDPServer

from src import state as st
from src.config import (
    OSC_HOST, OSC_RECEIVE_PORT,
    FX_RACK_DEVICE_INDEX, EQ_RACK_DEVICE_INDEX,
    FX_MACRO_NAMES_EXPECTED, EQ_MACRO_NAMES_EXPECTED,
    EQ_NEUTRAL_MACRO,
    VOL_MIN, VOL_MAX,
    ABLETON_ERROR_THROTTLE,
)
from src.helpers import clamp
from src.log_setup import get_logger

log = get_logger(__name__)

# ═══════════════════════════════════════════════════════════════════════════
#  TRANSPORT + SESSION HANDLERS
# ═══════════════════════════════════════════════════════════════════════════

def on_bpm(address, *args):
    if args:
        with st._lock:
            st.ableton["bpm"] = round(float(args[0]), 1)

def on_is_playing(address, *args):
    if args:
        with st._lock:
            st.ableton["is_playing"] = bool(args[0])

def on_track_name(address, *args):
    if len(args) < 2:
        return
    try:
        idx  = int(args[0])
        name = str(args[1]).strip() if args[1] else "—"
    except (ValueError, IndexError):
        return
    with st._lock:
        if idx == st.state["track"]:
            st.ableton["track_name"] = name or "—"
        groups = st.state["groups"]
        gc     = st.state["group_cursor"]
        if groups:
            next_idx = groups[gc + 1]["track_index"] if gc + 1 < len(groups) else -1
            prev_idx = groups[gc - 1]["track_index"] if gc - 1 >= 0 else -1
            if idx == next_idx:
                st.state["next_group_name"] = groups[gc + 1]["name"][:14]
            elif idx == prev_idx:
                st.state["prev_group_name"] = groups[gc - 1]["name"][:14]
        if 0 <= idx < len(st.ableton["all_track_names"]):
            st.ableton["all_track_names"][idx] = name

def on_scene_name(address, *args):
    if len(args) < 2:
        return
    try:
        idx  = int(args[0])
        name = str(args[1]).strip() if args[1] else ""
    except (ValueError, IndexError):
        return
    with st._lock:
        if idx == st.state["scene"]:
            st.ableton["scene_name"] = name or "—"
        if 0 <= idx < len(st.ableton["all_scene_names"]):
            st.ableton["all_scene_names"][idx] = name

def on_track_color(address, *args):
    if len(args) < 2:
        return
    try:
        idx       = int(args[0])
        color_int = int(args[1])
    except (ValueError, IndexError):
        return
    with st._lock:
        while len(st.ableton["all_track_colors"]) <= idx:
            st.ableton["all_track_colors"].append(0)
        st.ableton["all_track_colors"][idx] = color_int
        if idx == st.state["fx_track_index"]:
            st.ableton["fx_track_color"] = color_int
        if idx == st.state["eq_track_index"]:
            st.ableton["eq_track_color"] = color_int

def on_scene_color(address, *args):
    if len(args) < 2:
        return
    try:
        idx       = int(args[0])
        color_int = int(args[1])
    except (ValueError, IndexError):
        return
    with st._lock:
        while len(st.ableton["all_scene_colors"]) <= idx:
            st.ableton["all_scene_colors"].append(0)
        st.ableton["all_scene_colors"][idx] = color_int

def on_clip_color(address, *args):
    if len(args) < 3:
        return
    try:
        track_idx = int(args[0])
        scene_idx = int(args[1])
        color_int = int(args[2])
    except (ValueError, IndexError):
        return
    with st._lock:
        if track_idx == st.state["track"] and scene_idx == st.state["scene"]:
            st.ableton["clip_color"] = color_int

def on_track_volume(address, *args):
    if args:
        with st._lock:
            st.ableton["track_volume"] = clamp(float(args[-1]), VOL_MIN, VOL_MAX)

def on_track_meter_left(address, *args):
    """v9.10: EQ track output meter (left channel peak, 0-1)."""
    if len(args) < 2:
        return
    try:
        track_id = int(args[0])
        value    = float(args[1])
    except (ValueError, IndexError):
        return
    with st._lock:
        if track_id == st.state["eq_track_index"]:
            st.state["eq_meter_left"] = clamp(value, 0.0, 1.0)

def on_track_meter_right(address, *args):
    """v9.10: EQ track output meter (right channel peak, 0-1)."""
    if len(args) < 2:
        return
    try:
        track_id = int(args[0])
        value    = float(args[1])
    except (ValueError, IndexError):
        return
    with st._lock:
        if track_id == st.state["eq_track_index"]:
            st.state["eq_meter_right"] = clamp(value, 0.0, 1.0)

def on_clip_name(address, *args):
    with st._lock:
        if not args:
            st.ableton["clip_name"]  = "— empty —"
            st.ableton["clip_empty"] = True
            return
        name = str(args[-1]).strip()
        if name in ("", "None"):
            st.ableton["clip_name"]  = "— empty —"
            st.ableton["clip_empty"] = True
        else:
            st.ableton["clip_name"]  = name
            st.ableton["clip_empty"] = False

def on_scene_count(address, *args):
    if args:
        with st._lock:
            st.state["_real_scene_count"]    = int(args[0])
            st.ableton["all_scene_names"]    = [""] * st.state["_real_scene_count"]
            st.ableton["all_scene_colors"]   = [0]  * st.state["_real_scene_count"]

def on_track_count(address, *args):
    if args:
        with st._lock:
            st.state["_real_track_count"]    = int(args[0])
            st.ableton["all_track_names"]    = [""] * st.state["_real_track_count"]
            st.ableton["all_track_colors"]   = [0]  * st.state["_real_track_count"]

# ─── Known harmless Ableton error patterns ───
# These happen when navigating into empty clip slots / unassigned tracks
# and don't indicate a real problem. We downgrade them to DEBUG so they
# don't clutter normal logs, but are still recorded if DEBUG is enabled.
_IGNORED_ABLETON_ERROR_PATTERNS = (
    "'NoneType' object has no attribute 'name'",
    "'NoneType' object has no attribute 'color'",
    "'NoneType' object has no attribute 'clip'",
    "'NoneType' object has no attribute 'is_playing'",
    "'NoneType' object has no attribute 'value'",
)

def on_ableton_error(address, *args):
    if not args:
        return
    msg = str(args[0])
    now = time.perf_counter()

    # Throttle exact-duplicate messages
    if (msg == st._last_ableton_error_msg and
            (now - st._last_ableton_error_time) < ABLETON_ERROR_THROTTLE):
        return
    st._last_ableton_error_msg  = msg
    st._last_ableton_error_time = now

    # Filter known-benign patterns (empty slots, etc.) to DEBUG level
    for ignored in _IGNORED_ABLETON_ERROR_PATTERNS:
        if ignored in msg:
            log.debug(f"Ableton (benign): {msg}")
            return

    # Anything else is a real warning
    log.warning(f"Ableton error: {msg}")

# ═══════════════════════════════════════════════════════════════════════════
#  PARAM LIST EXTRACTORS
# ═══════════════════════════════════════════════════════════════════════════

def _extract_fx_param_list(args):
    if len(args) < 3:
        return None
    try:
        track_id  = int(args[0])
        device_id = int(args[1])
    except (ValueError, IndexError):
        return None
    with st._lock:
        if track_id != st.state["fx_track_index"]:
            return None
        if device_id != FX_RACK_DEVICE_INDEX:
            return None
    return list(args[2:])

def _extract_eq_param_list(args):
    if len(args) < 3:
        return None
    try:
        track_id  = int(args[0])
        device_id = int(args[1])
    except (ValueError, IndexError):
        return None
    with st._lock:
        if track_id != st.state["eq_track_index"]:
            return None
        if device_id != EQ_RACK_DEVICE_INDEX:
            return None
    return list(args[2:])

# ═══════════════════════════════════════════════════════════════════════════
#  FX MACRO HANDLERS
# ═══════════════════════════════════════════════════════════════════════════

def on_fx_macro_names(address, *args):
    params = _extract_fx_param_list(args)
    if params is None:
        return
    all_names   = [str(p) for p in params]
    found_names = [""] * 8
    found_ids   = [0]  * 8
    found_count = 0
    for slot, expected in enumerate(FX_MACRO_NAMES_EXPECTED):
        for idx, n in enumerate(all_names):
            if n == expected:
                found_names[slot] = n
                found_ids[slot]   = idx
                found_count      += 1
                break
    with st._lock:
        st.state["fx_macro_names"]     = found_names
        st.state["fx_macro_param_ids"] = found_ids
    log.info(f"FX macros mapped: {found_count}/8")
    for i, (n, pid) in enumerate(zip(found_names, found_ids)):
        marker = "" if n else "  ⚠ NOT FOUND"
        log.info(f"  slot {i}: param[{pid}] = {n!r}{marker}")

def on_fx_macro_values(address, *args):
    params = _extract_fx_param_list(args)
    if params is None:
        return
    try:
        all_values = [float(p) for p in params]
    except (ValueError, TypeError):
        return
    with st._lock:
        param_ids  = list(st.state["fx_macro_param_ids"])
        new_values = [
            all_values[pid] if 0 <= pid < len(all_values) else 0.0
            for pid in param_ids
        ]
        st.state["fx_macro_values"] = new_values
        if not st.state["fx_ready"] and any(st.state["fx_macro_names"]):
            st.state["fx_ready"] = True
        if not st.state["fx_baseline_ready"] and st.state["fx_ready"]:
            st.state["fx_baseline"]             = list(new_values)
            st.state["fx_baseline_ready"]       = True
            st.state["fx_baseline_captured_at"] = time.perf_counter()
            st.state["last_action"]             = "✓ Baseline auto-captured on startup"
            log.info(f"Baseline auto-captured: {[round(v,2) for v in new_values]}")

def on_fx_macro_mins(address, *args):
    params = _extract_fx_param_list(args)
    if params is None:
        return
    try:
        all_mins = [float(p) for p in params]
    except (ValueError, TypeError):
        return
    with st._lock:
        param_ids = list(st.state["fx_macro_param_ids"])
        st.state["fx_macro_mins"] = [
            all_mins[pid] if 0 <= pid < len(all_mins) else 0.0
            for pid in param_ids
        ]

def on_fx_macro_maxs(address, *args):
    params = _extract_fx_param_list(args)
    if params is None:
        return
    try:
        all_maxs = [float(p) for p in params]
    except (ValueError, TypeError):
        return
    with st._lock:
        param_ids = list(st.state["fx_macro_param_ids"])
        st.state["fx_macro_maxs"] = [
            all_maxs[pid] if 0 <= pid < len(all_maxs) else 1.0
            for pid in param_ids
        ]

def on_fx_param_value(address, *args):
    if len(args) < 4:
        return
    try:
        track_id  = int(args[0])
        device_id = int(args[1])
        param_id  = int(args[2])
        value     = float(args[3])
    except (ValueError, IndexError):
        return
    with st._lock:
        fx_track  = st.state["fx_track_index"]
        eq_track  = st.state["eq_track_index"]
    if track_id == fx_track and device_id == FX_RACK_DEVICE_INDEX:
        with st._lock:
            slot_match = -1
            for slot, pid in enumerate(st.state["fx_macro_param_ids"]):
                if pid == param_id and st.state["fx_macro_names"][slot]:
                    slot_match = slot
                    break
            if slot_match < 0:
                return
            st.state["fx_macro_values"][slot_match] = value
            if not st.state["fx_ready"]:
                st.state["fx_ready"] = True
    elif track_id == eq_track and device_id == EQ_RACK_DEVICE_INDEX:
        with st._lock:
            slot_match = -1
            for slot, pid in enumerate(st.state["eq_macro_param_ids"]):
                if pid == param_id and st.state["eq_macro_names"][slot]:
                    slot_match = slot
                    break
            if slot_match < 0:
                return
            st.state["eq_macro_values"][slot_match] = value
            if not st.state["eq_ready"]:
                st.state["eq_ready"] = True

def on_fx_param_value_string(address, *args):
    if len(args) < 4:
        return
    try:
        track_id  = int(args[0])
        device_id = int(args[1])
        param_id  = int(args[2])
        value_str = str(args[3])
    except (ValueError, IndexError):
        return
    with st._lock:
        fx_track  = st.state["fx_track_index"]
        eq_track  = st.state["eq_track_index"]
    if track_id == fx_track and device_id == FX_RACK_DEVICE_INDEX:
        with st._lock:
            for slot, pid in enumerate(st.state["fx_macro_param_ids"]):
                if pid == param_id and st.state["fx_macro_names"][slot]:
                    st.state["fx_macro_value_strings"][slot] = value_str
                    return
    elif track_id == eq_track and device_id == EQ_RACK_DEVICE_INDEX:
        with st._lock:
            for slot, pid in enumerate(st.state["eq_macro_param_ids"]):
                if pid == param_id and st.state["eq_macro_names"][slot]:
                    st.state["eq_macro_value_strings"][slot] = value_str
                    return

# ═══════════════════════════════════════════════════════════════════════════
#  EQ MACRO HANDLERS
# ═══════════════════════════════════════════════════════════════════════════

def on_eq_macro_names(address, *args):
    params = _extract_eq_param_list(args)
    if params is None:
        return
    all_names   = [str(p) for p in params]
    found_names = [""] * 3
    found_ids   = [0]  * 3
    found_count = 0
    for slot, expected in enumerate(EQ_MACRO_NAMES_EXPECTED):
        for idx, n in enumerate(all_names):
            if n == expected:
                found_names[slot] = n
                found_ids[slot]   = idx
                found_count      += 1
                break
    with st._lock:
        st.state["eq_macro_names"]     = found_names
        st.state["eq_macro_param_ids"] = found_ids
    log.info(f"EQ macros mapped: {found_count}/3")
    for i, (n, pid) in enumerate(zip(found_names, found_ids)):
        marker = "" if n else "  ⚠ NOT FOUND"
        log.info(f"  slot {i}: param[{pid}] = {n!r}{marker}")

def on_eq_macro_values(address, *args):
    params = _extract_eq_param_list(args)
    if params is None:
        return
    try:
        all_values = [float(p) for p in params]
    except (ValueError, TypeError):
        return
    with st._lock:
        param_ids  = list(st.state["eq_macro_param_ids"])
        new_values = [
            all_values[pid] if 0 <= pid < len(all_values) else EQ_NEUTRAL_MACRO
            for pid in param_ids
        ]
        st.state["eq_macro_values"] = new_values
        if not st.state["eq_ready"] and any(st.state["eq_macro_names"]):
            st.state["eq_ready"] = True

def on_eq_macro_mins(address, *args):
    params = _extract_eq_param_list(args)
    if params is None:
        return
    try:
        all_mins = [float(p) for p in params]
    except (ValueError, TypeError):
        return
    with st._lock:
        param_ids = list(st.state["eq_macro_param_ids"])
        st.state["eq_macro_mins"] = [
            all_mins[pid] if 0 <= pid < len(all_mins) else 0.0
            for pid in param_ids
        ]

def on_eq_macro_maxs(address, *args):
    params = _extract_eq_param_list(args)
    if params is None:
        return
    try:
        all_maxs = [float(p) for p in params]
    except (ValueError, TypeError):
        return
    with st._lock:
        param_ids = list(st.state["eq_macro_param_ids"])
        st.state["eq_macro_maxs"] = [
            all_maxs[pid] if 0 <= pid < len(all_maxs) else 127.0
            for pid in param_ids
        ]

# ═══════════════════════════════════════════════════════════════════════════
#  COMBINED PARAM DISPATCHERS (route by track_id)
# ═══════════════════════════════════════════════════════════════════════════

def on_combined_param_names(address, *args):
    if len(args) < 3:
        return
    try:
        track_id = int(args[0])
    except (ValueError, IndexError):
        return
    with st._lock:
        fx_track = st.state["fx_track_index"]
        eq_track = st.state["eq_track_index"]
    if track_id == fx_track:
        on_fx_macro_names(address, *args)
    elif track_id == eq_track:
        on_eq_macro_names(address, *args)

def on_combined_param_values(address, *args):
    if len(args) < 3:
        return
    try:
        track_id = int(args[0])
    except (ValueError, IndexError):
        return
    with st._lock:
        fx_track = st.state["fx_track_index"]
        eq_track = st.state["eq_track_index"]
    if track_id == fx_track:
        on_fx_macro_values(address, *args)
    elif track_id == eq_track:
        on_eq_macro_values(address, *args)

def on_combined_param_mins(address, *args):
    if len(args) < 3:
        return
    try:
        track_id = int(args[0])
    except (ValueError, IndexError):
        return
    with st._lock:
        fx_track = st.state["fx_track_index"]
        eq_track = st.state["eq_track_index"]
    if track_id == fx_track:
        on_fx_macro_mins(address, *args)
    elif track_id == eq_track:
        on_eq_macro_mins(address, *args)

def on_combined_param_maxs(address, *args):
    if len(args) < 3:
        return
    try:
        track_id = int(args[0])
    except (ValueError, IndexError):
        return
    with st._lock:
        fx_track = st.state["fx_track_index"]
        eq_track = st.state["eq_track_index"]
    if track_id == fx_track:
        on_fx_macro_maxs(address, *args)
    elif track_id == eq_track:
        on_eq_macro_maxs(address, *args)

# ═══════════════════════════════════════════════════════════════════════════
#  OSC SERVER STARTUP
# ═══════════════════════════════════════════════════════════════════════════

def start_osc_server():
    d = Dispatcher()
    d.map("/live/song/get/tempo",                     on_bpm)
    d.map("/live/song/get/is_playing",                on_is_playing)
    d.map("/live/track/get/name",                     on_track_name)
    d.map("/live/track/get/color",                    on_track_color)
    d.map("/live/scene/get/name",                     on_scene_name)
    d.map("/live/scene/get/color",                    on_scene_color)
    d.map("/live/track/get/volume",                   on_track_volume)
    d.map("/live/clip/get/name",                      on_clip_name)
    d.map("/live/clip/get/color",                     on_clip_color)
    d.map("/live/song/get/num_scenes",                on_scene_count)
    d.map("/live/song/get/num_tracks",                on_track_count)
    d.map("/live/device/get/parameters/name",         on_combined_param_names)
    d.map("/live/device/get/parameters/value",        on_combined_param_values)
    d.map("/live/device/get/parameters/min",          on_combined_param_mins)
    d.map("/live/device/get/parameters/max",          on_combined_param_maxs)
    d.map("/live/device/get/parameter/value",         on_fx_param_value)
    d.map("/live/device/get/parameter/value_string",  on_fx_param_value_string)
    d.map("/live/track/get/output_meter_left",        on_track_meter_left)
    d.map("/live/track/get/output_meter_right",       on_track_meter_right)
    d.map("/live/error",                              on_ableton_error)

    ThreadingOSCUDPServer.allow_reuse_address = True

    try:
        st._osc_server = ThreadingOSCUDPServer((OSC_HOST, OSC_RECEIVE_PORT), d)
    except OSError as e:
        log.error(f"OSC receiver could not bind to port {OSC_RECEIVE_PORT}: {e}")
        return

    log.info(f"OSC receiver listening ← {OSC_HOST}:{OSC_RECEIVE_PORT}")
    st._osc_server.serve_forever()