"""
================================================================================
  src/ui/widgets.py — Canvas Renderers + Dirty-Cache Label Setter
================================================================================
  Three canvas-based renderers, each with its own dirty cache to avoid
  redrawing when nothing has changed:

    draw_knob()           — FX macro knob (270° arc + body + indicator)
    draw_eq_knob()        — DJM-900 metallic EQ knob with dB labels
    draw_trim_knob()      — Same metallic style but -∞/0/+9 range labels
    draw_channel_meter()  — 24-segment DJM channel meter with peak (legacy)
    draw_djm_meter()      — Build B Phase 4: 22-segment DJM-900 NXS2 meter
    update_meter_peak()   — Legacy peak hold/decay logic (0-1 scale)

  Build B Phase 2 math functions (compute only, no drawing):
    raw_meter_to_display_db()
    apply_meter_ballistics()
    update_meter_peak_db()
    compute_clip_state()
    should_clip_flicker()
    clip_level_to_color()
    display_db_to_segment()
    segment_color()

  Plus set_label() — diff-based widget update to minimize Tk traffic.

  Fixes applied:
    - Removed redundant "import math as _math" and "from config_loader import cfg as _cfg"
      that were duplicating top-level imports. All Phase 2/4 code now uses the
      top-level `math` and `cfg` names consistently.
    - Moved _rounded_rect() above draw_djm_meter() so it is defined before use
      (was defined after, which works at call time in Python but hurts readability
      and violates the principle that helpers precede their callers).
    - draw_djm_meter() get_seg_colors() inner function documented as intentional
      closure over local `total_segs`.
================================================================================
"""

import math

from src.config import (
    EQ_METER_SEGMENTS, EQ_METER_GREEN, EQ_METER_YELLOW, EQ_METER_RED,
    EQ_METER_PEAK_HOLD_S, EQ_METER_PEAK_FALL,
    EQ_MACRO_MIN, EQ_MACRO_MAX, EQ_NEUTRAL_MACRO,
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
    """
    Update a Tkinter Label only when its text or style has actually changed.
    Avoids the per-frame Tk config() call overhead when nothing is different.
    """
    cache_key = (key, text, tuple(sorted(kwargs.items())))
    if _ui_cache.get(key) != cache_key:
        widget.config(text=text, **kwargs)
        _ui_cache[key] = cache_key


# ═══════════════════════════════════════════════════════════════════════════
#  FX KNOB
# ═══════════════════════════════════════════════════════════════════════════

_knob_cache = {}

def draw_knob(canvas, slot, value_frac, color, active=False, locked=False, moment=False):
    """
    FX macro knob: 270° arc background + active arc + body circle + indicator line.

    value_frac: 0.0 (minimum) to 1.0 (maximum)
    color:      accent color for the arc and indicator
    active:     knob is currently being moved (yellow highlight)
    locked:     knob is filter/wet locked (blue tint)
    moment:     momentary effect active (red highlight)
    """
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

    # Background arc (full 270° sweep, dark grey)
    canvas.create_arc(
        cx - r_outer, cy - r_outer,
        cx + r_outer, cy + r_outer,
        start=225, extent=-270,
        style="arc", outline=ABL_DIVIDER, width=2
    )

    # Active arc (fills clockwise from 7 o'clock by value_frac)
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

    # Body circle fill
    if moment:
        body_fill    = ABL_CELL_MOMENT
        body_outline = ABL_RED
    elif locked:
        body_fill    = ABL_CELL_LOCK
        body_outline = ABL_YELLOW
    elif active:
        body_fill    = ABL_CELL_HOT
        body_outline = ABL_YELLOW
    else:
        body_fill    = "#2a2a2a"
        body_outline = "#444444"

    canvas.create_oval(
        cx - r_inner, cy - r_inner,
        cx + r_inner, cy + r_inner,
        fill=body_fill, outline=body_outline
    )

    # Indicator line (points toward current value)
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

    visual_pos: 0.0 = -∞ dB (far left / 7 o'clock)
                0.5 = 0 dB  (top / 12 o'clock)
                1.0 = +6 dB (far right / 5 o'clock)

    The active arc draws FROM 12 o'clock TOWARD the current position,
    showing boost (right of center) or cut (left of center) symmetrically.
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

    # Background arc (full 270° sweep)
    canvas.create_arc(
        cx - r_ring, cy - r_ring,
        cx + r_ring, cy + r_ring,
        start=225, extent=-270,
        style="arc", outline=EQ_KNOB_ARC_BG, width=2
    )

    # Active arc: draws from 12 o'clock toward current position.
    # Cut (visual_pos < 0.5): arc sweeps CCW (positive extent from 90°)
    # Boost (visual_pos > 0.5): arc sweeps CW (negative extent from 90°)
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

    # Perimeter tick marks every 30° (10 ticks across the 270° sweep)
    for tick_angle_deg in range(225, -46, -30):
        tick_rad = math.radians(tick_angle_deg)
        outer_x = cx + (r_ring + 1) * math.cos(tick_rad)
        outer_y = cy - (r_ring + 1) * math.sin(tick_rad)
        inner_x = cx + (r_ring - 2) * math.cos(tick_rad)
        inner_y = cy - (r_ring - 2) * math.sin(tick_rad)
        canvas.create_line(inner_x, inner_y, outer_x, outer_y,
                           fill=EQ_KNOB_BODY_LIGHT, width=1)

    # Prominent center detent mark at 12 o'clock
    canvas.create_line(cx, cy - (r_ring + 2), cx, cy - (r_ring - 3),
                       fill=EQ_KNOB_DETENT, width=2)

    # dB range labels at the three key positions
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

    # Metallic body — three concentric ovals for depth illusion
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

    # Selected/armed glow ring (drawn on top of the mid body)
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

    # Light highlight ring
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

    # Center cap (darkest circle, sits on top of everything)
    canvas.create_oval(
        cx - r_cap, cy - r_cap,
        cx + r_cap, cy + r_cap,
        fill=EQ_KNOB_BODY_DARK, outline=EQ_KNOB_BODY_RIM, width=1
    )


# ═══════════════════════════════════════════════════════════════════════════
#  TRIM KNOB — same metallic style, different range labels (-∞ / 0 / +9)
# ═══════════════════════════════════════════════════════════════════════════

_trim_knob_cache = {}

def draw_trim_knob(canvas, band_idx, visual_pos, selected=False, armed=False):
    """
    TRIM knob: identical metallic DJM-900 style as draw_eq_knob, but with
    -∞/0/+9 range labels instead of -∞/0/+6.

    visual_pos: 0.0 = -∞ dB, 0.5 = 0 dB (TRIM neutral at macro 64.0), 1.0 = +9 dB cap
    """
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

    canvas.create_line(
        cx, cy - (r_ring + 2),
        cx, cy - (r_ring - 3),
        fill=EQ_KNOB_DETENT, width=2
    )

    # TRIM-specific range labels: -∞, 0, +9
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
#  DJM CHANNEL METER — Legacy 24-segment (active until Phase 4 replaces it)
# ═══════════════════════════════════════════════════════════════════════════

_channel_meter_cache = {}

def draw_channel_meter(canvas, level, peak_level):
    """
    Legacy DJM-900 style 24-segment channel meter.
    level:      current audio level (0.0 to 1.0 raw)
    peak_level: held peak (0.0 to 1.0 raw) — bright white indicator segment

    Color zones (bottom to top):
      Segments 0-14:  green  (safe)
      Segments 15-20: yellow (loud)
      Segments 21-23: red    (clipping zone)
    """
    cache_key = (round(level, 3), round(peak_level, 3))
    if _channel_meter_cache.get("k") == cache_key:
        return
    _channel_meter_cache["k"] = cache_key

    canvas.delete("all")

    w = int(canvas['width'])
    h = int(canvas['height'])

    total = EQ_METER_SEGMENTS    # 24
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
    """
    Legacy peak hold + decay logic (0.0-1.0 raw scale).
    Returns (new_peak, new_peak_time).

    Three states:
      1. current >= last_peak  → capture new peak
      2. Within hold window    → keep held peak
      3. Hold expired          → linear decay at EQ_METER_PEAK_FALL dB/s
    """
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
#
#  These functions compute values only — no drawing.
#  The UI updater calls them every frame and stores results in state.
#  draw_djm_meter() (Phase 4) reads state to render.
#
#  All references use the top-level `math` and `cfg` imports.
#  (Previously had a redundant "import math as _math" and
#  "from src.config_loader import cfg as _cfg" — both removed.)
# ═══════════════════════════════════════════════════════════════════════════

def raw_meter_to_display_db(raw_value):
    """
    Convert Ableton's raw meter output (0.0 to 1.0) to display dB.

    Ableton's output_meter values are normalized peak levels:
      raw 1.0 = 0 dBFS (digital clipping ceiling)
      raw 0.5 = ~-6 dBFS
      raw 0.0 = -∞ dBFS

    We convert to dBFS, then add a reference offset so the display
    reads in DJ-friendly terms:
      display_dB = 20*log10(raw) + cfg.METER_REFERENCE_OFFSET_DB

    With default offset of 18:
      -18 dBFS (typical headroom) → display 0
      0 dBFS (digital ceiling)   → display +18

    Returns display dB clamped to [-60, +15].
    """
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
    """
    Apply meter ballistics (release decay only — attack is instant).

    Attack:  instant (if current > smoothed, snap immediately)
    Release: linear decay at cfg.METER_RELEASE_DB_PER_SEC

    This mimics real analog VU meters where the needle rises instantly
    but falls slowly, making transient peaks readable.

    Args:
        current_db:           latest display dB value
        previous_smoothed_db: smoothed value from the last frame
        dt:                   time since last frame (seconds)

    Returns: new smoothed dB value
    """
    if current_db >= previous_smoothed_db:
        return current_db
    decay = cfg.METER_RELEASE_DB_PER_SEC * dt
    smoothed = previous_smoothed_db - decay
    if smoothed < current_db:
        return current_db
    return smoothed


def update_meter_peak_db(current_db, last_peak_db, last_peak_time, now):
    """
    Peak hold logic for the dB-scale meter peak indicator.

    Three states:
      1. New peak  → capture (current >= held peak)
      2. Hold      → maintain for cfg.METER_PEAK_HOLD_SECONDS
      3. Decay     → fall at cfg.METER_PEAK_FALL_DB_PER_SEC

    Args:
        current_db:     current smoothed display dB
        last_peak_db:   held peak dB from previous frame
        last_peak_time: timestamp when peak was captured
        now:            current time

    Returns: (new_peak_db, new_peak_time)
    """
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
    """
    Compute the CLIP indicator state.

    Two thresholds with smooth interpolation between them:
      cfg.METER_CLIP_WARN_DB     (default +6)  → clip_level = 0.0 (yellow)
      cfg.METER_CLIP_CRITICAL_DB (default +9)  → clip_level = 1.0 (red)

    After level drops below warn_db, CLIP stays active for
    cfg.METER_CLIP_FADEOUT_SECONDS then fades out.

    Returns: (is_active, clip_level, new_last_active_time)
      is_active:  bool — should CLIP indicator be visible
      clip_level: 0.0-1.0 color interpolation (0=yellow, 1=red)
      new_last_active_time: updated timestamp
    """
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
    """
    Whether the CLIP indicator should be in its bright phase this frame.

    Only flickers when clip_level >= 0.5 (approaching critical threshold).
    Below 0.5: solid on (warning zone, no flicker).
    At/above 0.5: square-wave flicker at cfg.METER_CLIP_FLICKER_HZ.

    Args:
        clip_level: 0.0-1.0 from compute_clip_state
        now:        current time (time.perf_counter())

    Returns: True = bright this frame, False = dim this frame
    """
    if clip_level < 0.5:
        return True

    hz = cfg.METER_CLIP_FLICKER_HZ
    if hz <= 0:
        return True

    cycle_s = 1.0 / hz
    position_in_cycle = (now % cycle_s) / cycle_s
    return position_in_cycle < 0.5


def clip_level_to_color(clip_level):
    """
    Convert clip_level (0.0 to 1.0) to an RGB hex color string.

    Smooth gradient through three stops:
      0.0 → yellow   (#f4d22b)
      0.5 → orange   (#ff6c2c)
      1.0 → red      (#ff3b30)

    Linear interpolation in RGB space between stops.

    Args:
        clip_level: 0.0 (warning/yellow) to 1.0 (critical/red)

    Returns: hex color string like "#ff6c2c"
    """
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
    """
    Convert display dB to a lit segment count (0 = bottom, total_segments = full).

    The 15-segment meter covers -30 dB to +12 dB (3 dB per segment).

    Returns: int number of segments that should be lit (0 to total_segments)
    """
    if display_db <= db_min:
        return 0
    if display_db >= db_max:
        return total_segments
    fraction = (display_db - db_min) / (db_max - db_min)
    return int(fraction * total_segments)


def segment_color(segment_index, total_segments=15):
    """
    Returns (on_color, off_color) for a given segment index in the DJM-900 meter.

    Color zones (bottom to top, 15 segments, -30 to +12 dB):
      Segments 0-9   (-30 to -3 dB)  → yellow-green
      Segments 10-12 (0 to +6 dB)    → orange
      Segment 13     (+9 dB)          → orange-red
      Segment 14     (+12 dB, top)    → red
    """
    if segment_index >= 14:
        return "#ee2222", "#1e0c0c"
    elif segment_index >= 13:
        return "#ee6622", "#1e120c"
    elif segment_index >= 10:
        return "#eeaa22", "#1e1a0c"
    else:
        return "#88cc22", "#0c1e0c"


# ═══════════════════════════════════════════════════════════════════════════
#  ROUNDED RECTANGLE HELPER
#
#  Defined BEFORE draw_djm_meter (which calls it) so the code reads
#  top-to-bottom in dependency order.
# ═══════════════════════════════════════════════════════════════════════════

def _rounded_rect(canvas, x1, y1, x2, y2, radius=3, fill="#000000", outline=""):
    """
    Draw a rectangle with rounded corners using overlapping primitives.

    Tkinter's canvas has no native rounded-rect, so we simulate it with:
      - 2 overlapping rectangles (horizontal and vertical main bodies)
      - 4 ovals at the corners
      - Optional outline arcs and lines if outline != ""

    This creates (6 + optional 8) = up to 14 canvas items per call.
    Callers (draw_djm_meter) should cache the parent canvas output
    to avoid recreating these on every frame.
    """
    r = min(radius, abs(x2 - x1) // 2, abs(y2 - y1) // 2)
    if r < 1:
        canvas.create_rectangle(x1, y1, x2, y2, fill=fill, outline=outline, width=0)
        return

    # Main fill bodies
    canvas.create_rectangle(x1 + r, y1, x2 - r, y2, fill=fill, outline="", width=0)
    canvas.create_rectangle(x1, y1 + r, x2, y2 - r, fill=fill, outline="", width=0)

    # Corner ovals
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
#  BUILD B PHASE 4 — DJM-900 NXS2 METER (22 segments, CLIP indicator)
# ═══════════════════════════════════════════════════════════════════════════

_djm_meter_cache = {}

def draw_djm_meter(canvas, smoothed_db, peak_db, clip_active, clip_level, clip_flicker_on):
    """
    Draw DJM-900 NXS2 style channel meter.

    Layout (top to bottom):
      CLIP indicator box  (16px high)
      8px gap
      22 LED segments     (from -30 dB at bottom to +12 dB at top)
      dB labels           (on the left side, 20px wide)

    Each LED is rendered as 3 horizontal stripes:
      top stripe:    edge color (darker)
      center stripe: bright color (lighter)
      bottom stripe: edge color (darker)
    This simulates the center-glow of real LED segments.

    Warm desaturated color palette (matches DJM-900 reference image):
      Bottom (green-yellow) → Middle (yellow-orange) → Top (red)

    Args:
        smoothed_db:      ballistics-smoothed display dB for lit segments
        peak_db:          held peak dB for the peak indicator segment
        clip_active:      bool — show CLIP indicator
        clip_level:       0.0-1.0 color intensity of CLIP
        clip_flicker_on:  bool — CLIP bright phase (from should_clip_flicker)
    """
    cache_key = (
        round(smoothed_db, 1),
        round(peak_db, 1),
        clip_active,
        round(clip_level, 2),
        clip_flicker_on,
    )
    if _djm_meter_cache.get("m") == cache_key:
        return
    _djm_meter_cache["m"] = cache_key

    canvas.delete("all")

    w = int(canvas['width'])
    h = int(canvas['height'])

    # Layout constants
    label_width = 20          # width reserved for dB labels on left
    led_left  = label_width + 3
    led_right = led_left + 8  # LED bar is 8px wide

    # CLIP box geometry
    clip_h      = 16
    clip_top    = 2
    clip_bottom = clip_top + clip_h
    clip_left   = led_left - 2
    clip_right  = w - 2

    # Gap between CLIP box and top of meter segments
    clip_to_meter_gap = 8

    # Meter segment geometry
    total_segs  = 22
    seg_gap     = 5           # pixels between LED segments
    meter_top    = clip_bottom + clip_to_meter_gap
    meter_bottom = h - 4
    meter_h_px   = meter_bottom - meter_top
    seg_h = max(3.0, (meter_h_px - (total_segs - 1) * seg_gap) / total_segs)

    # dB range
    db_min   = -30.0
    db_max   = 12.0
    db_range = db_max - db_min

    # ── CLIP indicator ──────────────────────────────────────────────────
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
        clip_text_color = "#2a2a2a"

    _rounded_rect(canvas, clip_left, clip_top, clip_right, clip_bottom,
                  radius=3, fill=clip_fill, outline=clip_outline)
    canvas.create_text(
        (clip_left + clip_right) // 2,
        (clip_top + clip_bottom) // 2,
        text="CLIP", fill=clip_text_color,
        font=("Segoe UI", 7, "bold")
    )

    # ── Lit segment count ───────────────────────────────────────────────
    if smoothed_db <= db_min:
        lit = 0
    elif smoothed_db >= db_max:
        lit = total_segs
    else:
        lit = int(((smoothed_db - db_min) / db_range) * total_segs)

    # ── Peak segment index ──────────────────────────────────────────────
    if peak_db <= db_min:
        peak_seg = -1
    elif peak_db >= db_max:
        peak_seg = total_segs - 1
    else:
        peak_seg = int(((peak_db - db_min) / db_range) * total_segs) - 1

    # ── Segment color palette ───────────────────────────────────────────
    def get_seg_colors(seg_index):
        """
        Returns (on_color, off_color, bright_color) for segment seg_index.

        Warm desaturated gradient from green-yellow (bottom) to red (top).
        bright_color is on_color amplified by 1.4× for the center stripe.

        This is an inner function because it closes over total_segs (a local
        constant). It is not a module-level function because it would need
        total_segs passed as a parameter, adding noise at every call site.
        """
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

        bright_r = min(255, int(on_r * 1.4))
        bright_g = min(255, int(on_g * 1.4))
        bright_b = min(255, int(on_b * 1.4))
        bright_color = f"#{bright_r:02x}{bright_g:02x}{bright_b:02x}"

        return on_color, off_color, bright_color

    # ── Draw LED segments (bottom = segment 0, top = segment 21) ───────
    for i in range(total_segs):
        seg_bottom = meter_bottom - i * (seg_h + seg_gap)
        seg_top    = seg_bottom - seg_h

        on_color, off_color, bright_color = get_seg_colors(i)

        is_lit  = (i < lit)
        is_peak = (i == peak_seg and peak_db > db_min)

        if is_peak:
            edge_color   = "#bbbbbb"
            center_color = "#ffffff"
        elif is_lit:
            edge_color   = on_color
            center_color = bright_color
        else:
            edge_color   = off_color
            center_color = off_color

        # Three-stripe LED rendering
        third = max(1.0, seg_h / 3.0)

        _rounded_rect(canvas,
                      led_left, seg_top,
                      led_right, seg_top + third,
                      radius=2, fill=edge_color)

        canvas.create_rectangle(
            led_left, seg_top + third,
            led_right, seg_bottom - third,
            fill=center_color, outline="", width=0
        )

        _rounded_rect(canvas,
                      led_left, seg_bottom - third,
                      led_right, seg_bottom,
                      radius=2, fill=edge_color)

    # ── dB labels on the left ───────────────────────────────────────────
    db_labels = [
        (12, "+12"), (9, "+9"), (6, "+6"), (3, "+3"), (0, "0"),
        (-3, "-3"), (-6, "-6"), (-9, "-9"), (-12, "-12"),
        (-15, "-15"), (-18, "-18"), (-21, "-21"), (-24, "-24"),
        (-27, "-27"), (-30, "-30"),
    ]

    for db_val, label_text in db_labels:
        frac = (db_val - db_min) / db_range
        y    = meter_bottom - frac * meter_h_px
        canvas.create_text(
            label_width - 1, y,
            text=label_text,
            fill="#888888",
            font=("Segoe UI", 5, "normal"),
            anchor="e"
        )

    canvas.create_text(
        label_width - 1, h - 1,
        text="dB",
        fill="#666666",
        font=("Segoe UI", 5, "bold"),
        anchor="e"
    )