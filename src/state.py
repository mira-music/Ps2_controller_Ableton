"""
================================================================================
  src/state.py — Shared State
================================================================================
  All mutable state lives here. Protected by _lock (reentrant) and
  _fetch_lock (regular). Other modules import this and read/write the
  state dict under the lock.

  Globals exposed:
    state           — main runtime state dict
    ableton         — current Ableton-side values (synced via OSC)
    _lock           — reentrant lock for state/ableton access
    _fetch_lock     — for discovery operations
    osc             — OSC client (assigned in osc.client.setup_osc)
    _osc_server     — OSC server reference (assigned at startup)
    _ctrl_handle    — pygame joystick handle
    _smoothed_*     — axis smoothing accumulators
    FX_LISTEN_REGISTERED / EQ_LISTEN_REGISTERED — listener guards
================================================================================
"""

import threading
from src.config import (
    EQ_NEUTRAL_MACRO, EQ_SLOT_MID,
    MAX_SCENES, MAX_TRACKS, ABLETON_UNITY,
)

# ═══════════════════════════════════════════════════════════════════════════
#  THREAD LOCKS
# ═══════════════════════════════════════════════════════════════════════════

_lock        = threading.RLock()
_fetch_lock  = threading.Lock()

# ═══════════════════════════════════════════════════════════════════════════
#  LISTENER REGISTRATION FLAGS (module-level globals)
# ═══════════════════════════════════════════════════════════════════════════

FX_LISTEN_REGISTERED = False
EQ_LISTEN_REGISTERED = False

# ═══════════════════════════════════════════════════════════════════════════
#  SHARED STATE
# ═══════════════════════════════════════════════════════════════════════════

state = {
    "scene":        0,
    "track":        0,
    "track_group":  0,

    "bookmarks":       [],
    "bookmark_cursor": 0,

    "groups":          [],
    "group_cursor":    0,

    "r2_held":      False,
    "select_held":  False,
    "l1_held":      False,

    "flash_scene":  False,
    "flash_track":  False,
    "flash_bmark":  False,
    "flash_group":  False,
    "flash_until":  0.0,

    "last_action":  "Starting up…",

    "controller_connected": False,
    "controller_name":      "—",

    "_last_input_at":  0.0,
    "_last_reprobe":   0.0,
    "_last_select_reconcile": 0.0,

    "_last_dpad_v": 0.0,
    "_last_dpad_h": 0.0,

    "_lx_held_since":   0.0,
    "_ly_held_since":   0.0,
    "_lx_last_dir":     0,
    "_ly_last_dir":     0,
    "_lx_last_repeat":  0.0,
    "_ly_last_repeat":  0.0,

    "_group_memory": {},

    "fx_track_index":     -1,
    "fx_track_name":      "",
    "fx_macro_names":     [""] * 8,
    "fx_macro_values":    [0.0] * 8,
    "fx_macro_mins":      [0.0] * 8,
    "fx_macro_maxs":      [1.0] * 8,
    "fx_macro_param_ids": [0] * 8,
    "fx_ready":           False,

    "fx_macro_value_strings": ["—"] * 8,

    "fx_baseline":             [0.0] * 8,
    "fx_baseline_ready":       False,
    "fx_baseline_captured_at": 0.0,
    "fx_filter_locked":        False,
    "fx_wet_locked":           False,
    "_fx_recovery_until":      [0.0] * 8,

    "_pre_l1_track":         -1,

    "_fx_last_write_at":  [0.0] * 8,
    "_fx_last_write_val": [0.0] * 8,
    "_fx_last_dpad_h":    0.0,
    "_fx_active_slot":    -1,
    "_fx_active_until":   0.0,

    "_accel_since": {"lx": 0.0, "ly": 0.0, "rx": 0.0, "ry": 0.0},
    "_accel_last_dir": {"lx": 0, "ly": 0, "rx": 0, "ry": 0},

    "_momentary_stutter_active":      False,
    "_momentary_bass_cut_active":     False,
    "_momentary_fx_throw_active":     False,
    "_momentary_bass_cut_snapshot":   {"freq": 0.0, "mode": 0.0},
    "_momentary_fx_throw_snapshot":   {"fx_send": 0.0},

    "eq_track_index":      -1,
    "eq_track_name":       "",
    "eq_macro_names":      [""] * 3,
    "eq_macro_values":     [EQ_NEUTRAL_MACRO] * 3,
    "eq_macro_mins":       [0.0] * 3,
    "eq_macro_maxs":       [127.0] * 3,
    "eq_macro_param_ids":  [0] * 3,
    "eq_macro_value_strings": ["—"] * 3,
    "eq_ready":            False,

    "eq_mode_active":      False,
    "eq_selected_band":    EQ_SLOT_MID,
    "eq_armed_band":       -1,
    "eq_armed_until":      0.0,

    # Gesture detection (X axis = value actions in v9.9+)
    "_eq_flick_x_state":   "idle",
    "_eq_flick_x_dir":     0,
    "_eq_flick_x_time":    0.0,
    "_eq_flick_x_returned_time": 0.0,

    # Y gesture state (v9.11: band navigation via double-flick)
    "_eq_flick_y_state":   "idle",
    "_eq_flick_y_dir":     0,
    "_eq_flick_y_time":    0.0,
    "_eq_flick_y_returned_time": 0.0,

    # v9.11: band navigation now uses double-flick on Y axis
    # (hold-to-switch removed — see _eq_flick_y_state for the new gesture)

    # EQ ramp animation
    "_eq_ramp_active":     [False] * 3,
    "_eq_ramp_start_val":  [0.0] * 3,
    "_eq_ramp_target_val": [0.0] * 3,
    "_eq_ramp_start_time": [0.0] * 3,
    "_eq_ramp_duration":   [0.0] * 3,

    "_eq_last_write_at":   [0.0] * 3,
    "_eq_last_write_val":  [0.0] * 3,

    "_eq_encoder_last_tick": 0.0,

    # v9.10: real audio meter on EQ track output (DJM channel meter)
    "eq_meter_left":       0.0,
    "eq_meter_right":      0.0,
    "eq_meter_peak":       0.0,
    "eq_meter_peak_time":  0.0,

    "_real_track_count":  MAX_TRACKS,
    "_real_scene_count":  MAX_SCENES,

    "next_group_name": "—",
    "prev_group_name": "—",

    "_r3_last_click":      0.0,
    "_query_requested_at": 0.0,
    "_vol_last_sent":  0.0,
    "_vol_last_value": ABLETON_UNITY,
}

# ═══════════════════════════════════════════════════════════════════════════
#  ABLETON-SYNCED VALUES
# ═══════════════════════════════════════════════════════════════════════════

ableton = {
    "bpm":             120.0,
    "is_playing":      False,
    "track_name":      "—",
    "scene_name":      "—",
    "track_volume":    ABLETON_UNITY,
    "clip_name":       "—",
    "clip_empty":      False,
    "all_scene_names": [],
    "all_track_names": [],
    "all_scene_colors": [],
    "all_track_colors": [],
    "clip_color":       0,
    "fx_track_color":   0,
    "eq_track_color":   0,
}

# ═══════════════════════════════════════════════════════════════════════════
#  SMOOTHED AXIS VALUES (module-level, mutated by axis handlers)
# ═══════════════════════════════════════════════════════════════════════════

_smoothed_lx = 0.0
_smoothed_ly = 0.0
_smoothed_rx = 0.0
_smoothed_ry = 0.0
_smoothed_eq_rx = 0.0
_smoothed_eq_ry = 0.0

# ═══════════════════════════════════════════════════════════════════════════
#  OSC + CONTROLLER REFERENCES
# ═══════════════════════════════════════════════════════════════════════════

osc          = None    # assigned in osc.client.setup_osc()
_osc_server  = None    # assigned in osc.server.start_osc_server()
_ctrl_handle = None    # assigned in controller.watchdog.reprobe_controller()

# ═══════════════════════════════════════════════════════════════════════════
#  ERROR THROTTLING (module-level, mutated by osc.server)
# ═══════════════════════════════════════════════════════════════════════════

_last_ableton_error_msg  = ""
_last_ableton_error_time = 0.0

# ═══════════════════════════════════════════════════════════════════════════
#  CONTROLLER HANDLE ACCESSORS
# ═══════════════════════════════════════════════════════════════════════════

def _set_controller_handle(h):
    global _ctrl_handle
    with _lock:
        _ctrl_handle = h

def _get_controller_handle():
    with _lock:
        return _ctrl_handle