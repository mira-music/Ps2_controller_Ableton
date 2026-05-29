"""
================================================================================
  src/ui/builder.py — Build the Tkinter UI
================================================================================
  Constructs the v9.10+ two-column layout:
    LEFT  — EQ stack (HIGH/MID/LOW vertical) + big DJM channel meter
    RIGHT — Session navigation info (bookmarks, group, track, scene,
            clip, number grid, volume, stop button, modifier pills,
            EQ status line)
    FX panel below (full width) — 8 macro knobs in 2 rows of 4

  Returns a dict of widget references that update_ui() drives.
================================================================================
"""

import tkinter as tk

from src.config import (
    VERSION, EQ_SLOT_LOW, EQ_SLOT_MID, EQ_SLOT_HIGH,
)
from src.engine.actions import action_stop_track, action_force_refresh
from src.ui.palette import (
    ABL_BG, ABL_PANEL, ABL_PANEL_DARK, ABL_CELL, ABL_CELL_ALT, ABL_DIVIDER,
    ABL_TEXT, ABL_TEXT_DIM, ABL_TEXT_FAINT,
    ABL_ORANGE, ABL_BLUE, ABL_YELLOW, ABL_RED, ABL_PURPLE,
    EQ_KNOB_RING_DARK,
    EQ_LABEL_COLOR,
    F_LABEL_TINY, F_LABEL_SMALL, F_BODY, F_BODY_BOLD,
    F_VALUE, F_VALUE_BIG, F_TITLE, F_TRACK_NAME, F_MONO, F_EQ_BAND,
)

# ═══════════════════════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def hline(parent, colour=ABL_DIVIDER, pady=4):
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

    # ── HEADER ──
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

    # ── TRANSPORT ──
    trow = tk.Frame(root, bg=ABL_BG)
    trow.pack(fill="x", padx=10, pady=(6, 0))
    lbl_playing = tk.Label(trow, text="■ STOPPED", bg=ABL_BG, fg=ABL_RED,
                           font=F_VALUE, anchor="w")
    lbl_playing.pack(side="left")
    lbl_bpm = tk.Label(trow, text="120.0 BPM", bg=ABL_BG, fg=ABL_TEXT,
                       font=F_MONO, anchor="e")
    lbl_bpm.pack(side="right")

    hline(root, pady=5)

    # ══════════════════════════════════════════════════════════
    #  TOP 2-COLUMN AREA: EQ + METER (left) | NAV INFO (right)
    # ══════════════════════════════════════════════════════════
    top_area = tk.Frame(root, bg=ABL_BG)
    top_area.pack(fill="x", padx=8)

    # ─────── LEFT COLUMN: EQ STACK + DJM CHANNEL METER ───────
    eq_section = tk.Frame(top_area, bg=ABL_BG)
    eq_section.pack(side="left", fill="y", padx=(0, 8))

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

    # Framed container (border around EQ + meter)
    eq_glow = tk.Frame(eq_section, bg=EQ_KNOB_RING_DARK, padx=2, pady=2)
    eq_glow.pack(fill="y")
    eq_body = tk.Frame(eq_glow, bg=ABL_PANEL_DARK)
    eq_body.pack(fill="y")

    # Knobs sub-column (HIGH / MID / LOW vertical)
    knobs_col = tk.Frame(eq_body, bg=ABL_PANEL_DARK)
    knobs_col.pack(side="left", fill="y", padx=2, pady=2)

    EQ_KNOB_SIZE_V910 = 78
    eq_cells = [None, None, None]
    display_order  = [EQ_SLOT_HIGH, EQ_SLOT_MID, EQ_SLOT_LOW]
    display_labels = {EQ_SLOT_LOW: "LOW", EQ_SLOT_MID: "MID", EQ_SLOT_HIGH: "HIGH"}

    for band_idx in display_order:
        cell = tk.Frame(knobs_col, bg=ABL_CELL, padx=6, pady=4)
        cell.pack(fill="x", pady=1)

        name_lbl = tk.Label(cell, text=display_labels[band_idx],
                            bg=ABL_CELL, fg=EQ_LABEL_COLOR,
                            font=F_EQ_BAND, anchor="center")
        name_lbl.pack(fill="x", pady=(0, 2))

        canvas = tk.Canvas(cell, width=EQ_KNOB_SIZE_V910,
                           height=EQ_KNOB_SIZE_V910,
                           bg=ABL_CELL, highlightthickness=0)
        canvas.pack()

        value_lbl = tk.Label(cell, text="0.00 dB", bg=ABL_CELL,
                             fg=ABL_TEXT, font=F_VALUE, anchor="center")
        value_lbl.pack(fill="x", pady=(2, 0))

        eq_cells[band_idx] = (cell, canvas, name_lbl, value_lbl)

    # DJM CHANNEL METER sub-column (big single meter)
    meter_col = tk.Frame(eq_body, bg=ABL_PANEL_DARK, padx=4, pady=2)
    meter_col.pack(side="left", fill="y")

    tk.Label(meter_col, text="OUT", bg=ABL_PANEL_DARK,
             fg=ABL_TEXT_DIM, font=F_LABEL_TINY).pack(pady=(2, 4))

    meter_h = (EQ_KNOB_SIZE_V910 + 38) * 3
    eq_channel_meter = tk.Canvas(meter_col, width=24, height=meter_h,
                                  bg="#0a0a0a", highlightthickness=0)
    eq_channel_meter.pack(pady=(0, 2))

    # ─────── RIGHT COLUMN: NAV INFO ───────
    nav_section = tk.Frame(top_area, bg=ABL_BG)
    nav_section.pack(side="left", fill="both", expand=True)

    # Bookmark row
    brow = tk.Frame(nav_section, bg=ABL_CELL, padx=8, pady=4)
    brow.pack(fill="x")
    tk.Label(brow, text="BMARK", bg=ABL_CELL, fg=ABL_TEXT_DIM,
             font=F_LABEL_TINY, width=8, anchor="w").pack(side="left")
    lbl_bookmark = tk.Label(brow, text="—", bg=ABL_CELL, fg=ABL_YELLOW,
                            font=F_BODY_BOLD, anchor="w")
    lbl_bookmark.pack(side="left", fill="x", expand=True)
    lbl_bm_pos = tk.Label(brow, text="", bg=ABL_CELL, fg=ABL_TEXT_DIM,
                          font=F_BODY)
    lbl_bm_pos.pack(side="right")

    # Group row
    grow2 = tk.Frame(nav_section, bg=ABL_CELL_ALT, padx=8, pady=4)
    grow2.pack(fill="x", pady=(2, 0))
    tk.Label(grow2, text="GROUP", bg=ABL_CELL_ALT, fg=ABL_TEXT_DIM,
             font=F_LABEL_TINY, width=8, anchor="w").pack(side="left")
    lbl_group = tk.Label(grow2, text="—", bg=ABL_CELL_ALT, fg=ABL_PURPLE,
                         font=F_BODY_BOLD, anchor="w")
    lbl_group.pack(side="left", fill="x", expand=True)
    lbl_group_pos = tk.Label(grow2, text="", bg=ABL_CELL_ALT,
                             fg=ABL_TEXT_DIM, font=F_BODY)
    lbl_group_pos.pack(side="right")

    # Track block
    track_block = tk.Frame(nav_section, bg=ABL_PANEL, padx=10, pady=4)
    track_block.pack(fill="x", pady=(4, 0))
    tk.Label(track_block, text="TRACK", bg=ABL_PANEL, fg=ABL_TEXT_DIM,
             font=F_LABEL_TINY, anchor="w").pack(fill="x")
    lbl_track_name = tk.Label(track_block, text="—",
                              bg=ABL_PANEL, fg=ABL_TEXT,
                              font=F_TRACK_NAME, anchor="w")
    lbl_track_name.pack(fill="x")

    # Scene
    scene_block = tk.Frame(nav_section, bg=ABL_BG, padx=10)
    scene_block.pack(fill="x", pady=(2, 0))
    tk.Label(scene_block, text="SCENE", bg=ABL_BG, fg=ABL_TEXT_DIM,
             font=F_LABEL_TINY, anchor="w").pack(fill="x")
    lbl_scene_name = tk.Label(scene_block, text="—", bg=ABL_BG, fg=ABL_TEXT,
                              font=F_TITLE, anchor="w")
    lbl_scene_name.pack(fill="x")

    # Clip
    clip_block = tk.Frame(nav_section, bg=ABL_BG, padx=10)
    clip_block.pack(fill="x", pady=(2, 0))
    tk.Label(clip_block, text="CLIP", bg=ABL_BG, fg=ABL_TEXT_DIM,
             font=F_LABEL_TINY, anchor="w").pack(fill="x")
    lbl_clip_name = tk.Label(clip_block, text="—", bg=ABL_BG, fg=ABL_BLUE,
                             font=F_BODY_BOLD, anchor="w")
    lbl_clip_name.pack(fill="x")

    # Number grid
    grid = tk.Frame(nav_section, bg=ABL_BG)
    grid.pack(fill="x", pady=(4, 0))

    def pos_col(parent, label, col, color=ABL_TEXT):
        f = tk.Frame(parent, bg=ABL_CELL, padx=6, pady=4)
        f.grid(row=0, column=col, padx=2, sticky="ew")
        parent.columnconfigure(col, weight=1)
        tk.Label(f, text=label, bg=ABL_CELL, fg=ABL_TEXT_DIM,
                 font=F_LABEL_TINY).pack()
        val = tk.Label(f, text="1", bg=ABL_CELL, fg=color, font=F_VALUE_BIG)
        val.pack()
        return val

    lbl_scene_num = pos_col(grid, "SCENE", 0)
    lbl_track_num = pos_col(grid, "TRACK", 1)
    lbl_bm_num    = pos_col(grid, "BMARK", 2, ABL_YELLOW)

    # Volume row
    vrow = tk.Frame(nav_section, bg=ABL_BG)
    vrow.pack(fill="x", padx=2, pady=(6, 0))
    lbl_volume = tk.Label(vrow, text="+0.0 dB", bg=ABL_BG, fg=ABL_TEXT,
                          font=F_VALUE_BIG, anchor="w")
    lbl_volume.pack(side="left")
    lbl_vol_mode = tk.Label(vrow, text="SELECT+R-stick", bg=ABL_BG,
                            fg=ABL_TEXT_FAINT, font=F_LABEL_TINY, anchor="e")
    lbl_vol_mode.pack(side="right")

    # Stop button
    btn_stop = tk.Button(nav_section, text="■ STOP TRACK (L2)",
                         bg=ABL_PANEL, fg=ABL_RED, font=F_BODY_BOLD,
                         activebackground="#3a0000", activeforeground=ABL_RED,
                         relief="flat", bd=0, pady=4, cursor="hand2",
                         command=action_stop_track)
    btn_stop.pack(fill="x", pady=(4, 4))

    # Modifier pills
    mrow = tk.Frame(nav_section, bg=ABL_BG)
    mrow.pack(fill="x", pady=(0, 2))

    def pill(parent, text):
        lbl = tk.Label(parent, text=text, bg=ABL_PANEL, fg=ABL_TEXT_FAINT,
                       font=F_LABEL_TINY, padx=5, pady=3)
        lbl.pack(side="left", padx=(0, 2))
        return lbl

    lbl_r2     = pill(mrow, "R2 SAFE")
    lbl_select = pill(mrow, "SEL")
    lbl_start  = pill(mrow, "PLAY")
    lbl_l1     = pill(mrow, "L1 FX")
    lbl_eq_pill = pill(mrow, "◇ EQ")

    # EQ status line
    lbl_eq_status = tk.Label(nav_section, text="EQ inactive (R3 to toggle)",
                             bg=ABL_BG, fg=ABL_TEXT_FAINT,
                             font=F_LABEL_TINY, anchor="w")
    lbl_eq_status.pack(fill="x", pady=(2, 0))

    hline(root, pady=6)
    
    #
    # ══════════════════════════════════════════════════════════
    #  NOTIFICATION SLOT (Build B Phase 3)
    #  Dedicated area for transient warnings (config errors,
    #  clipping alerts, restart-required notices). Separate from
    #  the action line at the bottom.
    # ══════════════════════════════════════════════════════════
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

    # ══════════════════════════════════════════════════════════
    #  FX MACHINE PANEL (full width)
    # ══════════════════════════════════════════════════════════
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

    for col in range(4):
        fx_cells.append(make_knob_cell(fx_inner, 0, col, ABL_ORANGE))
    for col in range(4):
        fx_cells.append(make_knob_cell(fx_inner, 1, col, ABL_BLUE))

    hline(root, pady=4)

    # Bottom row
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
    lbl_action = tk.Label(root, text="System ready",
                          bg=ABL_BG, fg=ABL_TEXT_DIM,
                          font=F_BODY, anchor="w")
    lbl_action.pack(fill="x", padx=10, pady=(0, 2))

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
    }