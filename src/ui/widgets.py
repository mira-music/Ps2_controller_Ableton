"""
================================================================================
  src/ui/widgets.py — Canvas Renderers + Dirty-Cache Label Setter
================================================================================
  Three canvas-based renderers, each with its own dirty cache to avoid
  redrawing when nothing has changed:

    draw_knob()           — FX macro knob (270° arc + body + indicator)
    draw_eq_knob()        — DJM-900 metallic EQ knob with dB labels
    draw_channel_meter()  — 24-segment DJM channel meter with peak
    update_meter_peak()   — peak hold/decay logic

  Plus set_label() — diff-based widget update to minimize Tk traffic.
================================================================================
"""

import math

from src.config import (
    EQ_METER_SEGMENTS, EQ_METER_GREEN, EQ_METER_YELLOW, EQ_METER_RED,
    EQ_METER_PEAK_HOLD_S, EQ_METER_PEAK_FALL,
    EQ_MACRO_MIN, EQ_MACRO_MAX, EQ_NEUTRAL_MACRO,
)
from src.ui.palette import (
    ABL_DIVIDER, ABL_YELLOW, ABL_RED,
    ABL_CELL_MOMENT, ABL_CELL_LOCK, ABL_CELL_HOT,
    EQ_KNOB_RING_OUTER, EQ_KNOB_RING_DARK,
    EQ_KNOB_BODY_DARK, EQ_KNOB_BODY_MID, EQ_KNOB_BODY_LIGHT, EQ_KNOB_BODY_RIM,
    EQ_KNOB_INDICATOR, EQ_KNOB_DETENT,
    EQ_KNOB_ARC_BG, EQ_KNOB_ARC_ACTIVE,
    EQ_LABEL_ARMED, EQ_LABEL_SELECTED,
)

# ═══════════════════════════════════════════════════════════════════════════
#  DIRTY-CACHE LABEL SETTER
# ═══════════════════════════════════════════════════════════════════════════

_ui_cache = {}

def set_label(widget, key, text, **kwargs):
    cache_key = (key, text, tuple(sorted(kwargs.items())))
    if _ui_cache.get(key) != cache_key:
        widget.config(text=text, **kwargs)
        _ui_cache[key] = cache_key

# ═══════════════════════════════════════════════════════════════════════════
#  FX KNOB
# ═══════════════════════════════════════════════════════════════════════════

_knob_cache = {}

def draw_knob(canvas, slot, value_frac, color, active=False, locked=False, moment=False):
    cache_key = (round(value_frac, 3), color, active, locked, moment)
    if _knob_cache.get(slot) == cache_key:
        return
    _knob_cache[slot] = cache_key

    canvas.delete("all")

    pad = 4
    size = int(canvas['width']) - pad * 2
    cx = pad + size // 2
    cy = pad + size // 2
    r_outer = size // 2
    r_inner = max(4, r_outer - 5)

    canvas.create_arc(
        cx - r_outer, cy - r_outer,
        cx + r_outer, cy + r_outer,
        start=225, extent=-270,
        style="arc", outline=ABL_DIVIDER, width=2
    )

    if value_frac > 0:
        active_color = color
        if active:
            active_color = ABL_YELLOW
        elif moment:
            active_color = ABL_RED
        canvas.create_arc(
            cx - r_outer, cy - r_outer,
            cx + r_outer, cy + r_outer,
            start=225, extent=-(270 * value_frac),
            style="arc", outline=active_color, width=3
        )

    if moment:
        body_fill = ABL_CELL_MOMENT
        body_outline = ABL_RED
    elif locked:
        body_fill = ABL_CELL_LOCK
        body_outline = ABL_YELLOW
    elif active:
        body_fill = ABL_CELL_HOT
        body_outline = ABL_YELLOW
    else:
        body_fill = "#2a2a2a"
        body_outline = "#444444"

    canvas.create_oval(
        cx - r_inner, cy - r_inner,
        cx + r_inner, cy + r_inner,
        fill=body_fill, outline=body_outline
    )

    angle_deg = 225 - 270 * value_frac
    angle_rad = math.radians(angle_deg)
    ix = cx + r_inner * 0.75 * math.cos(angle_rad)
    iy = cy - r_inner * 0.75 * math.sin(angle_rad)
    indicator_color = color
    if moment:
        indicator_color = ABL_RED
    elif active:
        indicator_color = ABL_YELLOW
    canvas.create_line(cx, cy, ix, iy, fill=indicator_color, width=2)

# ═══════════════════════════════════════════════════════════════════════════
#  EQ KNOB (DJM-900 metallic with dB labels)
# ═══════════════════════════════════════════════════════════════════════════

_eq_knob_cache = {}

def draw_eq_knob(canvas, band_idx, visual_pos, selected=False, armed=False):
    """
    DJM-900 style EQ knob with dB tick labels around perimeter.
    visual_pos: 0.0 = -∞ dB (far left), 0.5 = 0 dB (top), 1.0 = +6 dB (far right)
    """
    cache_key = (round(visual_pos, 3), selected, armed)
    if _eq_knob_cache.get(band_idx) == cache_key:
        return
    _eq_knob_cache[band_idx] = cache_key

    canvas.delete("all")

    w = int(canvas['width'])
    h = int(canvas['height'])
    cx = w // 2
    cy = h // 2

    r_outer  = min(w, h) // 2 - 10
    r_ring   = r_outer - 2
    r_body1  = r_outer - 7
    r_body2  = r_outer - 11
    r_body3  = r_outer - 15
    r_cap    = max(3, r_outer - 20)

    # Outer shadow ring
    canvas.create_oval(
        cx - r_outer, cy - r_outer,
        cx + r_outer, cy + r_outer,
        fill=EQ_KNOB_RING_OUTER, outline=EQ_KNOB_RING_DARK, width=1
    )

    # Background arc
    canvas.create_arc(
        cx - r_ring, cy - r_ring,
        cx + r_ring, cy + r_ring,
        start=225, extent=-270,
        style="arc", outline=EQ_KNOB_ARC_BG, width=2
    )

    # Active arc from center toward current position
    if abs(visual_pos - 0.5) > 0.005:
        if visual_pos < 0.5:
            extent = (0.5 - visual_pos) * 270
            start_angle = 90
        else:
            extent = -(visual_pos - 0.5) * 270
            start_angle = 90
        canvas.create_arc(
            cx - r_ring, cy - r_ring,
            cx + r_ring, cy + r_ring,
            start=start_angle, extent=extent,
            style="arc", outline=EQ_KNOB_ARC_ACTIVE, width=2
        )

    # Perimeter tick marks every 30°
    for tick_angle_deg in range(225, -46, -30):
        tick_rad = math.radians(tick_angle_deg)
        outer_x = cx + (r_ring + 1) * math.cos(tick_rad)
        outer_y = cy - (r_ring + 1) * math.sin(tick_rad)
        inner_x = cx + (r_ring - 2) * math.cos(tick_rad)
        inner_y = cy - (r_ring - 2) * math.sin(tick_rad)
        canvas.create_line(inner_x, inner_y, outer_x, outer_y,
                           fill=EQ_KNOB_BODY_LIGHT, width=1)

    # Prominent center detent at 12 o'clock
    canvas.create_line(cx, cy - (r_ring + 2), cx, cy - (r_ring - 3),
                       fill=EQ_KNOB_DETENT, width=2)

    # dB tick labels
    label_r = r_outer + 6
    lx = cx + label_r * math.cos(math.radians(225))
    ly = cy - label_r * math.sin(math.radians(225))
    canvas.create_text(lx, ly, text="−∞", fill=EQ_KNOB_BODY_LIGHT,
                       font=("Segoe UI", 6, "bold"))
    canvas.create_text(cx, cy - label_r, text="0", fill=EQ_KNOB_DETENT,
                       font=("Segoe UI", 6, "bold"))
    rx = cx + label_r * math.cos(math.radians(-45))
    ry = cy - label_r * math.sin(math.radians(-45))
    canvas.create_text(rx, ry, text="+6", fill=EQ_KNOB_BODY_LIGHT,
                       font=("Segoe UI", 6, "bold"))

    # Metallic body layers
    canvas.create_oval(
        cx - r_body1, cy - r_body1,
        cx + r_body1, cy + r_body1,
        fill=EQ_KNOB_BODY_DARK, outline=EQ_KNOB_BODY_RIM, width=1
    )
    canvas.create_oval(
        cx - r_body2, cy - r_body2,
        cx + r_body2, cy + r_body2,
        fill=EQ_KNOB_BODY_MID, outline=""
    )

    # Selected/armed glow ring
    if armed:
        canvas.create_oval(
            cx - r_body2 - 1, cy - r_body2 - 1,
            cx + r_body2 + 1, cy + r_body2 + 1,
            outline=EQ_LABEL_ARMED, width=2
        )
    elif selected:
        canvas.create_oval(
            cx - r_body2 - 1, cy - r_body2 - 1,
            cx + r_body2 + 1, cy + r_body2 + 1,
            outline=EQ_LABEL_SELECTED, width=1
        )

    canvas.create_oval(
        cx - r_body3, cy - r_body3,
        cx + r_body3, cy + r_body3,
        fill=EQ_KNOB_BODY_LIGHT, outline=""
    )

    # White indicator line
    angle_deg = 225 - 270 * visual_pos
    angle_rad = math.radians(angle_deg)
    line_inner_x = cx + (r_cap + 1) * math.cos(angle_rad)
    line_inner_y = cy - (r_cap + 1) * math.sin(angle_rad)
    line_outer_x = cx + (r_body1 - 1) * math.cos(angle_rad)
    line_outer_y = cy - (r_body1 - 1) * math.sin(angle_rad)
    canvas.create_line(line_inner_x, line_inner_y,
                       line_outer_x, line_outer_y,
                       fill=EQ_KNOB_INDICATOR, width=3)

    # Center cap
    canvas.create_oval(
        cx - r_cap, cy - r_cap,
        cx + r_cap, cy + r_cap,
        fill=EQ_KNOB_BODY_DARK, outline=EQ_KNOB_BODY_RIM, width=1
    )

# ═══════════════════════════════════════════════════════════════════════════
#  DJM CHANNEL METER (24 chunky LED segments + peak hold)
# ═══════════════════════════════════════════════════════════════════════════

_channel_meter_cache = {}

def draw_channel_meter(canvas, level, peak_level):
    """
    DJM-900 style channel output meter.
    level:      current audio level (0.0 to 1.0)
    peak_level: held peak (0.0 to 1.0) — bright white indicator
    """
    cache_key = (round(level, 3), round(peak_level, 3))
    if _channel_meter_cache.get("k") == cache_key:
        return
    _channel_meter_cache["k"] = cache_key

    canvas.delete("all")

    w = int(canvas['width'])
    h = int(canvas['height'])

    total = EQ_METER_SEGMENTS
    gap   = 2
    seg_h = max(2.0, (h - (total - 1) * gap) / total)

    lit      = int(level * total)
    peak_seg = int(peak_level * total) - 1
    if peak_seg < 0:
        peak_seg = -1

    for i in range(total):
        seg_bottom = h - i * (seg_h + gap)
        seg_top    = seg_bottom - seg_h

        if i < EQ_METER_GREEN:
            on_color  = "#22dd44"
            off_color = "#0c1e10"
        elif i < EQ_METER_GREEN + EQ_METER_YELLOW:
            on_color  = "#eecc22"
            off_color = "#1e1e0c"
        else:
            on_color  = "#ee2222"
            off_color = "#1e0c0c"

        is_lit  = (i < lit)
        is_peak = (i == peak_seg and peak_level > 0.02)

        if is_peak:
            fill = "#ffffff"  # bright white peak indicator
        elif is_lit:
            fill = on_color
        else:
            fill = off_color

        canvas.create_rectangle(
            2, seg_top, w - 2, seg_bottom,
            fill=fill, outline="", width=0
        )

def update_meter_peak(current, last_peak, last_peak_time, now):
    """Peak hold + decay logic. Returns (new_peak, new_peak_time)."""
    if current >= last_peak:
        return current, now
    elapsed = now - last_peak_time
    if elapsed < EQ_METER_PEAK_HOLD_S:
        return last_peak, last_peak_time
    fall_elapsed = elapsed - EQ_METER_PEAK_HOLD_S
    decayed = last_peak - EQ_METER_PEAK_FALL * fall_elapsed
    if decayed < current:
        return current, now
    return max(decayed, 0.0), last_peak_time
    
# ═══════════════════════════════════════════════════════════════════════════
#  BUILD B PHASE 2 — DJM-900 METER MATH + CLIP DETECTION
# ═══════════════════════════════════════════════════════════════════════════
#
#  New meter system: 15 segments from -30 dB to +12 dB (3 dB per segment)
#  with CLIP indicator above. Replaces the old 24-segment system in Phase 4.
#
#  These functions compute values; they don't draw anything.
#  The UI updater calls them every frame and stores results in state.
#  The UI builder/drawer reads state to render.
# ═══════════════════════════════════════════════════════════════════════════

import math as _math
from src.config_loader import cfg as _cfg


def raw_meter_to_display_db(raw_value):
    """
    Convert Ableton's raw meter output (0.0 to 1.0) to display dB.

    Ableton's output_meter values are normalized peak levels:
      raw 1.0 = 0 dBFS (digital clipping ceiling)
      raw 0.5 = ~-6 dBFS
      raw 0.0 = -∞ dBFS

    We convert to dBFS, then add a reference offset so the display
    reads in DJ-friendly terms:
      display_dB = dBFS + reference_offset
      display_dB = 20*log10(raw) + 18   (with default offset of 18)

    Result: typical mix sits around 0 on the display, heavy peaks push
    toward +6/+9, and clipping is at +12.

    Returns display dB clamped to [-60, +15] (slightly wider than the
    meter range so we can detect out-of-bounds).
    """
    if raw_value <= 0.0:
        return -60.0

    db_fs = 20.0 * _math.log10(raw_value)
    display_db = db_fs + _cfg.METER_REFERENCE_OFFSET_DB

    # Clamp to a wide range (meter display is -30 to +12,
    # but we allow wider for CLIP detection at +12+)
    if display_db < -60.0:
        return -60.0
    if display_db > 15.0:
        return 15.0
    return display_db


def apply_meter_ballistics(current_db, previous_smoothed_db, dt):
    """
    Apply meter ballistics (release decay).

    Attack: instant (if current > smoothed, snap to current).
    Release: linear decay at cfg.METER_RELEASE_DB_PER_SEC.

    This mimics real analog VU meters where the needle rises instantly
    but falls slowly, giving a readable display even with transient peaks.

    Args:
        current_db:          latest display dB value (from raw_meter_to_display_db)
        previous_smoothed_db: the smoothed value from the last frame
        dt:                  time since last frame (seconds)

    Returns:
        new smoothed dB value
    """
    if current_db >= previous_smoothed_db:
        # Attack: instant rise
        return current_db
    else:
        # Release: decay linearly
        decay = _cfg.METER_RELEASE_DB_PER_SEC * dt
        smoothed = previous_smoothed_db - decay
        # Don't decay below the current actual level
        if smoothed < current_db:
            return current_db
        return smoothed


def update_meter_peak_db(current_db, last_peak_db, last_peak_time, now):
    """
    Peak hold logic for the meter's peak indicator.

    Three states:
      1. New peak captured (current > held peak) → capture it
      2. Within hold window → keep the held peak, don't decay
      3. Hold expired → decay linearly until it reaches current level

    Args:
        current_db:     current smoothed display dB
        last_peak_db:   the held peak dB from previous frame
        last_peak_time: timestamp when the peak was captured
        now:            current time

    Returns:
        (new_peak_db, new_peak_time)
    """
    # New peak — capture it
    if current_db >= last_peak_db:
        return current_db, now

    # Within hold window — keep the peak
    elapsed = now - last_peak_time
    if elapsed < _cfg.METER_PEAK_HOLD_SECONDS:
        return last_peak_db, last_peak_time

    # Hold expired — start decaying
    fall_elapsed = elapsed - _cfg.METER_PEAK_HOLD_SECONDS
    decayed = last_peak_db - (_cfg.METER_PEAK_FALL_DB_PER_SEC * fall_elapsed)

    # Don't decay below current level
    if decayed < current_db:
        return current_db, now

    return max(decayed, -60.0), last_peak_time


def compute_clip_state(display_db, was_active, last_active_time, now):
    """
    Compute the CLIP indicator state.

    Two thresholds with smooth interpolation between them:
      cfg.METER_CLIP_WARN_DB     (default +6)  → clip_level = 0.0 (yellow)
      cfg.METER_CLIP_CRITICAL_DB (default +9)  → clip_level = 1.0 (red)

    Between the two thresholds, clip_level interpolates linearly:
      +6 dB → 0.0 (pure yellow)
      +7 dB → 0.33 (yellowish orange)
      +8 dB → 0.66 (orangish red)
      +9 dB → 1.0 (pure red, flicker starts)

    After the level drops below warn_db, the CLIP stays active for
    cfg.METER_CLIP_FADEOUT_SECONDS (default 0.5s) then fades out.

    Args:
        display_db:       current display dB level
        was_active:       whether CLIP was active last frame
        last_active_time: when CLIP was last actively triggered
        now:              current time

    Returns:
        (is_active, clip_level, new_last_active_time)
        where:
          is_active:  bool — should the CLIP indicator be visible
          clip_level: 0.0-1.0 — color interpolation (0=yellow, 1=red)
          new_last_active_time: updated timestamp
    """
    warn_db = _cfg.METER_CLIP_WARN_DB
    crit_db = _cfg.METER_CLIP_CRITICAL_DB

    if display_db >= warn_db:
        # Level is above warning threshold — CLIP is active
        if crit_db > warn_db:
            # Interpolate between warn and critical
            fraction = (display_db - warn_db) / (crit_db - warn_db)
            clip_level = max(0.0, min(1.0, fraction))
        else:
            clip_level = 1.0

        return True, clip_level, now

    elif was_active:
        # Level dropped below threshold — check fadeout
        elapsed_since_active = now - last_active_time
        if elapsed_since_active < _cfg.METER_CLIP_FADEOUT_SECONDS:
            # Still in fadeout period — fade clip_level toward 0
            fade_fraction = elapsed_since_active / _cfg.METER_CLIP_FADEOUT_SECONDS
            clip_level = max(0.0, 1.0 - fade_fraction)
            return True, clip_level, last_active_time
        else:
            # Fadeout complete — turn off
            return False, 0.0, last_active_time

    else:
        # Not active, level is below threshold
        return False, 0.0, last_active_time


def should_clip_flicker(clip_level, now):
    """
    Determine whether the CLIP indicator should be in its "on" or "off"
    flicker phase. Only flickers when clip_level is above a threshold
    (when approaching or exceeding the critical zone).

    Flicker rate is cfg.METER_CLIP_FLICKER_HZ (default 4 Hz = 250ms cycle).

    Args:
        clip_level: 0.0-1.0 from compute_clip_state
        now:        current time

    Returns:
        True if the CLIP indicator should be BRIGHT this frame,
        False if it should be DIM (or not flickering at all).
    """
    # Only flicker when clip_level is significant (above 0.5 = approaching critical)
    if clip_level < 0.5:
        # Below midpoint — solid on, no flicker
        return True

    # Above midpoint — flicker at configured rate
    hz = _cfg.METER_CLIP_FLICKER_HZ
    if hz <= 0:
        return True

    cycle_s = 1.0 / hz
    position_in_cycle = (now % cycle_s) / cycle_s

    # Square wave: on for first half of cycle, off for second half
    return position_in_cycle < 0.5


def clip_level_to_color(clip_level):
    """
    Convert clip_level (0.0 to 1.0) to an RGB hex color string.

    Smooth gradient:
      0.0 → yellow   (#f4d22b)
      0.3 → orange   (#f4962b)
      0.7 → red-orange (#ee4422)
      1.0 → red      (#ff3b30)

    Uses linear interpolation in RGB space.

    Args:
        clip_level: 0.0 (warning/yellow) to 1.0 (critical/red)

    Returns:
        hex color string like "#ff6c2c"
    """
    # Define the gradient stops
    if clip_level <= 0.0:
        return "#f4d22b"  # yellow
    elif clip_level >= 1.0:
        return "#ff3b30"  # red

    # Smooth interpolation through orange
    # Yellow (#f4d22b) → Orange (#ff6c2c) → Red (#ff3b30)
    if clip_level < 0.5:
        # Yellow to orange (first half)
        t = clip_level / 0.5
        r = int(0xf4 + (0xff - 0xf4) * t)
        g = int(0xd2 + (0x6c - 0xd2) * t)
        b = int(0x2b + (0x2c - 0x2b) * t)
    else:
        # Orange to red (second half)
        t = (clip_level - 0.5) / 0.5
        r = int(0xff + (0xff - 0xff) * t)
        g = int(0x6c + (0x3b - 0x6c) * t)
        b = int(0x2c + (0x30 - 0x2c) * t)

    r = max(0, min(255, r))
    g = max(0, min(255, g))
    b = max(0, min(255, b))

    return f"#{r:02x}{g:02x}{b:02x}"


def display_db_to_segment(display_db, total_segments=15, db_min=-30.0, db_max=12.0):
    """
    Convert display dB to a segment index (0 = bottom, total_segments-1 = top).

    The meter has 15 segments covering -30 dB to +12 dB (3 dB each):
      segment 0  = -30 dB (bottom, green)
      segment 7  = -9 dB
      segment 10 = 0 dB (orange, unity)
      segment 14 = +12 dB (top, red)

    Returns the number of segments that should be LIT (0 to total_segments).
    """
    if display_db <= db_min:
        return 0
    if display_db >= db_max:
        return total_segments

    fraction = (display_db - db_min) / (db_max - db_min)
    return int(fraction * total_segments)


def segment_color(segment_index, total_segments=15):
    """
    Returns the color for a given segment index in the DJM-900 meter.

    Color zones (matching the reference image):
      Segments 0-9   (bottom, -30 to -3 dB)  → yellow/green
      Segments 10-12 (0 to +6 dB)            → orange
      Segment 13     (+9 dB)                  → orange-red
      Segment 14     (+12 dB, top)            → red

    Returns: (on_color, off_color) tuple of hex strings.
    """
    if segment_index >= 14:
        # Top segment — red
        return "#ee2222", "#1e0c0c"
    elif segment_index >= 13:
        # Near-top — orange-red
        return "#ee6622", "#1e120c"
    elif segment_index >= 10:
        # Orange zone (0 to +6 dB)
        return "#eeaa22", "#1e1a0c"
    else:
        # Yellow-green zone (-30 to -3 dB)
        return "#88cc22", "#0c1e0c"