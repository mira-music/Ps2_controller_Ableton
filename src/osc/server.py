"""
================================================================================
  src/osc/server.py — OSC Receive Handlers
================================================================================
  All on_* callbacks invoked when AbletonOSC sends data back to us.
  Handlers update shared state. The Tkinter UI thread reads that state
  at 40 Hz to redraw.

  IMPORTANT: Both FX and EQ single-param listeners share the same OSC
  address (/live/device/get/parameter/value). pythonosc Dispatcher.map()
  only allows one handler per address — second call overwrites the first.
  We solve this with a single dispatching handler (on_param_value) that
  routes internally by track_id.

  Build B: EQ rack now has 4 macros instead of 3 (Trim added at slot 3).
================================================================================
"""

import time
import threading

from src import state as st
from src.config import (
    FX_RACK_DEVICE_INDEX, EQ_RACK_DEVICE_INDEX,
    FX_MACRO_NAMES_EXPECTED, EQ_MACRO_NAMES_EXPECTED,
    EQ_MACRO_COUNT,
    ABLETON_ERROR_THROTTLE,
    OSC_HOST, OSC_RECEIVE_PORT,
)
from src.log_setup import get_logger

log = get_logger(__name__)

# Known Ableton OSC errors to silently downgrade to DEBUG level
_IGNORED_ABLETON_ERROR_PATTERNS = [
    "Unknown OSC address: /live/device/start_listen/parameter/value_string",
    "'NoneType' object has no attribute 'name'",
    "'NoneType' object has no attribute 'color'",
]

# Lock for ableton error throttle globals (these are written from the OSC
# server thread which is ThreadingOSCUDPServer — multiple threads possible).
_error_throttle_lock = threading.Lock()


# ═══════════════════════════════════════════════════════════════════════════
#  SESSION-WIDE HANDLERS
# ═══════════════════════════════════════════════════════════════════════════

def on_bpm(addr, *args):
    if not args:
        return
    with st._lock:
        st.ableton["bpm"] = float(args[0])


def on_is_playing(addr, *args):
    if not args:
        return
    with st._lock:
        st.ableton["is_playing"] = bool(args[0])


def on_scene_count(addr, *args):
    if not args:
        return
    count = int(args[0])
    with st._lock:
        st.state["_real_scene_count"] = count
        while len(st.ableton["all_scene_names"]) < count:
            st.ableton["all_scene_names"].append("")
        while len(st.ableton["all_scene_colors"]) < count:
            st.ableton["all_scene_colors"].append(0)


def on_track_count(addr, *args):
    if not args:
        return
    count = int(args[0])
    with st._lock:
        st.state["_real_track_count"] = count
        while len(st.ableton["all_track_names"]) < count:
            st.ableton["all_track_names"].append("")
        while len(st.ableton["all_track_colors"]) < count:
            st.ableton["all_track_colors"].append(0)


# ═══════════════════════════════════════════════════════════════════════════
#  SCENE + TRACK HANDLERS
# ═══════════════════════════════════════════════════════════════════════════

def on_scene_name(addr, *args):
    if len(args) < 2:
        return
    try:
        idx = int(args[0])
        name = str(args[1]) if args[1] is not None else ""
    except (ValueError, TypeError):
        return
    with st._lock:
        while len(st.ableton["all_scene_names"]) <= idx:
            st.ableton["all_scene_names"].append("")
        st.ableton["all_scene_names"][idx] = name
        if idx == st.state["scene"]:
            st.ableton["scene_name"] = name


def on_scene_color(addr, *args):
    if len(args) < 2:
        return
    try:
        idx = int(args[0])
        color = int(args[1])
    except (ValueError, TypeError):
        return
    with st._lock:
        while len(st.ableton["all_scene_colors"]) <= idx:
            st.ableton["all_scene_colors"].append(0)
        st.ableton["all_scene_colors"][idx] = color


def on_track_name(addr, *args):
    if len(args) < 2:
        return
    try:
        idx = int(args[0])
        name = str(args[1]) if args[1] is not None else ""
    except (ValueError, TypeError):
        return
    with st._lock:
        while len(st.ableton["all_track_names"]) <= idx:
            st.ableton["all_track_names"].append("")
        st.ableton["all_track_names"][idx] = name
        if idx == st.state["track"]:
            st.ableton["track_name"] = name


def on_track_color(addr, *args):
    if len(args) < 2:
        return
    try:
        idx = int(args[0])
        color = int(args[1])
    except (ValueError, TypeError):
        return
    with st._lock:
        while len(st.ableton["all_track_colors"]) <= idx:
            st.ableton["all_track_colors"].append(0)
        st.ableton["all_track_colors"][idx] = color
        if idx == st.state["fx_track_index"]:
            st.ableton["fx_track_color"] = color
        if idx == st.state["eq_track_index"]:
            st.ableton["eq_track_color"] = color


def on_track_volume(addr, *args):
    if len(args) < 2:
        return
    try:
        idx = int(args[0])
        vol = float(args[1])
    except (ValueError, TypeError):
        return
    with st._lock:
        if idx == st.state["track"]:
            st.ableton["track_volume"] = vol


def on_track_meter_left(addr, *args):
    if len(args) < 2:
        return
    try:
        idx = int(args[0])
        level = float(args[1])
    except (ValueError, TypeError):
        return
    with st._lock:
        eq_idx = st.state["eq_track_index"]
        # Guard: idx must be non-negative and match the EQ track
        if idx >= 0 and idx == eq_idx:
            st.state["eq_meter_left"] = level


def on_track_meter_right(addr, *args):
    if len(args) < 2:
        return
    try:
        idx = int(args[0])
        level = float(args[1])
    except (ValueError, TypeError):
        return
    with st._lock:
        eq_idx = st.state["eq_track_index"]
        if idx >= 0 and idx == eq_idx:
            st.state["eq_meter_right"] = level


# ═══════════════════════════════════════════════════════════════════════════
#  CLIP HANDLERS
# ═══════════════════════════════════════════════════════════════════════════

def on_clip_name(addr, *args):
    if len(args) < 3:
        return
    try:
        track_idx = int(args[0])
        scene_idx = int(args[1])
        name = str(args[2]) if args[2] is not None else ""
    except (ValueError, TypeError):
        return
    with st._lock:
        if track_idx == st.state["track"] and scene_idx == st.state["scene"]:
            st.ableton["clip_name"] = name
            st.ableton["clip_empty"] = (name == "" or name.lower() == "none")


def on_clip_color(addr, *args):
    if len(args) < 3:
        return
    try:
        track_idx = int(args[0])
        scene_idx = int(args[1])
        color = int(args[2])
    except (ValueError, TypeError):
        return
    with st._lock:
        if track_idx == st.state["track"] and scene_idx == st.state["scene"]:
            st.ableton["clip_color"] = color


# ═══════════════════════════════════════════════════════════════════════════
#  COMBINED PARAM HANDLERS (dispatch FX vs EQ by track_id)
# ═══════════════════════════════════════════════════════════════════════════

def on_combined_param_names(addr, *args):
    if len(args) < 3:
        return
    try:
        track_idx = int(args[0])
        device_idx = int(args[1])
    except (ValueError, TypeError):
        return
    with st._lock:
        fx_track = st.state["fx_track_index"]
        eq_track = st.state["eq_track_index"]

    if track_idx == fx_track and device_idx == FX_RACK_DEVICE_INDEX:
        _handle_fx_macro_names(args[2:])
    elif track_idx == eq_track and device_idx == EQ_RACK_DEVICE_INDEX:
        _handle_eq_macro_names(args[2:])


def on_combined_param_mins(addr, *args):
    if len(args) < 3:
        return
    try:
        track_idx = int(args[0])
        device_idx = int(args[1])
    except (ValueError, TypeError):
        return
    with st._lock:
        fx_track = st.state["fx_track_index"]
        eq_track = st.state["eq_track_index"]

    if track_idx == fx_track and device_idx == FX_RACK_DEVICE_INDEX:
        _handle_fx_macro_mins(args[2:])
    elif track_idx == eq_track and device_idx == EQ_RACK_DEVICE_INDEX:
        _handle_eq_macro_mins(args[2:])


def on_combined_param_maxs(addr, *args):
    if len(args) < 3:
        return
    try:
        track_idx = int(args[0])
        device_idx = int(args[1])
    except (ValueError, TypeError):
        return
    with st._lock:
        fx_track = st.state["fx_track_index"]
        eq_track = st.state["eq_track_index"]

    if track_idx == fx_track and device_idx == FX_RACK_DEVICE_INDEX:
        _handle_fx_macro_maxs(args[2:])
    elif track_idx == eq_track and device_idx == EQ_RACK_DEVICE_INDEX:
        _handle_eq_macro_maxs(args[2:])


def on_combined_param_values(addr, *args):
    if len(args) < 3:
        return
    try:
        track_idx = int(args[0])
        device_idx = int(args[1])
    except (ValueError, TypeError):
        return
    with st._lock:
        fx_track = st.state["fx_track_index"]
        eq_track = st.state["eq_track_index"]

    if track_idx == fx_track and device_idx == FX_RACK_DEVICE_INDEX:
        _handle_fx_macro_values(args[2:])
    elif track_idx == eq_track and device_idx == EQ_RACK_DEVICE_INDEX:
        _handle_eq_macro_values(args[2:])


# ═══════════════════════════════════════════════════════════════════════════
#  FX MACRO HANDLERS
# ═══════════════════════════════════════════════════════════════════════════

def _handle_fx_macro_names(args):
    found_names = [""] * 8
    found_ids = [-1] * 8
    found_count = 0

    for pid, raw_name in enumerate(args):
        try:
            name = str(raw_name)
        except (ValueError, TypeError):
            continue
        for slot, expected in enumerate(FX_MACRO_NAMES_EXPECTED):
            if name == expected and found_ids[slot] < 0:
                found_names[slot] = name
                found_ids[slot] = pid
                found_count += 1
                break

    with st._lock:
        st.state["fx_macro_names"] = found_names
        st.state["fx_macro_param_ids"] = found_ids
        st.state["fx_ready"] = (found_count > 0)

    log.info(f"FX macros mapped: {found_count}/8")
    for slot, (name, pid) in enumerate(zip(found_names, found_ids)):
        if name:
            log.info(f"  slot {slot}: param[{pid}] = '{name}'")
        else:
            log.warning(f"  slot {slot}: MISSING '{FX_MACRO_NAMES_EXPECTED[slot]}'")


def _handle_fx_macro_mins(args):
    """Min values arrive as flat list indexed by param_id. Single lock acquisition."""
    with st._lock:
        for slot, pid in enumerate(st.state["fx_macro_param_ids"]):
            if 0 <= pid < len(args):
                try:
                    st.state["fx_macro_mins"][slot] = float(args[pid])
                except (ValueError, TypeError):
                    continue


def _handle_fx_macro_maxs(args):
    """Max values arrive as flat list indexed by param_id. Single lock acquisition."""
    with st._lock:
        for slot, pid in enumerate(st.state["fx_macro_param_ids"]):
            if 0 <= pid < len(args):
                try:
                    st.state["fx_macro_maxs"][slot] = float(args[pid])
                except (ValueError, TypeError):
                    continue


def _handle_fx_macro_values(args):
    """
    Current values arrive as flat list indexed by param_id.
    Auto-captures baseline on first successful read.

    Baseline capture is done inside a single lock acquisition to prevent
    a race where action_save_baseline() fires between the read and write.
    """
    with st._lock:
        param_ids = list(st.state["fx_macro_param_ids"])
        baseline_already = st.state["fx_baseline_ready"]

        for slot, pid in enumerate(param_ids):
            if 0 <= pid < len(args):
                try:
                    st.state["fx_macro_values"][slot] = float(args[pid])
                except (ValueError, TypeError):
                    continue

        # Re-check baseline_ready inside the lock to avoid race with
        # action_save_baseline() firing between two lock acquisitions.
        if not st.state["fx_baseline_ready"] and any(p >= 0 for p in param_ids):
            st.state["fx_baseline"] = list(st.state["fx_macro_values"])
            st.state["fx_baseline_ready"] = True
            st.state["fx_baseline_captured_at"] = time.perf_counter()
            log.info(f"Baseline auto-captured: {st.state['fx_baseline']}")


def on_fx_param_value(addr, *args):
    """Single-parameter listener for FX (live updates). Called by on_param_value."""
    if len(args) < 4:
        return
    try:
        track_idx = int(args[0])
        device_idx = int(args[1])
        pid = int(args[2])
        val = float(args[3])
    except (ValueError, TypeError):
        return
    with st._lock:
        if track_idx != st.state["fx_track_index"] or device_idx != FX_RACK_DEVICE_INDEX:
            return
        param_ids = st.state["fx_macro_param_ids"]
        if pid in param_ids:
            slot = param_ids.index(pid)
            st.state["fx_macro_values"][slot] = val


def on_fx_param_value_string(addr, *args):
    """Display-string for FX. Called by on_param_value_string."""
    if len(args) < 4:
        return
    try:
        track_idx = int(args[0])
        device_idx = int(args[1])
        pid = int(args[2])
        text = str(args[3])
    except (ValueError, TypeError):
        return
    with st._lock:
        if track_idx != st.state["fx_track_index"] or device_idx != FX_RACK_DEVICE_INDEX:
            return
        param_ids = st.state["fx_macro_param_ids"]
        if pid in param_ids:
            slot = param_ids.index(pid)
            st.state["fx_macro_value_strings"][slot] = text


# ═══════════════════════════════════════════════════════════════════════════
#  EQ MACRO HANDLERS
# ═══════════════════════════════════════════════════════════════════════════

def _handle_eq_macro_names(args):
    found_names = [""] * EQ_MACRO_COUNT
    found_ids = [-1] * EQ_MACRO_COUNT
    found_count = 0

    for pid, raw_name in enumerate(args):
        try:
            name = str(raw_name)
        except (ValueError, TypeError):
            continue
        for slot, expected in enumerate(EQ_MACRO_NAMES_EXPECTED):
            if name == expected and found_ids[slot] < 0:
                found_names[slot] = name
                found_ids[slot] = pid
                found_count += 1
                break

    with st._lock:
        st.state["eq_macro_names"] = found_names
        st.state["eq_macro_param_ids"] = found_ids
        st.state["eq_ready"] = (found_count > 0)

    log.info(f"EQ macros mapped: {found_count}/{EQ_MACRO_COUNT}")
    for slot, (name, pid) in enumerate(zip(found_names, found_ids)):
        if name:
            log.info(f"  slot {slot}: param[{pid}] = '{name}'")
        else:
            log.warning(f"  slot {slot}: MISSING '{EQ_MACRO_NAMES_EXPECTED[slot]}'")


def _handle_eq_macro_mins(args):
    """Single lock acquisition."""
    with st._lock:
        for slot, pid in enumerate(st.state["eq_macro_param_ids"]):
            if 0 <= pid < len(args):
                try:
                    st.state["eq_macro_mins"][slot] = float(args[pid])
                except (ValueError, TypeError):
                    continue


def _handle_eq_macro_maxs(args):
    """Single lock acquisition."""
    with st._lock:
        for slot, pid in enumerate(st.state["eq_macro_param_ids"]):
            if 0 <= pid < len(args):
                try:
                    st.state["eq_macro_maxs"][slot] = float(args[pid])
                except (ValueError, TypeError):
                    continue


def _handle_eq_macro_values(args):
    """Single lock acquisition."""
    with st._lock:
        for slot, pid in enumerate(st.state["eq_macro_param_ids"]):
            if 0 <= pid < len(args):
                try:
                    st.state["eq_macro_values"][slot] = float(args[pid])
                except (ValueError, TypeError):
                    continue


def on_eq_param_value(addr, *args):
    """Single-parameter listener for EQ. Called by on_param_value."""
    if len(args) < 4:
        return
    try:
        track_idx = int(args[0])
        device_idx = int(args[1])
        pid = int(args[2])
        val = float(args[3])
    except (ValueError, TypeError):
        return
    with st._lock:
        if track_idx != st.state["eq_track_index"] or device_idx != EQ_RACK_DEVICE_INDEX:
            return
        param_ids = st.state["eq_macro_param_ids"]
        if pid in param_ids:
            slot = param_ids.index(pid)
            st.state["eq_macro_values"][slot] = val


def on_eq_param_value_string(addr, *args):
    """Display-string for EQ. Called by on_param_value_string."""
    if len(args) < 4:
        return
    try:
        track_idx = int(args[0])
        device_idx = int(args[1])
        pid = int(args[2])
        text = str(args[3])
    except (ValueError, TypeError):
        return
    with st._lock:
        if track_idx != st.state["eq_track_index"] or device_idx != EQ_RACK_DEVICE_INDEX:
            return
        param_ids = st.state["eq_macro_param_ids"]
        if pid in param_ids:
            slot = param_ids.index(pid)
            st.state["eq_macro_value_strings"][slot] = text


# ═══════════════════════════════════════════════════════════════════════════
#  UNIFIED SINGLE-PARAM DISPATCHERS
#
#  pythonosc Dispatcher.map() only allows ONE handler per address.
#  Registering both on_fx_param_value and on_eq_param_value to the same
#  address would silently drop the first. These unified handlers dispatch
#  internally by track_id, solving the overwrite problem.
# ═══════════════════════════════════════════════════════════════════════════

def on_param_value(addr, *args):
    """
    Unified handler for /live/device/get/parameter/value.
    Routes to FX or EQ handler based on which track sent the update.
    """
    if len(args) < 1:
        return
    try:
        track_idx = int(args[0])
    except (ValueError, TypeError):
        return

    with st._lock:
        fx_track = st.state["fx_track_index"]
        eq_track = st.state["eq_track_index"]

    if track_idx == fx_track:
        on_fx_param_value(addr, *args)
    elif track_idx == eq_track:
        on_eq_param_value(addr, *args)


def on_param_value_string(addr, *args):
    """
    Unified handler for /live/device/get/parameter/value_string.
    Routes to FX or EQ handler based on which track sent the update.
    """
    if len(args) < 1:
        return
    try:
        track_idx = int(args[0])
    except (ValueError, TypeError):
        return

    with st._lock:
        fx_track = st.state["fx_track_index"]
        eq_track = st.state["eq_track_index"]

    if track_idx == fx_track:
        on_fx_param_value_string(addr, *args)
    elif track_idx == eq_track:
        on_eq_param_value_string(addr, *args)


# ═══════════════════════════════════════════════════════════════════════════
#  ABLETON ERROR HANDLER
# ═══════════════════════════════════════════════════════════════════════════

def on_ableton_error(addr, *args):
    if not args:
        return
    msg = str(args[0])
    now = time.perf_counter()

    for pattern in _IGNORED_ABLETON_ERROR_PATTERNS:
        if pattern in msg:
            log.debug(f"Ableton (benign): {msg}")
            return

    # Use a dedicated lock for throttle globals — these are written from
    # the OSC server's thread pool (ThreadingOSCUDPServer), not the main lock.
    with _error_throttle_lock:
        last_msg  = st._last_ableton_error_msg
        last_time = st._last_ableton_error_time
        if (msg == last_msg and
                (now - last_time) < ABLETON_ERROR_THROTTLE):
            return
        st._last_ableton_error_msg  = msg
        st._last_ableton_error_time = now

    log.warning(f"Ableton error: {msg}")


# ═══════════════════════════════════════════════════════════════════════════
#  OSC SERVER STARTUP
# ═══════════════════════════════════════════════════════════════════════════

def start_osc_server():
    """
    Start the OSC server in a background thread.
    Sets state["_shutting_down"] = False on entry.
    The unified on_param_value / on_param_value_string handlers are registered
    once each, replacing the old duplicate-registration pattern.
    """
    from pythonosc.dispatcher import Dispatcher
    from pythonosc.osc_server import ThreadingOSCUDPServer

    dispatcher = Dispatcher()

    # Session
    dispatcher.map("/live/song/get/tempo",        on_bpm)
    dispatcher.map("/live/song/get/is_playing",   on_is_playing)
    dispatcher.map("/live/song/get/num_scenes",   on_scene_count)
    dispatcher.map("/live/song/get/num_tracks",   on_track_count)

    # Scenes
    dispatcher.map("/live/scene/get/name",        on_scene_name)
    dispatcher.map("/live/scene/get/color",       on_scene_color)

    # Tracks
    dispatcher.map("/live/track/get/name",        on_track_name)
    dispatcher.map("/live/track/get/color",       on_track_color)
    dispatcher.map("/live/track/get/volume",      on_track_volume)
    dispatcher.map("/live/track/get/output_meter_left",  on_track_meter_left)
    dispatcher.map("/live/track/get/output_meter_right", on_track_meter_right)

    # Clips
    dispatcher.map("/live/clip/get/name",         on_clip_name)
    dispatcher.map("/live/clip/get/color",        on_clip_color)

    # Device params (combined bulk — dispatches by track_id)
    dispatcher.map("/live/device/get/parameters/name",  on_combined_param_names)
    dispatcher.map("/live/device/get/parameters/min",   on_combined_param_mins)
    dispatcher.map("/live/device/get/parameters/max",   on_combined_param_maxs)
    dispatcher.map("/live/device/get/parameters/value", on_combined_param_values)

    # Single-param listeners — UNIFIED handlers to avoid dispatcher overwrite.
    # Both FX and EQ listeners share these addresses; routing is done internally
    # by track_id inside on_param_value / on_param_value_string.
    dispatcher.map("/live/device/get/parameter/value",        on_param_value)
    dispatcher.map("/live/device/get/parameter/value_string", on_param_value_string)

    # Errors
    dispatcher.map("/live/error", on_ableton_error)

    server = ThreadingOSCUDPServer((OSC_HOST, OSC_RECEIVE_PORT), dispatcher)
    st._osc_server = server
    log.info(f"OSC receiver listening ← {OSC_HOST}:{OSC_RECEIVE_PORT}")
    server.serve_forever()