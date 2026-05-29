"""
================================================================================
  src/controller/axes.py — Axis + D-pad Handlers
================================================================================
  Layer-aware axis processing:

    handle_axes_navigation(ctrl)
        L-stick X/Y → track/scene navigation with hold-to-scroll

    handle_axes_fx(ctrl, dt)
        L-stick Y → Filter Freq (sweep with acceleration)
        L-stick X → Filter Res (sweep)
        R-stick   → FX Send + Reverb Size (rotation-corrected)

    handle_axes_eq(ctrl, dt)
        Y axis → double-flick BAND navigation (with axis-dominance suppression)
        X axis → encoder VALUE control + double-flick value actions
        Y gesture FREEZES X encoder until complete (and vice versa)

    handle_right_joystick_volume(ctrl)
        SELECT+R-stick Y → Ableton track volume control

    handle_dpad(ctrl)
        Nav layer: U/D bookmarks, L/R groups (with R2=force lead)
        FX layer:  U/D bookmarks, L/R Delay FB step

  All tunable values read from cfg (hot-reloadable via SELECT+START):
    cfg.ANALOG_THRESHOLD  cfg.HOLD_SCROLL_DELAY  cfg.HOLD_SCROLL_RATE
    cfg.FX_AXIS_DEAD_ZONE
    cfg.EQ_SMOOTHING_FACTOR  cfg.EQ_AXIS_DEAD_ZONE  cfg.EQ_DOMINANCE_RATIO
    cfg.VOL_DEAD_ZONE  cfg.VOL_SENSITIVITY  cfg.VOL_CHANGE_THRESHOLD
================================================================================
"""

import time

from src import state as st
from src.config import (
    # Architectural constants — axis indices, slot indices, hardware-defined
    AXIS_LEFT_X, AXIS_LEFT_Y, AXIS_RIGHT_X, AXIS_RIGHT_Y,
    FX_SLOT_FILTER_FREQ, FX_SLOT_FILTER_RES, FX_SLOT_FX_SEND, FX_SLOT_REVERB_SIZE,
    RIGHT_STICK_ROTATED_90,
    VOL_MIN, VOL_MAX,
)
from src.config_loader import cfg
from src.helpers import (
    smooth_axis, hybrid_curve, clamp, db_from_vol,
    compute_accel_multiplier,
)
from src.osc.client import osc_set_volume
from src.engine.navigation import (
    navigate_scene, navigate_track, navigate_bookmark, navigate_track_group,
)
from src.engine.fx import fx_drive_macro, fx_step_delay_fb
from src.engine.eq import (
    update_eq_x_gesture, update_eq_y_gesture_v911,
    eq_drive_continuous_encoder,
)

# ═══════════════════════════════════════════════════════════════════════════
#  LEFT-STICK NAVIGATION (L-stick X/Y for track/scene)
# ═══════════════════════════════════════════════════════════════════════════

def handle_axes_navigation(controller):
    """
    Reads from cfg (hot-reloadable):
      cfg.ANALOG_THRESHOLD     — how far to push stick before scrolling triggers
      cfg.HOLD_SCROLL_DELAY    — pause before auto-scroll starts
      cfg.HOLD_SCROLL_RATE     — speed of auto-scroll once started
    """
    now = time.perf_counter()

    st._smoothed_lx = smooth_axis(st._smoothed_lx, controller.get_axis(AXIS_LEFT_X))
    st._smoothed_ly = smooth_axis(st._smoothed_ly, controller.get_axis(AXIS_LEFT_Y))
    lx = hybrid_curve(st._smoothed_lx)
    ly = hybrid_curve(st._smoothed_ly)

    dir_x = 1 if lx > cfg.ANALOG_THRESHOLD else (-1 if lx < -cfg.ANALOG_THRESHOLD else 0)
    with st._lock:
        last_dir_x    = st.state["_lx_last_dir"]
        held_since_x  = st.state["_lx_held_since"]
        last_repeat_x = st.state["_lx_last_repeat"]

    if dir_x != last_dir_x:
        with st._lock:
            st.state["_lx_last_dir"]    = dir_x
            st.state["_lx_held_since"]  = now if dir_x != 0 else 0.0
            st.state["_lx_last_repeat"] = now
        if dir_x != 0:
            navigate_track(dir_x)
    elif dir_x != 0:
        if (now - held_since_x  >= cfg.HOLD_SCROLL_DELAY and
                now - last_repeat_x >= cfg.HOLD_SCROLL_RATE):
            navigate_track(dir_x)
            with st._lock:
                st.state["_lx_last_repeat"] = now

    dir_y = 1 if ly > cfg.ANALOG_THRESHOLD else (-1 if ly < -cfg.ANALOG_THRESHOLD else 0)
    with st._lock:
        last_dir_y    = st.state["_ly_last_dir"]
        held_since_y  = st.state["_ly_held_since"]
        last_repeat_y = st.state["_ly_last_repeat"]

    if dir_y != last_dir_y:
        with st._lock:
            st.state["_ly_last_dir"]    = dir_y
            st.state["_ly_held_since"]  = now if dir_y != 0 else 0.0
            st.state["_ly_last_repeat"] = now
        if dir_y != 0:
            navigate_scene(dir_y)
    elif dir_y != 0:
        if (now - held_since_y  >= cfg.HOLD_SCROLL_DELAY and
                now - last_repeat_y >= cfg.HOLD_SCROLL_RATE):
            navigate_scene(dir_y)
            with st._lock:
                st.state["_ly_last_repeat"] = now

# ═══════════════════════════════════════════════════════════════════════════
#  FX-LAYER AXES (both sticks)
# ═══════════════════════════════════════════════════════════════════════════

def handle_axes_fx(controller, dt):
    """
    Reads from cfg (hot-reloadable):
      cfg.FX_AXIS_DEAD_ZONE — stick deadzone for FX layer
    """
    now = time.perf_counter()

    raw_lx = controller.get_axis(AXIS_LEFT_X)
    raw_ly = controller.get_axis(AXIS_LEFT_Y)
    raw_rx = controller.get_axis(AXIS_RIGHT_X)
    raw_ry = controller.get_axis(AXIS_RIGHT_Y)

    st._smoothed_lx = smooth_axis(st._smoothed_lx, raw_lx)
    st._smoothed_ly = smooth_axis(st._smoothed_ly, raw_ly)
    st._smoothed_rx = smooth_axis(st._smoothed_rx, raw_rx)
    st._smoothed_ry = smooth_axis(st._smoothed_ry, raw_ry)

    lx = hybrid_curve(st._smoothed_lx)
    ly = -hybrid_curve(st._smoothed_ly)
    rx = hybrid_curve(st._smoothed_rx)
    ry = hybrid_curve(st._smoothed_ry)

    if RIGHT_STICK_ROTATED_90:
        fx_send_input    = -rx
        reverb_size_input = ry
        fx_send_dir = 1 if fx_send_input > cfg.FX_AXIS_DEAD_ZONE else \
                      (-1 if fx_send_input < -cfg.FX_AXIS_DEAD_ZONE else 0)
        rev_size_dir = 1 if reverb_size_input > cfg.FX_AXIS_DEAD_ZONE else \
                       (-1 if reverb_size_input < -cfg.FX_AXIS_DEAD_ZONE else 0)
        accel_fxsend  = compute_accel_multiplier("rx", fx_send_dir, now)
        accel_revsize = compute_accel_multiplier("ry", rev_size_dir, now)
    else:
        fx_send_input    = -ry
        reverb_size_input = rx
        fx_send_dir = 1 if fx_send_input > cfg.FX_AXIS_DEAD_ZONE else \
                      (-1 if fx_send_input < -cfg.FX_AXIS_DEAD_ZONE else 0)
        rev_size_dir = 1 if reverb_size_input > cfg.FX_AXIS_DEAD_ZONE else \
                       (-1 if reverb_size_input < -cfg.FX_AXIS_DEAD_ZONE else 0)
        accel_fxsend  = compute_accel_multiplier("ry", fx_send_dir, now)
        accel_revsize = compute_accel_multiplier("rx", rev_size_dir, now)

    lx_dir = 1 if lx > cfg.FX_AXIS_DEAD_ZONE else (-1 if lx < -cfg.FX_AXIS_DEAD_ZONE else 0)
    ly_dir = 1 if ly > cfg.FX_AXIS_DEAD_ZONE else (-1 if ly < -cfg.FX_AXIS_DEAD_ZONE else 0)
    accel_lx = compute_accel_multiplier("lx", lx_dir, now)
    accel_ly = compute_accel_multiplier("ly", ly_dir, now)

    fx_drive_macro(FX_SLOT_FILTER_FREQ,  ly,                dt, accel_ly)
    fx_drive_macro(FX_SLOT_FILTER_RES,   lx,                dt, accel_lx)
    fx_drive_macro(FX_SLOT_FX_SEND,      fx_send_input,     dt, accel_fxsend)
    fx_drive_macro(FX_SLOT_REVERB_SIZE,  reverb_size_input, dt, accel_revsize)

# ═══════════════════════════════════════════════════════════════════════════
#  EQ-LAYER AXES (right stick only)
# ═══════════════════════════════════════════════════════════════════════════

def handle_axes_eq(controller, dt):
    """
    EQ mode axis handling.

    Y axis (up/down): DOUBLE-FLICK to switch band
                      UP   → next band up (HIGH direction, wraps)
                      DOWN → next band down (LOW direction, wraps)
    X axis (left/right): ENCODER (continuous value control) + double-flick actions
                         RIGHT held → boost
                         LEFT  held → cut
                         RIGHT 2x   → restore/boost-15%
                         LEFT  2x   → kill/normalize

    Mutual exclusion: each axis freezes the other during gesture detection.

    Right stick is physically rotated 90° (see RIGHT_STICK_ROTATED_90).

    Reads from cfg (hot-reloadable):
      cfg.EQ_SMOOTHING_FACTOR
      cfg.EQ_AXIS_DEAD_ZONE
      cfg.EQ_DOMINANCE_RATIO
    """
    now = time.perf_counter()

    raw_rx = controller.get_axis(AXIS_RIGHT_X)
    raw_ry = controller.get_axis(AXIS_RIGHT_Y)

    st._smoothed_eq_rx = smooth_axis(st._smoothed_eq_rx, raw_rx, factor=cfg.EQ_SMOOTHING_FACTOR)
    st._smoothed_eq_ry = smooth_axis(st._smoothed_eq_ry, raw_ry, factor=cfg.EQ_SMOOTHING_FACTOR)

    rx_curved = hybrid_curve(st._smoothed_eq_rx)
    ry_curved = hybrid_curve(st._smoothed_eq_ry)

    if RIGHT_STICK_ROTATED_90:
        eq_y_input = -rx_curved
        eq_x_input =  ry_curved
    else:
        eq_y_input = -ry_curved
        eq_x_input =  rx_curved

    abs_x = abs(eq_x_input)
    abs_y = abs(eq_y_input)

    # ── STEP 1: Y gesture (band navigation) — runs first ──────────────
    y_in_gesture = update_eq_y_gesture_v911(eq_y_input, now)

    # ── STEP 2: Y dominance suppression ────────────────────────────────
    y_dominates = (abs_y > cfg.EQ_AXIS_DEAD_ZONE and
                   abs_y > abs_x * cfg.EQ_DOMINANCE_RATIO)

    if y_in_gesture or y_dominates:
        # Y owns the stick — freeze X completely
        with st._lock:
            st.state["_eq_encoder_last_tick"] = now
            st.state["_eq_flick_x_state"]     = "idle"
            st.state["_eq_flick_x_dir"]       = 0
        return

    # ── STEP 3: X gesture (kill / restore) ─────────────────────────────
    x_in_gesture = update_eq_x_gesture(eq_x_input, now)

    if x_in_gesture:
        # X owns the stick — freeze Y completely
        # Prevents band switch from firing mid-gesture
        with st._lock:
            st.state["_eq_encoder_last_tick"] = now
            st.state["_eq_flick_y_state"]     = "idle"
            st.state["_eq_flick_y_dir"]       = 0
        # Do NOT run encoder during a gesture
        return

    # ── STEP 4: Continuous encoder (only when no gesture owns the stick) ─
    eq_drive_continuous_encoder(eq_x_input, now)

# ═══════════════════════════════════════════════════════════════════════════
#  SELECT+R-STICK VOLUME CONTROL
# ═══════════════════════════════════════════════════════════════════════════

def handle_right_joystick_volume(controller):
    """
    SELECT modifier + R-stick Y = track volume control.

    Reads from cfg (hot-reloadable):
      cfg.VOL_DEAD_ZONE         — stick deadzone for volume
      cfg.VOL_SENSITIVITY       — how much volume changes per stick movement
      cfg.VOL_CHANGE_THRESHOLD  — minimum change worth sending to Ableton
    """
    with st._lock:
        if not st.state["select_held"]:
            return

    st._smoothed_ry = smooth_axis(st._smoothed_ry, controller.get_axis(AXIS_RIGHT_Y))
    ry  = hybrid_curve(st._smoothed_ry)
    now = time.perf_counter()

    if abs(ry) < cfg.VOL_DEAD_ZONE:
        return

    delta = -ry * cfg.VOL_SENSITIVITY
    should_send = False

    with st._lock:
        new_vol = clamp(st.ableton["track_volume"] + delta, VOL_MIN, VOL_MAX)
        if new_vol == st.ableton["track_volume"]:
            return
        st.ableton["track_volume"] = new_vol
        if (now - st.state["_vol_last_sent"] > 0.02 and
                abs(new_vol - st.state["_vol_last_value"]) > cfg.VOL_CHANGE_THRESHOLD):
            st.state["_vol_last_sent"]  = now
            st.state["_vol_last_value"] = new_vol
            should_send = True
        st.state["last_action"] = f"Vol  {db_from_vol(new_vol)}"

    if should_send:
        osc_set_volume(new_vol)

# ═══════════════════════════════════════════════════════════════════════════
#  D-PAD ROUTING
# ═══════════════════════════════════════════════════════════════════════════

def handle_dpad(controller):
    """
    Nav layer: U/D bookmarks + L/R groups (R2 held = force-lead navigation)
    FX layer:  U/D bookmarks + L/R Delay FB step
    """
    if controller.get_numhats() == 0:
        return
    h, v = controller.get_hat(0)

    with st._lock:
        l1     = st.state["l1_held"]
        r2_hld = st.state["r2_held"]

    if l1:
        if   v == 1:  navigate_bookmark(-1)
        elif v == -1: navigate_bookmark(+1)
        if   h == 1:  fx_step_delay_fb(+1)
        elif h == -1: fx_step_delay_fb(-1)
        return

    if   v == 1:  navigate_bookmark(-1)
    elif v == -1: navigate_bookmark(+1)
    if   h == 1:  navigate_track_group(+1, force_lead=r2_hld)
    elif h == -1: navigate_track_group(-1, force_lead=r2_hld)