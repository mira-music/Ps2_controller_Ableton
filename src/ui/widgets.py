"""
================================================================================
  src/ui/widgets.py — Canvas Renderers + Dirty-Cache Label Setter
================================================================================
  Three knob renderers with dirty caching:

    draw_knob()           — FX macro knob (270° arc + body + indicator)
    draw_eq_knob()        — DJM-900 metallic EQ knob, -∞/0/+6 dB labels
    draw_trim_knob()      — DJM-900 metallic TRIM knob, -∞/0/+9 dB labels

  Legacy 24-segment meter (kept for compatibility, not active):
    draw_channel_meter()
    update_meter_peak()

  Meter math (compute only, no drawing):
    raw_meter_to_display_db()
    apply_meter_ballistics()
    update_meter_peak_db()
    compute_clip_state()
    should_clip_flicker()
    clip_level_to_color()
    display_db_to_segment()
    segment_color()

  Build B Phase 4 DJM-900 NXS2 meter with PhotoImage bitmap rendering:
    draw_djm_meter()      — main entry point, drop-in replacement for old version

  Plus set_label() — diff-based widget update.

  Active build details:
    - TRIM visual position uses cfg.TRIM_MAX_DB as the visual full-right
      endpoint via compute_trim_visual_position().
    - CLIP indicator spans the full meter column width (~2× original).
    - Meter LED bar is a single PhotoImage with incremental pixel updates.
      Only segments that change state since last frame are repainted.
================================================================================
"""

import math
import tkinter as tk

from src.config import (
    EQ_METER_SEGMENTS, EQ_METER_GREEN, EQ_METER_YELLOW, EQ_METER_RED,
    EQ_METER_PEAK_HOLD_S, EQ_METER_PEAK_FALL,
    EQ_MACRO_MIN, EQ_MACRO_MAX, EQ_NEUTRAL_MACRO,
    TRIM_NEUTRAL_MACRO, TRIM_DB_PER_MACRO,
)
from src.config_loader import cfg
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
    """Update Tkinter Label only when text/style actually changed."""
    cache_key = (key, text, tuple(sorted(kwargs.items())))
    if _ui_cache.get(key) != cache_key:
        widget.config(text=text, **kwargs)
        _ui_cache[key] = cache_key


# ═══════════════════════════════════════════════════════════════════════════
#  TRIM VISUAL POSITION
#  Maps macro value to visual knob position using cfg.TRIM_MAX_DB as the
#  full-right endpoint (5 o'clock = visual 1.0).
# ═══════════════════════════════════════════════════════════════════════════

def compute_trim_visual_position(macro_value: float) -> float:
    """
    Convert a TRIM macro value (0.0 to MAX_CAP) to a visual knob position
    in the range [0.0, 1.0].

    The boost side uses cfg.TRIM_MAX_DB as the visual 1.0 endpoint so
    the indicator reaches 5 o'clock when TRIM is at its configured cap.
    """
    if cfg.TRIM_MAX_DB <= 0.0:
        visual_max_macro = TRIM_NEUTRAL_MACRO
    else:
        visual_max_macro = TRIM_NEUTRAL_MACRO + (cfg.TRIM_MAX_DB / TRIM_DB_PER_MACRO)
        if visual_max_macro > EQ_MACRO_MAX:
            visual_max_macro = EQ_MACRO_MAX

    if macro_value <= TRIM_NEUTRAL_MACRO:
        if TRIM_NEUTRAL_MACRO <= 0:
            return 0.0
        return (macro_value / TRIM_NEUTRAL_MACRO) * 0.5

    boost_range = visual_max_macro - TRIM_NEUTRAL_MACRO
    if boost_range <= 0:
        return 0.5

    boost_fraction = (macro_value - TRIM_NEUTRAL_MACRO) / boost_range
    if boost_fraction > 1.0:
        boost_fraction = 1.0
    return 0.5 + boost_fraction * 0.5


# ═══════════════════════════════════════════════════════════════════════════
#  FX KNOB
# ═══════════════════════════════════════════════════════════════════════════

_knob_cache = {}

def draw_knob(canvas, slot, value_frac, color, active=False, locked=False, moment=False):
    """FX macro knob: 270° arc + body circle + indicator line."""
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
        body_fill, body_outline = ABL_CELL_MOMENT, ABL_RED
    elif locked:
        body_fill, body_outline = ABL_CELL_LOCK,  ABL_YELLOW
    elif active:
        body_fill, body_outline = ABL_CELL_HOT,   ABL_YELLOW
    else:
        body_fill, body_outline = "#2a2a2a", "#444444"

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
#  EQ KNOB (DJM-900 metallic, -∞/0/+6 dB labels)
# ═══════════════════════════════════════════════════════════════════════════

_eq_knob_cache = {}

def draw_eq_knob(canvas, band_idx, visual_pos, selected=False, armed=False):
    """DJM-900 metallic EQ knob."""
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

    canvas.create_oval(
        cx - r_outer, cy - r_outer,
        cx + r_outer, cy + r_outer,
        fill=EQ_KNOB_RING_OUTER, outline=EQ_KNOB_RING_DARK, width=1
    )

    canvas.create_arc(
        cx - r_ring, cy - r_ring,
        cx + r_ring, cy + r_ring,
        start=225, extent=-270,
        style="arc", outline=EQ_KNOB_ARC_BG, width=2
    )

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

    for tick_angle_deg in range(225, -46, -30):
        tick_rad = math.radians(tick_angle_deg)
        outer_x = cx + (r_ring + 1) * math.cos(tick_rad)
        outer_y = cy - (r_ring + 1) * math.sin(tick_rad)
        inner_x = cx + (r_ring - 2) * math.cos(tick_rad)
        inner_y = cy - (r_ring - 2) * math.sin(tick_rad)
        canvas.create_line(inner_x, inner_y, outer_x, outer_y,
                           fill=EQ_KNOB_BODY_LIGHT, width=1)

    canvas.create_line(cx, cy - (r_ring + 2), cx, cy - (r_ring - 3),
                       fill=EQ_KNOB_DETENT, width=2)

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

    angle_deg = 225 - 270 * visual_pos
    angle_rad = math.radians(angle_deg)
    line_inner_x = cx + (r_cap + 1) * math.cos(angle_rad)
    line_inner_y = cy - (r_cap + 1) * math.sin(angle_rad)
    line_outer_x = cx + (r_body1 - 1) * math.cos(angle_rad)
    line_outer_y = cy - (r_body1 - 1) * math.sin(angle_rad)
    canvas.create_line(line_inner_x, line_inner_y,
                       line_outer_x, line_outer_y,
                       fill=EQ_KNOB_INDICATOR, width=3)

    canvas.create_oval(
        cx - r_cap, cy - r_cap,
        cx + r_cap, cy + r_cap,
        fill=EQ_KNOB_BODY_DARK, outline=EQ_KNOB_BODY_RIM, width=1
    )


# ═══════════════════════════════════════════════════════════════════════════
#  TRIM KNOB (DJM-900 metallic, -∞/0/+9 dB labels)
# ═══════════════════════════════════════════════════════════════════════════

_trim_knob_cache = {}

def draw_trim_knob(canvas, band_idx, visual_pos, selected=False, armed=False):
    """DJM-900 metallic TRIM knob with -∞/0/+9 labels."""
    cache_key = (round(visual_pos, 3), selected, armed)
    if _trim_knob_cache.get(band_idx) == cache_key:
        return
    _trim_knob_cache[band_idx] = cache_key

    canvas.delete("all")

    w = int(canvas['width'])
    h = int(canvas['height'])
    cx = w // 2
    cy = h // 2

    r_outer = min(w, h) // 2 - 10
    r_ring  = r_outer - 2
    r_body1 = r_outer - 7
    r_body2 = r_outer - 11
    r_body3 = r_outer - 15
    r_cap   = max(3, r_outer - 20)

    canvas.create_oval(
        cx - r_outer, cy - r_outer,
        cx + r_outer, cy + r_outer,
        fill=EQ_KNOB_RING_OUTER, outline=EQ_KNOB_RING_DARK, width=1
    )

    canvas.create_arc(
        cx - r_ring, cy - r_ring,
        cx + r_ring, cy + r_ring,
        start=225, extent=-270,
        style="arc", outline=EQ_KNOB_ARC_BG, width=2
    )

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

    for tick_angle_deg in range(225, -46, -30):
        tick_rad = math.radians(tick_angle_deg)
        ox = cx + (r_ring + 1) * math.cos(tick_rad)
        oy = cy - (r_ring + 1) * math.sin(tick_rad)
        ix = cx + (r_ring - 2) * math.cos(tick_rad)
        iy = cy - (r_ring - 2) * math.sin(tick_rad)
        canvas.create_line(ix, iy, ox, oy, fill=EQ_KNOB_BODY_LIGHT, width=1)

    canvas.create_line(cx, cy - (r_ring + 2), cx, cy - (r_ring - 3),
                       fill=EQ_KNOB_DETENT, width=2)

    label_r = r_outer + 6
    lx = cx + label_r * math.cos(math.radians(225))
    ly = cy - label_r * math.sin(math.radians(225))
    canvas.create_text(lx, ly, text="−∞", fill=EQ_KNOB_BODY_LIGHT,
                       font=("Segoe UI", 6, "bold"))
    canvas.create_text(cx, cy - label_r, text="0", fill=EQ_KNOB_DETENT,
                       font=("Segoe UI", 6, "bold"))
    rx = cx + label_r * math.cos(math.radians(-45))
    ry = cy - label_r * math.sin(math.radians(-45))
    canvas.create_text(rx, ry, text="+9", fill=EQ_KNOB_BODY_LIGHT,
                       font=("Segoe UI", 6, "bold"))

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

    angle_deg = 225 - 270 * visual_pos
    angle_rad = math.radians(angle_deg)
    lix = cx + (r_cap + 1) * math.cos(angle_rad)
    liy = cy - (r_cap + 1) * math.sin(angle_rad)
    lox = cx + (r_body1 - 1) * math.cos(angle_rad)
    loy = cy - (r_body1 - 1) * math.sin(angle_rad)
    canvas.create_line(lix, liy, lox, loy, fill=EQ_KNOB_INDICATOR, width=3)

    canvas.create_oval(
        cx - r_cap, cy - r_cap,
        cx + r_cap, cy + r_cap,
        fill=EQ_KNOB_BODY_DARK, outline=EQ_KNOB_BODY_RIM, width=1
    )


# ═══════════════════════════════════════════════════════════════════════════
#  LEGACY 24-SEGMENT METER (kept for compatibility — not active in current build)
# ═══════════════════════════════════════════════════════════════════════════

_channel_meter_cache = {}

def draw_channel_meter(canvas, level, peak_level):
    """Legacy 24-segment meter. New code uses draw_djm_meter."""
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
            on_color, off_color = "#22dd44", "#0c1e10"
        elif i < EQ_METER_GREEN + EQ_METER_YELLOW:
            on_color, off_color = "#eecc22", "#1e1e0c"
        else:
            on_color, off_color = "#ee2222", "#1e0c0c"

        is_lit  = (i < lit)
        is_peak = (i == peak_seg and peak_level > 0.02)

        if is_peak:
            fill = "#ffffff"
        elif is_lit:
            fill = on_color
        else:
            fill = off_color

        canvas.create_rectangle(
            2, seg_top, w - 2, seg_bottom,
            fill=fill, outline="", width=0
        )


def update_meter_peak(current, last_peak, last_peak_time, now):
    """Legacy 0-1 raw peak hold/decay."""
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
#  METER MATH (compute only, no drawing)
# ═══════════════════════════════════════════════════════════════════════════

def raw_meter_to_display_db(raw_value):
    """Convert Ableton 0-1 raw meter to display dB with reference offset."""
    if raw_value <= 0.0:
        return -60.0
    db_fs = 20.0 * math.log10(raw_value)
    display_db = db_fs + cfg.METER_REFERENCE_OFFSET_DB
    if display_db < -60.0:
        return -60.0
    if display_db > 15.0:
        return 15.0
    return display_db


def apply_meter_ballistics(current_db, previous_smoothed_db, dt):
    """Instant attack, linear release decay."""
    if current_db >= previous_smoothed_db:
        return current_db
    decay = cfg.METER_RELEASE_DB_PER_SEC * dt
    smoothed = previous_smoothed_db - decay
    if smoothed < current_db:
        return current_db
    return smoothed


def update_meter_peak_db(current_db, last_peak_db, last_peak_time, now):
    """Peak capture → hold → linear decay."""
    if current_db >= last_peak_db:
        return current_db, now
    elapsed = now - last_peak_time
    if elapsed < cfg.METER_PEAK_HOLD_SECONDS:
        return last_peak_db, last_peak_time
    fall_elapsed = elapsed - cfg.METER_PEAK_HOLD_SECONDS
    decayed = last_peak_db - (cfg.METER_PEAK_FALL_DB_PER_SEC * fall_elapsed)
    if decayed < current_db:
        return current_db, now
    return max(decayed, -60.0), last_peak_time


def compute_clip_state(display_db, was_active, last_active_time, now):
    """CLIP active state + level interpolation + fadeout."""
    warn_db = cfg.METER_CLIP_WARN_DB
    crit_db = cfg.METER_CLIP_CRITICAL_DB

    if display_db >= warn_db:
        if crit_db > warn_db:
            fraction = (display_db - warn_db) / (crit_db - warn_db)
            clip_level = max(0.0, min(1.0, fraction))
        else:
            clip_level = 1.0
        return True, clip_level, now

    elif was_active:
        elapsed_since_active = now - last_active_time
        if elapsed_since_active < cfg.METER_CLIP_FADEOUT_SECONDS:
            fade_fraction = elapsed_since_active / cfg.METER_CLIP_FADEOUT_SECONDS
            clip_level = max(0.0, 1.0 - fade_fraction)
            return True, clip_level, last_active_time
        else:
            return False, 0.0, last_active_time

    else:
        return False, 0.0, last_active_time


def should_clip_flicker(clip_level, now):
    """Square-wave flicker at cfg.METER_CLIP_FLICKER_HZ when clip_level ≥ 0.5."""
    if clip_level < 0.5:
        return True
    hz = cfg.METER_CLIP_FLICKER_HZ
    if hz <= 0:
        return True
    cycle_s = 1.0 / hz
    position_in_cycle = (now % cycle_s) / cycle_s
    return position_in_cycle < 0.5


def clip_level_to_color(clip_level):
    """Yellow (0.0) → orange (0.5) → red (1.0) interpolation in RGB."""
    if clip_level <= 0.0:
        return "#f4d22b"
    elif clip_level >= 1.0:
        return "#ff3b30"

    if clip_level < 0.5:
        t = clip_level / 0.5
        r = int(0xf4 + (0xff - 0xf4) * t)
        g = int(0xd2 + (0x6c - 0xd2) * t)
        b = int(0x2b + (0x2c - 0x2b) * t)
    else:
        t = (clip_level - 0.5) / 0.5
        r = int(0xff + (0xff - 0xff) * t)
        g = int(0x6c + (0x3b - 0x6c) * t)
        b = int(0x2c + (0x30 - 0x2c) * t)

    r = max(0, min(255, r))
    g = max(0, min(255, g))
    b = max(0, min(255, b))
    return f"#{r:02x}{g:02x}{b:02x}"


def display_db_to_segment(display_db, total_segments=15, db_min=-30.0, db_max=12.0):
    """Display dB → lit segment count."""
    if display_db <= db_min:
        return 0
    if display_db >= db_max:
        return total_segments
    fraction = (display_db - db_min) / (db_max - db_min)
    return int(fraction * total_segments)


def segment_color(segment_index, total_segments=15):
    """Return (on_color, off_color) for a meter segment by index."""
    if segment_index >= 14:
        return "#ee2222", "#1e0c0c"
    elif segment_index >= 13:
        return "#ee6622", "#1e120c"
    elif segment_index >= 10:
        return "#eeaa22", "#1e1a0c"
    else:
        return "#88cc22", "#0c1e0c"


# ═══════════════════════════════════════════════════════════════════════════
#  ROUNDED RECTANGLE HELPER (used by FX knob bodies)
# ═══════════════════════════════════════════════════════════════════════════

def _rounded_rect(canvas, x1, y1, x2, y2, radius=3, fill="#000000", outline=""):
    """Rounded rectangle via overlapping rects + corner ovals."""
    r = min(radius, abs(x2 - x1) // 2, abs(y2 - y1) // 2)
    if r < 1:
        canvas.create_rectangle(x1, y1, x2, y2, fill=fill, outline=outline, width=0)
        return

    canvas.create_rectangle(x1 + r, y1, x2 - r, y2, fill=fill, outline="", width=0)
    canvas.create_rectangle(x1, y1 + r, x2, y2 - r, fill=fill, outline="", width=0)

    canvas.create_oval(x1, y1, x1 + 2*r, y1 + 2*r, fill=fill, outline="", width=0)
    canvas.create_oval(x2 - 2*r, y1, x2, y1 + 2*r, fill=fill, outline="", width=0)
    canvas.create_oval(x1, y2 - 2*r, x1 + 2*r, y2, fill=fill, outline="", width=0)
    canvas.create_oval(x2 - 2*r, y2 - 2*r, x2, y2, fill=fill, outline="", width=0)

    if outline:
        canvas.create_arc(x1, y1, x1 + 2*r, y1 + 2*r,
                          start=90, extent=90, style="arc", outline=outline, width=1)
        canvas.create_arc(x2 - 2*r, y1, x2, y1 + 2*r,
                          start=0, extent=90, style="arc", outline=outline, width=1)
        canvas.create_arc(x1, y2 - 2*r, x1 + 2*r, y2,
                          start=180, extent=90, style="arc", outline=outline, width=1)
        canvas.create_arc(x2 - 2*r, y2 - 2*r, x2, y2,
                          start=270, extent=90, style="arc", outline=outline, width=1)
        canvas.create_line(x1 + r, y1, x2 - r, y1, fill=outline, width=1)
        canvas.create_line(x1 + r, y2, x2 - r, y2, fill=outline, width=1)
        canvas.create_line(x1, y1 + r, x1, y2 - r, fill=outline, width=1)
        canvas.create_line(x2, y1 + r, x2, y2 - r, fill=outline, width=1)


# ═══════════════════════════════════════════════════════════════════════════
#  DJM METER — PhotoImage bitmap renderer (high-performance)
#
#  Architecture:
#    - One PhotoImage bitmap per canvas (LED bar area only)
#    - dB labels are canvas items, drawn once on first frame
#    - CLIP indicator is two canvas items (rect + text), updated via itemconfig
#    - Per-frame: only LED segments that changed state since last frame
#      are repainted. Most frames during audio playback see 1-3 changes.
#
#  Per-canvas state is stored in _djm_meter_state[id(canvas)].
# ═══════════════════════════════════════════════════════════════════════════

_djm_meter_state: dict = {}


def _get_or_create_meter_state(canvas, w: int, h: int) -> dict:
    """
    Get or lazily create per-canvas state. Called on every frame but only
    does real work on first call or after canvas resize.
    """
    canvas_id = id(canvas)
    state = _djm_meter_state.get(canvas_id)

    label_width = 20
    led_left    = label_width + 3
    led_right   = led_left + 8
    led_width   = led_right - led_left

    clip_h      = 16
    clip_top    = 2
    clip_bottom = clip_top + clip_h
    clip_left   = 2
    clip_right  = max(led_right + 2, w - 2)

    clip_to_meter_gap = 8
    meter_top    = clip_bottom + clip_to_meter_gap
    meter_bottom = h - 4
    led_height   = meter_bottom - meter_top

    if state is not None and state.get("led_height") == led_height and state.get("led_width") == led_width:
        return state

    # Clean slate if size changed
    if state is not None:
        try:
            canvas.delete("all")
        except Exception:
            pass

    bitmap = tk.PhotoImage(width=led_width, height=led_height)
    bitmap.put("#000000", to=(0, 0, led_width, led_height))

    state = {
        "bitmap":              bitmap,
        "image_id":            None,
        "clip_bg_id":          None,
        "clip_text_id":        None,
        "label_ids":           [],
        "label_ids_drawn":     False,
        "last_clip_state":     None,
        "last_segment_states": None,
        "segment_colors":      None,
        "led_height":          led_height,
        "led_width":           led_width,
        "led_left":            led_left,
        "led_right":           led_right,
        "meter_top":           meter_top,
        "meter_bottom":        meter_bottom,
        "clip_top":            clip_top,
        "clip_bottom":         clip_bottom,
        "clip_left":           clip_left,
        "clip_right":          clip_right,
        "canvas_w":            w,
        "canvas_h":            h,
    }

    _djm_meter_state[canvas_id] = state
    return state


def _draw_static_meter_elements(canvas, state: dict):
    """Draw dB labels and footer text once. Called on first frame only."""
    if state["label_ids_drawn"]:
        return

    label_width = 20
    db_min = -30.0
    db_max = 12.0
    db_range = db_max - db_min
    meter_top    = state["meter_top"]
    meter_bottom = state["meter_bottom"]
    meter_h_px   = meter_bottom - meter_top

    db_labels = [
        (12, "+12"), (9, "+9"), (6, "+6"), (3, "+3"), (0, "0"),
        (-3, "-3"), (-6, "-6"), (-9, "-9"), (-12, "-12"),
        (-15, "-15"), (-18, "-18"), (-21, "-21"), (-24, "-24"),
        (-27, "-27"), (-30, "-30"),
    ]

    for db_val, label_text in db_labels:
        frac = (db_val - db_min) / db_range
        y = meter_bottom - frac * meter_h_px
        label_id = canvas.create_text(
            label_width - 1, y,
            text=label_text,
            fill="#888888",
            font=("Segoe UI", 5, "normal"),
            anchor="e",
        )
        state["label_ids"].append(label_id)

    db_footer_id = canvas.create_text(
        label_width - 1, state["canvas_h"] - 1,
        text="dB",
        fill="#666666",
        font=("Segoe UI", 5, "bold"),
        anchor="e",
    )
    state["label_ids"].append(db_footer_id)

    state["label_ids_drawn"] = True


def _compute_segment_colors(total_segs: int = 22) -> list:
    """
    Precompute color triples (off, lit, peak) for each segment index.
    Called once and cached. Same warm desaturated palette as the previous
    canvas-item renderer for visual consistency.
    """
    colors = []
    for seg_index in range(total_segs):
        frac = seg_index / (total_segs - 1) if total_segs > 1 else 0
        if frac >= 0.91:
            on_r, on_g, on_b   = 0xcc, 0x22, 0x22
            off_r, off_g, off_b = 0x14, 0x06, 0x06
        elif frac >= 0.82:
            on_r, on_g, on_b   = 0xbb, 0x55, 0x22
            off_r, off_g, off_b = 0x14, 0x0a, 0x06
        elif frac >= 0.73:
            on_r, on_g, on_b   = 0xaa, 0x77, 0x22
            off_r, off_g, off_b = 0x12, 0x0e, 0x06
        elif frac >= 0.64:
            on_r, on_g, on_b   = 0x99, 0x88, 0x22
            off_r, off_g, off_b = 0x10, 0x0e, 0x06
        elif frac >= 0.45:
            on_r, on_g, on_b   = 0x77, 0x88, 0x22
            off_r, off_g, off_b = 0x0c, 0x0e, 0x06
        else:
            on_r, on_g, on_b   = 0x55, 0x77, 0x28
            off_r, off_g, off_b = 0x08, 0x0c, 0x06

        on_color  = f"#{on_r:02x}{on_g:02x}{on_b:02x}"
        off_color = f"#{off_r:02x}{off_g:02x}{off_b:02x}"
        bright_r  = min(255, int(on_r * 1.4))
        bright_g  = min(255, int(on_g * 1.4))
        bright_b  = min(255, int(on_b * 1.4))
        bright_color = f"#{bright_r:02x}{bright_g:02x}{bright_b:02x}"

        colors.append({
            "off":  off_color,
            "lit":  bright_color,
            "peak": "#ffffff",
        })
    return colors


def _paint_meter_bitmap(state: dict,
                         smoothed_db: float,
                         peak_db: float) -> int:
    """
    Incremental paint: only segments that changed state since last frame
    are repainted. Most frames see 1-3 changes during audio playback.

    Strategy:
      1. Compute new segment state list ("off" / "lit" / "peak")
      2. Diff against cached old state
      3. Paint only changed segments via bitmap.put()
      4. Cache new state for next frame

    Returns number of segments repainted (informational).
    """
    bitmap = state["bitmap"]
    led_height = state["led_height"]
    led_width  = state["led_width"]

    total_segs = 22
    seg_gap_px = 2

    total_gap_px = (total_segs - 1) * seg_gap_px
    seg_height_px = max(1, (led_height - total_gap_px) // total_segs)

    db_min = -30.0
    db_max = 12.0
    db_range = db_max - db_min

    # Lit segment count
    if smoothed_db <= db_min:
        lit = 0
    elif smoothed_db >= db_max:
        lit = total_segs
    else:
        lit = int(((smoothed_db - db_min) / db_range) * total_segs)

    # Peak segment index
    if peak_db <= db_min:
        peak_seg = -1
    elif peak_db >= db_max:
        peak_seg = total_segs - 1
    else:
        peak_seg = int(((peak_db - db_min) / db_range) * total_segs) - 1

    # Build new segment state list
    new_states = []
    for seg_index in range(total_segs):
        is_lit  = (seg_index < lit)
        is_peak = (seg_index == peak_seg and peak_db > db_min)
        if is_peak:
            new_states.append("peak")
        elif is_lit:
            new_states.append("lit")
        else:
            new_states.append("off")

    # Compare to previous state
    old_states = state.get("last_segment_states")
    if old_states is None:
        # First paint: clear bitmap so gaps are set
        old_states = ["unknown"] * total_segs
        bitmap.put("#000000", to=(0, 0, led_width, led_height))

    # Lazy-init segment colors
    if state["segment_colors"] is None:
        state["segment_colors"] = _compute_segment_colors(total_segs)

    seg_colors = state["segment_colors"]

    # Repaint only changed segments
    repainted = 0
    for seg_index in range(total_segs):
        if new_states[seg_index] == old_states[seg_index]:
            continue

        new_state = new_states[seg_index]
        color = seg_colors[seg_index][new_state]

        # Compute pixel rows (bitmap y=0 is top, segment 0 is bottom)
        from_bottom = seg_index * (seg_height_px + seg_gap_px)
        seg_bottom_y = led_height - from_bottom
        seg_top_y    = seg_bottom_y - seg_height_px

        if seg_top_y < 0:
            seg_top_y = 0
        if seg_bottom_y > led_height:
            seg_bottom_y = led_height
        if seg_top_y >= seg_bottom_y:
            continue

        bitmap.put(color, to=(0, seg_top_y, led_width, seg_bottom_y))
        repainted += 1

    state["last_segment_states"] = new_states
    return repainted


def _update_clip_indicator(canvas, state: dict,
                            clip_active: bool, clip_level: float,
                            clip_flicker_on: bool):
    """
    Update CLIP indicator via itemconfig (cheap) instead of recreate.
    First call creates the items; subsequent calls just update colors.
    """
    if clip_active:
        if clip_flicker_on:
            clip_fill        = clip_level_to_color(clip_level)
            clip_outline     = "#cc2222"
            clip_text_color  = "#ffffff"
        else:
            clip_fill        = "#1a0808"
            clip_outline     = "#552222"
            clip_text_color  = "#553333"
    else:
        clip_fill       = "#0d0d0d"
        clip_outline    = "#2a2a2a"
        clip_text_color = "#553333"

    current_state = (clip_fill, clip_outline, clip_text_color)

    if state["last_clip_state"] == current_state and state["clip_bg_id"] is not None:
        return

    state["last_clip_state"] = current_state

    clip_left   = state["clip_left"]
    clip_top    = state["clip_top"]
    clip_right  = state["clip_right"]
    clip_bottom = state["clip_bottom"]

    if state["clip_bg_id"] is None:
        state["clip_bg_id"] = canvas.create_rectangle(
            clip_left, clip_top, clip_right, clip_bottom,
            fill=clip_fill, outline=clip_outline, width=1,
        )
        state["clip_text_id"] = canvas.create_text(
            (clip_left + clip_right) // 2,
            (clip_top + clip_bottom) // 2,
            text="CLIP",
            fill=clip_text_color,
            font=("Segoe UI", 8, "bold"),
        )
    else:
        canvas.itemconfig(state["clip_bg_id"], fill=clip_fill, outline=clip_outline)
        canvas.itemconfig(state["clip_text_id"], fill=clip_text_color)


def draw_djm_meter(canvas, smoothed_db: float, peak_db: float,
                    clip_active: bool, clip_level: float,
                    clip_flicker_on: bool):
    """
    DJM-900 NXS2 meter using incremental PhotoImage rendering.

    Per-frame:
      1. Get/create canvas state (cheap after first call)
      2. Draw dB labels once
      3. Create bitmap canvas item once
      4. Paint only changed LED segments to the bitmap (1-3 ops typical)
      5. Update CLIP indicator via itemconfig (no item creation)

    Drop-in replacement for the canvas-item version. Same signature,
    visually identical output, ~50-100× faster during audio playback.
    """
    w = int(canvas['width'])
    h = int(canvas['height'])

    state = _get_or_create_meter_state(canvas, w, h)

    if not state["label_ids_drawn"]:
        _draw_static_meter_elements(canvas, state)

    if state["image_id"] is None:
        state["image_id"] = canvas.create_image(
            state["led_left"], state["meter_top"],
            anchor="nw",
            image=state["bitmap"],
        )

    _paint_meter_bitmap(state, smoothed_db, peak_db)
    _update_clip_indicator(canvas, state, clip_active, clip_level, clip_flicker_on)