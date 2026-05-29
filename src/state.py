"""
================================================================================
  src/state.py — Shared State + Thread Locks
================================================================================
  Thread-safe state shared across all 5 daemon threads.

  Three rules for using _lock:
    1. Always hold the lock when reading or writing state
    2. NEVER call OSC functions while holding the lock
    3. Use the RLock for nested locking (same-thread re-acquire is safe)

  Build B changes:
    - EQ macro arrays expanded from 3 to 4 entries (added TRIM at slot 3)
    - Added TRIM-specific encoder state
    - Added missing volume control and R3 mute state keys (_vol_last_sent,
      _vol_last_value, _r3_last_click)
================================================================================
"""

import threading
from src.config import (
    EQ_MACRO_COUNT,
    EQ_NEUTRAL_MACRO,
    EQ_SLOT_MID,
    ABLETON_UNITY,
    MAX_TRACKS, MAX_SCENES,
)

# ═══════════════════════════════════════════════════════════════════════════
#  THREAD LOCKS
# ═══════════════════════════════════════════════════════════════════════════

_lock        = threading.RLock()
_fetch_lock  = threading.Lock()

# ═══════════════════════════════════════════════════════════════════════════
#  CORE MUTABLE STATE
# ═══════════════════════════════════════════════════════════════════════════

state = {
    # ─── Navigation ───
    "track":            0,
    "scene":            0,
    "bookmark_cursor":  0,
    "group_cursor":     0,
    "track_group":      0,
    "_lx_last_dir":     0,
    "_ly_last_dir":     0,
    "_lx_held_since":   0.0,
    "_ly_held_since":   0.0,
    "_lx_last_repeat":  0.0,
    "_ly_last_repeat":  0.0,
    "_last_dpad_v":     0.0,
    "_last_dpad_h":     0.0,
    "next_group_name":  "—",
    "prev_group_name":  "—",
    "bookmarks":        [],
    "groups":           [],
    "_real_track_count": MAX_TRACKS,
    "_real_scene_count": MAX_SCENES,
    "_group_memory":    {},

    # ─── Controller status ───
    "controller_connected": False,
    "controller_name":      "—",
    "_last_input_at":   0.0,
    "_last_reprobe":    0.0,
    "_last_select_reconcile": 0.0,

    # ─── Modifiers ───
    "l1_held":          False,
    "r2_held":          False,
    "select_held":      False,
    "_pre_l1_track":    -1,

    # ─── FX rack discovery + state ───
    "fx_track_index":   -1,
    "fx_track_name":    "",
    "fx_ready":         False,
    "fx_macro_names":   [""] * 8,
    "fx_macro_param_ids": [0] * 8,
    "fx_macro_values":  [0.0] * 8,
    "fx_macro_mins":    [0.0] * 8,
    "fx_macro_maxs":    [127.0] * 8,
    "fx_macro_value_strings": [""] * 8,
    "fx_baseline":      [0.0] * 8,
    "fx_baseline_ready": False,
    "fx_baseline_captured_at": 0.0,
    "fx_filter_locked": False,
    "fx_wet_locked":    False,
    "_fx_last_write_at":  [0.0] * 8,
    "_fx_last_write_val": [0.0] * 8,
    "_fx_recovery_until": [0.0] * 8,
    "_fx_active_slot":  -1,
    "_fx_active_until": 0.0,
    "_fx_last_dpad_h":  0.0,
    "_accel_since":     {"lx": 0.0, "ly": 0.0, "rx": 0.0, "ry": 0.0},
    "_accel_last_dir":  {"lx": 0, "ly": 0, "rx": 0, "ry": 0},

    # ─── Momentary FX state ───
    "_momentary_stutter_active": False,
    "_momentary_bass_cut_active": False,
    "_momentary_bass_cut_snapshot": {"freq": 0.0, "mode": 0.0},
    "_momentary_fx_throw_active": False,
    "_momentary_fx_throw_snapshot": {"fx_send": 0.0},

    # ─── EQ rack discovery + state ───
    # Build B: arrays now sized for 4 macros (Low, Mid, High, Trim)
    "eq_track_index":   -1,
    "eq_track_name":    "",
    "eq_ready":         False,
    "eq_macro_names":   [""] * EQ_MACRO_COUNT,
    "eq_macro_param_ids": [0] * EQ_MACRO_COUNT,
    "eq_macro_values":  [EQ_NEUTRAL_MACRO] * EQ_MACRO_COUNT,
    "eq_macro_mins":    [0.0] * EQ_MACRO_COUNT,
    "eq_macro_maxs":    [127.0] * EQ_MACRO_COUNT,
    "eq_macro_value_strings": [""] * EQ_MACRO_COUNT,
    "_eq_last_write_at":  [0.0] * EQ_MACRO_COUNT,
    "_eq_last_write_val": [0.0] * EQ_MACRO_COUNT,

    # ─── EQ mode + gesture state ───
    "eq_mode_active":   False,
    "eq_selected_band": EQ_SLOT_MID,
    "eq_armed_band":    -1,
    "eq_armed_until":   0.0,

    # X-axis gesture state machine (value actions: kill/normalize/boost/restore)
    "_eq_flick_x_state":   "idle",
    "_eq_flick_x_dir":     0,
    "_eq_flick_x_time":    0.0,
    "_eq_flick_x_returned_time": 0.0,

    # Y-axis gesture state machine (band navigation)
    "_eq_flick_y_state":   "idle",
    "_eq_flick_y_dir":     0,
    "_eq_flick_y_time":    0.0,
    "_eq_flick_y_returned_time": 0.0,

    # Continuous encoder state
    "_eq_encoder_last_tick": 0.0,

    # ─── EQ ramp animation (one slot per macro) ───
    "_eq_ramp_active":     [False] * EQ_MACRO_COUNT,
    "_eq_ramp_start_val":  [0.0]   * EQ_MACRO_COUNT,
    "_eq_ramp_target_val": [0.0]   * EQ_MACRO_COUNT,
    "_eq_ramp_start_time": [0.0]   * EQ_MACRO_COUNT,
    "_eq_ramp_duration":   [0.0]   * EQ_MACRO_COUNT,

    # ─── EQ meter (channel output level) ───
    # Raw values from Ableton (0.0 to 1.0 normalized peak)
    "eq_meter_left":        0.0,
    "eq_meter_right":       0.0,

    # OLD meter state (kept until Phase 4 replaces the drawing code)
    "eq_meter_peak":        0.0,
    "eq_meter_peak_time":   0.0,

    # Build B Phase 2: processed meter values for the new DJM-style display
    "meter_display_db":     -60.0,
    "meter_smoothed_db":    -60.0,
    "meter_peak_db":        -60.0,
    "meter_peak_time":      0.0,

    # CLIP indicator state
    "clip_active":          False,
    "clip_level":           0.0,
    "clip_last_active_time": 0.0,

    # ─── UI flash + last action ───
    "last_action":      "Starting up…",
    "flash_scene":      False,
    "flash_track":      False,
    "flash_bmark":      False,
    "flash_group":      False,
    "flash_until":      0.0,

    # ─── Notification slot (Build B Phase 3) ───
    "notification_text":     "",
    "notification_severity": "info",
    "notification_time":     0.0,
    "notification_duration": 3.0,

    # ─── Volume control state (SELECT + R-stick) ───
    # These were previously missing, causing KeyError on first volume use.
    "_vol_last_sent":   0.0,   # timestamp of last volume OSC write
    "_vol_last_value":  ABLETON_UNITY,  # value at last write (for epsilon culling)

    # ─── R3 double-click mute (SELECT + R3) ───
    # Previously missing, causing KeyError on first mute toggle.
    "_r3_last_click":   0.0,   # timestamp of last R3 click (0.0 = never)

    # ─── Polling timing ───
    "_query_requested_at": 0.0,

    # ─── Shutdown flag (explicit signal for clean loop exit) ───
    # More reliable than checking _osc_server is None, which is ambiguous
    # when OSC server fails to start during startup.
    "_shutting_down":   False,
}

# ═══════════════════════════════════════════════════════════════════════════
#  ABLETON-SIDE STATE MIRROR
# ═══════════════════════════════════════════════════════════════════════════

ableton = {
    "bpm":              120.0,
    "is_playing":       False,
    "track_name":       "—",
    "scene_name":       "—",
    "clip_name":        "—",
    "clip_empty":       True,
    "track_volume":     ABLETON_UNITY,
    "all_track_names":  [],
    "all_scene_names":  [],
    "all_track_colors": [],
    "all_scene_colors": [],
    "fx_track_color":   0,
    "eq_track_color":   0,
    "clip_color":       0,
}

# ═══════════════════════════════════════════════════════════════════════════
#  MODULE-LEVEL GLOBALS (assigned during startup)
# ═══════════════════════════════════════════════════════════════════════════

osc = None             # SimpleUDPClient — assigned by setup_osc()
_osc_server = None     # ThreadingOSCUDPServer — assigned by start_osc_server()
_ctrl_handle = None    # pygame Joystick — assigned by reprobe_controller()

# Smoothed axis values (held across frames for exponential smoothing)
_smoothed_lx = 0.0
_smoothed_ly = 0.0
_smoothed_rx = 0.0
_smoothed_ry = 0.0
_smoothed_eq_rx = 0.0
_smoothed_eq_ry = 0.0

# Listener registration flags
FX_LISTEN_REGISTERED = False
EQ_LISTEN_REGISTERED = False

# Ableton error throttling
_last_ableton_error_msg  = ""
_last_ableton_error_time = 0.0


def _set_controller_handle(handle):
    """Set the pygame Joystick handle (called by watchdog)."""
    global _ctrl_handle
    _ctrl_handle = handle

def _get_controller_handle():
    """Get the current pygame Joystick handle."""
    return _ctrl_handle