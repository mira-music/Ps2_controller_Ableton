"""
================================================================================
  src/ui/builder.py — Build the Tkinter UI
================================================================================
  Constructs the layout. Build B revision:

    Top area, two columns:
      ┌─────────────────────────────────────────────────────────────┐
      │  TRANSPORT BAR (full width: ■ STOPPED / ▶ PLAYING + BPM)    │
      ├──────────────────────────────────┬──────────────────────────┤
      │  LEFT: EQ + METER SECTION        │  RIGHT: NAV INFO         │
      │                                  │                          │
      │  ┌──────────┬──────────────┐    │  BMARK row               │
      │  │ METER    │  KNOBS       │    │  GROUP row               │
      │  │ COLUMN   │  COLUMN      │    │  TRACK block             │
      │  │          │              │    │  SCENE block             │
      │  │ CLIP bar │  TRIM ●      │    │  CLIP block              │
      │  │          │              │    │  Number grid             │
      │  │  +12 ▓   │  HIGH ●      │    │  Volume                  │
      │  │   +9 ▓   │              │    │  Stop button             │
      │  │   +6 ▓   │  MID  ●      │    │  Modifier pills          │
      │  │   ...    │              │    │  EQ status               │
      │  │  -30 ▓   │  LOW  ●      │    │                          │
      │  │          │              │    │                          │
      │  └──────────┴──────────────┘    │                          │
      │                                  │                          │
      ├──────────────────────────────────┴──────────────────────────┤
      │  NOTIFICATION SLOT                                           │
      ├──────────────────────────────────────────────────────────────┤
      │  FX MACHINE PANEL (full width)                               │
      ├──────────────────────────────────────────────────────────────┤
      │  CONTROLLER STATUS + REFRESH                                 │
      │  ACTION LINE                                                 │
      │  FOOTER                                                      │
      └──────────────────────────────────────────────────────────────┘

  Build B revisions to the EQ section:
    - METER moved to LEFT of knobs (was: knobs on left, meter on right)
      Matches the DJM-900 NXS2 physical layout where the channel meter
      sits on the left side of each channel strip.
    - The CLIP indicator inside the meter now spans the meter column
      width (handled in widgets.draw_djm_meter, not here).
    - TRIM knob now appears at the TOP of the knob column, then HIGH /
      MID / LOW below. This matches the DJM-900 NXS2 reference image.

  Returns a dict of widget references that update_ui() drives.
================================================================================
"""

import tkinter as tk

from src.config import (
    VERSION, EQ_SLOT_LOW, EQ_SLOT_MID, EQ_SLOT_HIGH, EQ_SLOT_TRIM,
    EQ_MACRO_COUNT,
)
from src.engine.actions import action_stop_track, action_force_refresh
from src.ui.palette import (
    ABL_BG, ABL_PANEL, ABL_PANEL_DARK, ABL_CELL, ABL_CELL_ALT, ABL_DIVIDER,
    ABL_TEXT, ABL_TEXT_DIM, ABL_TEXT_FAINT,
    ABL_ORANGE, ABL_BLUE, ABL_YELLOW, ABL_RED, ABL_PURPLE,
    LCD_BG, LCD_BG_ALT, LCD_BORDER, LCD_TEXT, LCD_TEXT_DIM, LCD_ACCENT,
    EQ_KNOB_RING_DARK,
    EQ_LABEL_COLOR,
    F_LABEL_TINY, F_LABEL_SMALL, F_BODY, F_BODY_BOLD,
    F_VALUE, F_VALUE_BIG, F_TITLE, F_TRACK_NAME, F_MONO, F_EQ_BAND,
)


# ═══════════════════════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def hline(parent, colour=ABL_DIVIDER, pady=4):
    """Thin horizontal divider line."""
    tk.Frame(parent, bg=colour, height=1).pack(fill="x", padx=10, pady=pady)


# ═══════════════════════════════════════════════════════════════════════════
#  MAIN UI BUILDER
# ═══════════════════════════════════════════════════════════════════════════

def build_ui(root):
    root.title(f"FX Machine v{VERSION}  —  MIRA___OFC / Modulated_OFC")
    root.configure(bg=ABL_BG)
    root.resizable(True, True)
    root.minsize(700, 850)
    root.attributes("-topmost", True)

    # ─── HEADER BAR ─────────────────────────────────────────────────────
    hdr = tk.Frame(root, bg=ABL_PANEL_DARK)
    hdr.pack(fill="x")
    inner = tk.Frame(hdr, bg=ABL_PANEL_DARK)
    inner.pack(fill="x", padx=10, pady=6)
    tk.Label(inner, text="FX MACHINE",
             bg=ABL_PANEL_DARK, fg=ABL_TEXT,
             font=("Segoe UI", 11, "bold"), anchor="w").pack(side="left")
    tk.Label(inner, text=f"v{VERSION}",
             bg=ABL_PANEL_DARK, fg=ABL_TEXT_DIM,
             font=F_LABEL_TINY, anchor="e").pack(side="right")
    tk.Frame(root, bg=ABL_BLUE, height=2).pack(fill="x")

    # ─── TRANSPORT BAR ──────────────────────────────────────────────────
    trow = tk.Frame(root, bg=ABL_BG)
    trow.pack(fill="x", padx=10, pady=(6, 0))
    lbl_playing = tk.Label(trow, text="■ STOPPED", bg=ABL_BG, fg=ABL_RED,
                           font=F_VALUE, anchor="w")
    lbl_playing.pack(side="left")
    lbl_bpm = tk.Label(trow, text="120.0 BPM", bg=ABL_BG, fg=ABL_TEXT,
                       font=F_MONO, anchor="e")
    lbl_bpm.pack(side="right")

    hline(root, pady=5)

    # ══════════════════════════════════════════════════════════════════
    #  TOP TWO-COLUMN AREA: EQ + METER (left) | NAV INFO (right)
    # ══════════════════════════════════════════════════════════════════
    top_area = tk.Frame(root, bg=ABL_BG)
    top_area.pack(fill="x", padx=8)

    # ─────── LEFT COLUMN: EQ SECTION (METER + KNOBS) ─────────────────
    eq_section = tk.Frame(top_area, bg=ABL_BG)
    eq_section.pack(side="left", fill="y", padx=(0, 8))

    # Section title row (above the framed container)
    eq_title_row = tk.Frame(eq_section, bg=ABL_BG)
    eq_title_row.pack(fill="x", pady=(0, 2))
    lbl_eq_title = tk.Label(eq_title_row, text="◇ EQ",
                            bg=ABL_BG, fg=ABL_TEXT,
                            font=F_LABEL_SMALL, anchor="w")
    lbl_eq_title.pack(side="left")
    lbl_eq_track = tk.Label(eq_title_row, text="—",
                            bg=ABL_BG, fg=ABL_TEXT_DIM,
                            font=F_LABEL_TINY, anchor="e")
    lbl_eq_track.pack(side="right")

    # Framed container around the meter + knobs (gives a visual border)
    eq_glow = tk.Frame(eq_section, bg=EQ_KNOB_RING_DARK, padx=2, pady=2)
    eq_glow.pack(fill="y")
    eq_body = tk.Frame(eq_glow, bg=ABL_PANEL_DARK)
    eq_body.pack(fill="y")

    # ── Inside eq_body, two sub-columns:
    # ── LEFT sub-column  = DJM channel meter (new position, was on right)
    # ── RIGHT sub-column = TRIM / HIGH / MID / LOW knobs vertical stack
    #
    # Layout matches DJM-900 NXS2 hardware: meter sits to the LEFT of
    # the channel strip's EQ knobs.

    # Constants used to size both sub-columns
    EQ_KNOB_SIZE = 82
    # Meter height needs to span 4 knob cells (TRIM + HIGH + MID + LOW),
    # each cell is approximately (KNOB_SIZE + label + value + padding).
    # The +38 accounts for: name label (~14px) + value label (~14px) +
    # cell pady (5*2=10px). The *4 covers all four cells. +10 is breathing room.
    meter_h = (EQ_KNOB_SIZE + 38) * 4 + 10

    # ──────── METER COLUMN (LEFT) ──────────
    meter_col = tk.Frame(eq_body, bg=ABL_PANEL_DARK, padx=4, pady=2)
    meter_col.pack(side="left", fill="y")

    tk.Label(meter_col, text="OUT", bg=ABL_PANEL_DARK,
             fg=ABL_TEXT_DIM, font=F_LABEL_TINY).pack(pady=(2, 4))

    # Width increased from 42 → 58 to accommodate the WIDE CLIP bar
    # (CLIP now spans the full meter column width, see widgets.draw_djm_meter).
    eq_channel_meter = tk.Canvas(meter_col, width=66, height=meter_h,
                                  bg=ABL_PANEL_DARK, highlightthickness=0)
    eq_channel_meter.pack(pady=(0, 2))

    # ──────── KNOBS COLUMN (RIGHT) ──────────
    knobs_col = tk.Frame(eq_body, bg=ABL_PANEL_DARK)
    knobs_col.pack(side="left", fill="y", padx=2, pady=2)

    eq_cells = [None] * EQ_MACRO_COUNT

    # Display order top-to-bottom: TRIM, HIGH, MID, LOW (DJM-900 NXS2 layout)
    display_order = [EQ_SLOT_TRIM, EQ_SLOT_HIGH, EQ_SLOT_MID, EQ_SLOT_LOW]
    display_labels = {
        EQ_SLOT_LOW:  "LOW",
        EQ_SLOT_MID:  "MID",
        EQ_SLOT_HIGH: "HIGH",
        EQ_SLOT_TRIM: "TRIM",
    }

    for band_idx in display_order:
        cell = tk.Frame(knobs_col, bg=ABL_CELL, padx=6, pady=5)
        cell.pack(fill="x", pady=1)

        name_lbl = tk.Label(cell, text=display_labels[band_idx],
                            bg=ABL_CELL, fg=EQ_LABEL_COLOR,
                            font=F_EQ_BAND, anchor="center")
        name_lbl.pack(fill="x", pady=(0, 1))

        canvas = tk.Canvas(cell, width=EQ_KNOB_SIZE, height=EQ_KNOB_SIZE,
                           bg=ABL_CELL, highlightthickness=0)
        canvas.pack()

        value_lbl = tk.Label(cell, text="0.00 dB", bg=ABL_CELL,
                             fg=ABL_TEXT, font=F_VALUE, anchor="center")
        value_lbl.pack(fill="x", pady=(1, 0))

        eq_cells[band_idx] = (cell, canvas, name_lbl, value_lbl)

    # ─────── RIGHT COLUMN: TN / TERMINAL SESSION NAVIGATOR ───────────
    # The live display is a custom Canvas renderer. It keeps the navigation
    # module readable while adding restrained TN scanlines, afterimages, and
    # small status backlights; all text remains dynamic application data.
    nav_section = tk.Frame(top_area, bg=LCD_BORDER, padx=2, pady=2)
    nav_section.pack(side="left", fill="both", expand=True)
    session_lcd = tk.Canvas(nav_section, width=510, height=255,
                            bg=LCD_BG, highlightthickness=0)
    session_lcd.pack(fill="both", expand=True)

    # Compatibility widgets retain the existing updater's label writes during
    # this first renderer migration. They are deliberately not packed; the
    # Canvas above is the only visible Navigator implementation.
    compat = tk.Frame(nav_section, bg=LCD_BG)
    def hidden_label():
        return tk.Label(compat, bg=LCD_BG)

    lbl_bookmark = hidden_label()
    lbl_bm_pos = hidden_label()
    lbl_group = hidden_label()
    lbl_group_pos = hidden_label()
    track_block = compat
    lbl_track_name = hidden_label()
    lbl_scene_name = hidden_label()
    lbl_clip_name = hidden_label()
    lbl_scene_num = hidden_label()
    lbl_track_num = hidden_label()
    lbl_bm_num = hidden_label()
    lbl_volume = hidden_label()
    lbl_vol_mode = hidden_label()
    lbl_r2 = hidden_label()
    lbl_select = hidden_label()
    lbl_start = hidden_label()
    lbl_l1 = hidden_label()
    lbl_eq_pill = hidden_label()
    lbl_eq_status = hidden_label()

    hline(root, pady=6)

    # ══════════════════════════════════════════════════════════════════
    #  NOTIFICATION SLOT
    #  Dedicated area for transient warnings (config errors, clipping
    #  alerts, restart-required notices). Separate from the action line
    #  at the bottom so important warnings aren't overwritten by
    #  routine activity messages.
    # ══════════════════════════════════════════════════════════════════
    notif_frame = tk.Frame(root, bg=ABL_BG)
    notif_frame.pack(fill="x", padx=8, pady=(0, 2))
    lbl_notification = tk.Label(
        notif_frame,
        text="",
        bg=ABL_BG,
        fg=ABL_TEXT_FAINT,
        font=F_LABEL_SMALL,
        anchor="w",
    )
    lbl_notification.pack(fill="x")

    # ══════════════════════════════════════════════════════════════════
    #  FX MACHINE PANEL (full width)
    # ══════════════════════════════════════════════════════════════════
    fx_section = tk.Frame(root, bg=ABL_BG)
    fx_section.pack(fill="x", padx=8, pady=(0, 2))

    fx_title_row = tk.Frame(fx_section, bg=ABL_BG)
    fx_title_row.pack(fill="x", pady=(0, 1))
    lbl_fx_title = tk.Label(fx_title_row, text="⚡ FX MACHINE",
                            bg=ABL_BG, fg=ABL_TEXT,
                            font=F_LABEL_SMALL, anchor="w")
    lbl_fx_title.pack(side="left")
    lbl_fx_track = tk.Label(fx_title_row, text="—",
                            bg=ABL_BG, fg=ABL_TEXT_DIM,
                            font=F_LABEL_TINY, anchor="e")
    lbl_fx_track.pack(side="right")

    fx_status_row = tk.Frame(fx_section, bg=ABL_BG)
    fx_status_row.pack(fill="x", pady=(0, 2))
    lbl_baseline = tk.Label(fx_status_row, text="✗ no baseline",
                            bg=ABL_BG, fg=ABL_TEXT_FAINT,
                            font=F_LABEL_TINY, anchor="w")
    lbl_baseline.pack(side="left")
    lbl_lock_wet = tk.Label(fx_status_row, text="wet: free",
                            bg=ABL_BG, fg=ABL_TEXT_FAINT,
                            font=F_LABEL_TINY, anchor="e")
    lbl_lock_wet.pack(side="right", padx=(0, 4))
    lbl_lock_filter = tk.Label(fx_status_row, text="filter: free",
                               bg=ABL_BG, fg=ABL_TEXT_FAINT,
                               font=F_LABEL_TINY, anchor="e")
    lbl_lock_filter.pack(side="right", padx=(0, 4))

    fx_glow = tk.Frame(fx_section, bg=ABL_BG, padx=2, pady=2)
    fx_glow.pack(fill="x")
    fx_inner = tk.Frame(fx_glow, bg=ABL_BG)
    fx_inner.pack(fill="x")

    fx_cells = []
    KNOB_SIZE = 56

    def make_knob_cell(parent, row, col, accent):
        cell = tk.Frame(parent, bg=ABL_CELL, padx=2, pady=2)
        cell.grid(row=row, column=col, padx=1, pady=1, sticky="nsew")
        parent.columnconfigure(col, weight=1)

        tk.Frame(cell, bg=accent, height=2).pack(fill="x")

        canvas = tk.Canvas(cell, width=KNOB_SIZE, height=KNOB_SIZE,
                           bg=ABL_CELL, highlightthickness=0)
        canvas.pack(pady=(2, 1))

        name_lbl = tk.Label(cell, text="—", bg=ABL_CELL, fg=ABL_TEXT_DIM,
                            font=F_LABEL_TINY, anchor="center")
        name_lbl.pack(fill="x")
        value_lbl = tk.Label(cell, text="--", bg=ABL_CELL, fg=accent,
                             font=F_VALUE, anchor="center")
        value_lbl.pack(fill="x")

        return cell, canvas, name_lbl, value_lbl

    # Two rows of 4 FX knobs each
    for col in range(4):
        fx_cells.append(make_knob_cell(fx_inner, 0, col, ABL_ORANGE))
    for col in range(4):
        fx_cells.append(make_knob_cell(fx_inner, 1, col, ABL_BLUE))

    hline(root, pady=4)

    # ── Controller status + refresh button ──
    bot_row = tk.Frame(root, bg=ABL_BG)
    bot_row.pack(fill="x", padx=8, pady=(0, 2))

    lbl_ctrl = tk.Label(bot_row, text="● NO CTRL",
                        bg=ABL_PANEL, fg=ABL_RED,
                        font=F_LABEL_TINY, padx=5, pady=3)
    lbl_ctrl.pack(side="left")

    tk.Button(bot_row, text="⟳ REFRESH",
              bg=ABL_PANEL, fg=ABL_BLUE, font=F_LABEL_TINY,
              activebackground="#002a2a", activeforeground=ABL_BLUE,
              relief="flat", bd=0, pady=3, padx=8, cursor="hand2",
              command=action_force_refresh).pack(side="right")

    hline(root, pady=3)

    # ── Action line ──
    lbl_action = tk.Label(root, text="System ready",
                          bg=ABL_BG, fg=ABL_TEXT_DIM,
                          font=F_BODY, anchor="w")
    lbl_action.pack(fill="x", padx=10, pady=(0, 2))

    # ── Footer ──
    footer = tk.Label(root,
                      text="MIRA___OFC  ·  Modulated_OFC  ·  © Ayoub Agoujdad",
                      bg=ABL_BG, fg=ABL_TEXT_FAINT,
                      font=("Segoe UI", 7, "normal"), anchor="center")
    footer.pack(fill="x", padx=10, pady=(0, 4))

    return {
        "playing":          lbl_playing,
        "bpm":              lbl_bpm,
        "bookmark":         lbl_bookmark,
        "bm_pos":           lbl_bm_pos,
        "group":            lbl_group,
        "group_pos":        lbl_group_pos,
        "track_block":      track_block,
        "track_name":       lbl_track_name,
        "scene_name":       lbl_scene_name,
        "clip_name":        lbl_clip_name,
        "scene_num":        lbl_scene_num,
        "track_num":        lbl_track_num,
        "bm_num":           lbl_bm_num,
        "volume":           lbl_volume,
        "vol_mode":         lbl_vol_mode,
        "r2":               lbl_r2,
        "select":           lbl_select,
        "start":            lbl_start,
        "l1":               lbl_l1,
        "eq_pill":          lbl_eq_pill,
        "ctrl":             lbl_ctrl,
        "action":           lbl_action,
        "fx_title":         lbl_fx_title,
        "fx_track":         lbl_fx_track,
        "fx_glow":          fx_glow,
        "fx_cells":         fx_cells,
        "baseline":         lbl_baseline,
        "lock_filter":      lbl_lock_filter,
        "lock_wet":         lbl_lock_wet,
        "eq_title":         lbl_eq_title,
        "eq_track":         lbl_eq_track,
        "eq_glow":          eq_glow,
        "eq_cells":         eq_cells,
        "eq_status":        lbl_eq_status,
        "notification":     lbl_notification,
        "eq_channel_meter": eq_channel_meter,
        "session_lcd":      session_lcd,
    }