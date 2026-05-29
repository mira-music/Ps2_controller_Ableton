"""
================================================================================
  src/ui/updater.py — Tkinter UI Update Loop (40 Hz)
================================================================================
  update_ui() is scheduled via root.after() at UI_REFRESH_MS intervals.
  Reads state snapshot under lock, then updates widgets via dirty-cache
  set_label() and canvas redraws.

  All UI updates happen on the main thread (Tkinter requirement).
================================================================================
"""

import time

from src import state as st
from src.config import (
    UI_REFRESH_MS, BLINK_PERIOD_MS,
    ABLETON_UNITY,
    EQ_NEUTRAL_MACRO,
    FX_TRACK_NAME,
    EQ_MACRO_NAMES_EXPECTED, FX_MACRO_NAMES_EXPECTED,
    FX_SLOT_FILTER_FREQ, FX_SLOT_FILTER_MODE, FX_SLOT_STUTTER, FX_SLOT_FX_SEND,
)
from src.helpers import (
    db_from_vol, int_to_hex_color, clear_flashes_if_expired,
    eq_visual_position,
)
from src.ui.palette import (
    ABL_BG, ABL_PANEL, ABL_CELL,
    ABL_TEXT, ABL_TEXT_DIM, ABL_TEXT_FAINT,
    ABL_ORANGE, ABL_BLUE, ABL_YELLOW, ABL_GREEN, ABL_RED, ABL_PURPLE,
    BLINK_BG_BRIGHT, BLINK_BG_DIM,
    ABL_CELL_HOT, ABL_CELL_REC, ABL_CELL_LOCK, ABL_CELL_MOMENT,
    EQ_KNOB_RING_DARK,
    EQ_GLOW_SELECTED, EQ_GLOW_ARMED,
    EQ_LABEL_COLOR, EQ_LABEL_SELECTED, EQ_LABEL_ARMED,
)
from src.ui.widgets import (
    set_label, draw_knob, draw_eq_knob, draw_channel_meter, update_meter_peak,
)
from src.log_setup import get_logger

log = get_logger(__name__)
# ═══════════════════════════════════════════════════════════════════════════
#  BLINK HELPER
# ═══════════════════════════════════════════════════════════════════════════

def _blink_on():
    ms_now = int(time.perf_counter() * 1000)
    return (ms_now // BLINK_PERIOD_MS) % 2 == 0

# ═══════════════════════════════════════════════════════════════════════════
#  MAIN UI UPDATE
# ═══════════════════════════════════════════════════════════════════════════

def update_ui(root, lbl):
    clear_flashes_if_expired()

    now = time.perf_counter()

    with st._lock:
        s          = {k: v for k, v in st.state.items()
                      if not isinstance(v, (dict, list))}
        bmarks     = list(st.state["bookmarks"])
        groups     = list(st.state["groups"])
        abl        = dict(st.ableton)
        fx_idx     = st.state["fx_track_index"]
        fx_name    = st.state["fx_track_name"]
        fx_ready   = st.state["fx_ready"]
        fx_names   = list(st.state["fx_macro_names"])
        fx_strings = list(st.state["fx_macro_value_strings"])
        fx_values  = list(st.state["fx_macro_values"])
        fx_mins    = list(st.state["fx_macro_mins"])
        fx_maxs    = list(st.state["fx_macro_maxs"])
        l1_held    = st.state["l1_held"]
        ctrl_conn  = st.state["controller_connected"]
        ctrl_name  = st.state["controller_name"]
        active_slot   = st.state["_fx_active_slot"]
        active_until  = st.state["_fx_active_until"]
        recovery_until = list(st.state["_fx_recovery_until"])
        baseline_ready = st.state["fx_baseline_ready"]
        baseline_captured_at = st.state["fx_baseline_captured_at"]
        filter_locked = st.state["fx_filter_locked"]
        wet_locked    = st.state["fx_wet_locked"]

        moment_stutter   = st.state["_momentary_stutter_active"]
        moment_bass_cut  = st.state["_momentary_bass_cut_active"]
        moment_throw     = st.state["_momentary_fx_throw_active"]

        all_track_colors = list(st.ableton["all_track_colors"])
        all_scene_colors = list(st.ableton["all_scene_colors"])
        clip_color       = st.ableton["clip_color"]
        fx_track_color   = st.ableton["fx_track_color"]
        eq_track_color   = st.ableton["eq_track_color"]
        current_track    = st.state["track"]
        current_scene    = st.state["scene"]
        cursor_bmark     = s["bookmark_cursor"]
        cursor_group     = s["group_cursor"]

        eq_idx           = st.state["eq_track_index"]
        eq_name          = st.state["eq_track_name"]
        eq_ready         = st.state["eq_ready"]
        eq_mode_active   = st.state["eq_mode_active"]
        eq_selected_band = st.state["eq_selected_band"]
        eq_armed_band    = st.state["eq_armed_band"]
        eq_armed_until   = st.state["eq_armed_until"]
        eq_macro_values  = list(st.state["eq_macro_values"])
        eq_value_strings = list(st.state["eq_macro_value_strings"])

        meter_left       = st.state["eq_meter_left"]
        meter_right      = st.state["eq_meter_right"]
        meter_peak       = st.state["eq_meter_peak"]
        meter_peak_time  = st.state["eq_meter_peak_time"]

    if active_slot >= 0 and now > active_until:
        with st._lock:
            st.state["_fx_active_slot"] = -1
        active_slot = -1

    if eq_armed_band >= 0 and now > eq_armed_until:
        with st._lock:
            st.state["eq_armed_band"] = -1
        eq_armed_band = -1

    # ── TRANSPORT + BPM ──
    if abl["is_playing"]:
        set_label(lbl["playing"], "playing", "▶ PLAYING", fg=ABL_GREEN)
    else:
        set_label(lbl["playing"], "playing", "■ STOPPED", fg=ABL_RED)
    set_label(lbl["bpm"], "bpm", f"{abl['bpm']:.1f} BPM")

    # ── BOOKMARK + GROUP ROWS ──
    if bmarks:
        cur = cursor_bmark
        bm  = bmarks[cur]
        scene_idx = bm["scene_index"]
        scene_color_int = all_scene_colors[scene_idx] if scene_idx < len(all_scene_colors) else 0
        bm_color = int_to_hex_color(scene_color_int, ABL_YELLOW)
        fg = ABL_RED if s["flash_bmark"] else bm_color
        set_label(lbl["bookmark"], "bookmark", bm["name"], fg=fg)
        set_label(lbl["bm_pos"],   "bm_pos",   f"{cur + 1}/{len(bmarks)}")
        set_label(lbl["bm_num"],   "bm_num",   str(cur + 1), fg=fg)
    else:
        set_label(lbl["bookmark"], "bookmark", "no §-scenes", fg=ABL_TEXT_FAINT)
        set_label(lbl["bm_pos"],   "bm_pos",   "")
        set_label(lbl["bm_num"],   "bm_num",   "—", fg=ABL_TEXT_FAINT)

    if groups:
        gc = cursor_group
        g  = groups[gc]
        group_track_idx = g["track_index"]
        group_color_int = (all_track_colors[group_track_idx]
                           if group_track_idx < len(all_track_colors) else 0)
        gr_color = int_to_hex_color(group_color_int, ABL_PURPLE)
        fg = ABL_RED if s["flash_group"] else gr_color
        set_label(lbl["group"],     "group",     g["name"], fg=fg)
        set_label(lbl["group_pos"], "group_pos", f"{gc + 1}/{len(groups)}")
    else:
        set_label(lbl["group"],     "group",     "no *-tracks", fg=ABL_TEXT_FAINT)
        set_label(lbl["group_pos"], "group_pos", "")

    # ── TRACK / SCENE / CLIP NAMES ──
    track_color_int = (all_track_colors[current_track]
                       if current_track < len(all_track_colors) else 0)
    track_color = int_to_hex_color(track_color_int, ABL_TEXT)
    set_label(lbl["track_name"], "track_name", abl["track_name"], fg=track_color)

    scene_color_int = (all_scene_colors[current_scene]
                       if current_scene < len(all_scene_colors) else 0)
    scene_color = int_to_hex_color(scene_color_int, ABL_TEXT)
    set_label(lbl["scene_name"], "scene_name", abl["scene_name"], fg=scene_color)

    clip = abl["clip_name"]
    clip_color_hex = int_to_hex_color(clip_color, ABL_BLUE)
    if clip == "…":
        set_label(lbl["clip_name"], "clip_name", "…", fg=ABL_TEXT_FAINT)
    elif abl["clip_empty"]:
        set_label(lbl["clip_name"], "clip_name", "— empty —", fg=ABL_TEXT_FAINT)
    else:
        set_label(lbl["clip_name"], "clip_name", clip, fg=clip_color_hex)

    set_label(lbl["scene_num"], "scene_num",
              str(s["scene"] + 1),
              fg=ABL_RED if s["flash_scene"] else ABL_TEXT)
    set_label(lbl["track_num"], "track_num",
              str(s["track"] + 1),
              fg=ABL_RED if s["flash_track"] else ABL_TEXT)

    # ── VOLUME ──
    vol = abl["track_volume"]
    vol_ratio = vol / ABLETON_UNITY
    if vol == 0.0:
        vc = ABL_RED
    elif vol_ratio > 1.05:
        vc = ABL_ORANGE
    elif vol_ratio > 0.95:
        vc = ABL_GREEN
    else:
        vc = ABL_BLUE
    set_label(lbl["volume"], "volume", db_from_vol(vol), fg=vc)

    if s["select_held"]:
        set_label(lbl["vol_mode"], "vol_mode", "● VOL", fg=ABL_BLUE)
    else:
        set_label(lbl["vol_mode"], "vol_mode", "SELECT+R-stick", fg=ABL_TEXT_FAINT)

    # ── MODIFIER PILLS ──
    lbl["r2"].config(fg=ABL_RED if s["r2_held"] else ABL_TEXT_FAINT,
                     bg="#3a1818" if s["r2_held"] else ABL_PANEL)
    lbl["select"].config(fg=ABL_BLUE if s["select_held"] else ABL_TEXT_FAINT,
                         bg="#142838" if s["select_held"] else ABL_PANEL)
    lbl["start"].config(fg=ABL_GREEN if abl["is_playing"] else ABL_TEXT_FAINT,
                        bg="#1a2a1a" if abl["is_playing"] else ABL_PANEL)
    lbl["l1"].config(fg=ABL_YELLOW if l1_held else ABL_TEXT_FAINT,
                     bg="#3a3010" if l1_held else ABL_PANEL)
    lbl["eq_pill"].config(fg=ABL_PURPLE if eq_mode_active else ABL_TEXT_FAINT,
                          bg="#2a1a2a" if eq_mode_active else ABL_PANEL)

    set_label(lbl["action"], "action", s["last_action"])

    # ── CONTROLLER STATUS ──
    if ctrl_conn:
        lbl["ctrl"].config(text=f"● {ctrl_name[:16]}",
                           bg="#1a2a1a", fg=ABL_GREEN)
    else:
        bright = _blink_on()
        lbl["ctrl"].config(text="● NO CONTROLLER",
                           bg=BLINK_BG_BRIGHT if bright else BLINK_BG_DIM,
                           fg="#ffffff" if bright else ABL_TEXT)

    # ── EQ STATUS LINE ──
    eq_track_color_hex = int_to_hex_color(eq_track_color, ABL_TEXT)
    if eq_idx < 0:
        set_label(lbl["eq_title"], "eq_title", "◇ EQ", fg=ABL_TEXT_FAINT)
        set_label(lbl["eq_track"], "eq_track", "—", fg=ABL_TEXT_FAINT)
        set_label(lbl["eq_status"], "eq_status",
                  "(no ~ EQ Macros track)", fg=ABL_TEXT_FAINT)
        lbl["eq_glow"].config(bg=EQ_KNOB_RING_DARK)
    elif not eq_ready:
        set_label(lbl["eq_title"], "eq_title", "◇ EQ", fg=ABL_TEXT_DIM)
        set_label(lbl["eq_track"], "eq_track", f"loading…  [t{eq_idx}]",
                  fg=ABL_TEXT_DIM)
        set_label(lbl["eq_status"], "eq_status", "loading EQ rack…",
                  fg=ABL_TEXT_DIM)
        lbl["eq_glow"].config(bg=EQ_KNOB_RING_DARK)
    elif eq_mode_active:
        set_label(lbl["eq_title"], "eq_title", "◇ EQ ACTIVE", fg=ABL_TEXT)
        set_label(lbl["eq_track"], "eq_track", f"[t{eq_idx}]", fg=ABL_TEXT)
        band_name = EQ_MACRO_NAMES_EXPECTED[eq_selected_band]
        set_label(lbl["eq_status"], "eq_status",
                  f"◇ {band_name}  •  ←/→ value  •  ↑/↓ band",
                  fg=ABL_TEXT)
        lbl["eq_glow"].config(bg=EQ_LABEL_SELECTED)
    else:
        set_label(lbl["eq_title"], "eq_title", "◇ EQ", fg=ABL_TEXT)
        set_label(lbl["eq_track"], "eq_track", f"[t{eq_idx}]",
                  fg=eq_track_color_hex)
        set_label(lbl["eq_status"], "eq_status",
                  "EQ inactive (R3 to toggle)", fg=ABL_TEXT_FAINT)
        lbl["eq_glow"].config(bg=EQ_KNOB_RING_DARK)

    # ── EQ KNOBS (HIGH / MID / LOW) ──
    for band_idx in range(3):
        cell, canvas, name_lbl, value_lbl = lbl["eq_cells"][band_idx]
        macro_val = eq_macro_values[band_idx] if band_idx < len(eq_macro_values) else EQ_NEUTRAL_MACRO
        value_str = eq_value_strings[band_idx] if band_idx < len(eq_value_strings) else "—"

        visual_pos = eq_visual_position(macro_val)
        is_selected = (eq_mode_active and band_idx == eq_selected_band)
        is_armed    = (eq_mode_active and band_idx == eq_armed_band)

        if is_armed:
            cell_bg = EQ_GLOW_ARMED
            label_color = EQ_LABEL_ARMED
        elif is_selected:
            cell_bg = EQ_GLOW_SELECTED
            label_color = EQ_LABEL_SELECTED
        else:
            cell_bg = ABL_CELL
            label_color = EQ_LABEL_COLOR

        if cell.cget("bg") != cell_bg:
            cell.config(bg=cell_bg)
            canvas.config(bg=cell_bg)
            name_lbl.config(bg=cell_bg)
            value_lbl.config(bg=cell_bg)

        draw_eq_knob(canvas, band_idx, visual_pos,
                     selected=is_selected, armed=is_armed)

        band_name = EQ_MACRO_NAMES_EXPECTED[band_idx]
        display_name = band_name.replace("EQ ", "").upper()
        set_label(name_lbl, f"eq_name_{band_idx}", display_name, fg=label_color)

        set_label(value_lbl, f"eq_value_{band_idx}",
                  value_str if value_str else "—", fg=label_color)

    # ── DJM CHANNEL METER (Build B Phase 2: new math + CLIP detection) ──
    # Import the new meter functions
    from src.ui.widgets import (
        raw_meter_to_display_db, apply_meter_ballistics,
        update_meter_peak_db, compute_clip_state,
    )

    current_level = max(meter_left, meter_right)  # stereo peak

    # Convert raw 0-1 to display dB (-30 to +12 range)
    current_display_db = raw_meter_to_display_db(current_level)

    # Apply release ballistics (instant attack, slow decay)
    with st._lock:
        prev_smoothed = st.state["meter_smoothed_db"]
    dt_meter = 1.0 / 40.0  # UI runs at ~40 Hz = 25ms per frame
    smoothed_db = apply_meter_ballistics(current_display_db, prev_smoothed, dt_meter)

    # Peak hold
    with st._lock:
        prev_peak_db = st.state["meter_peak_db"]
        prev_peak_time = st.state["meter_peak_time"]
    new_peak_db, new_peak_time = update_meter_peak_db(
        smoothed_db, prev_peak_db, prev_peak_time, now
    )

    # CLIP detection
    with st._lock:
        was_clip_active = st.state["clip_active"]
        clip_last_time = st.state["clip_last_active_time"]
    clip_active, clip_level, clip_last_time = compute_clip_state(
        smoothed_db, was_clip_active, clip_last_time, now
    )

    # Write all computed values back to state
    with st._lock:
        st.state["meter_display_db"]     = current_display_db
        st.state["meter_smoothed_db"]    = smoothed_db
        st.state["meter_peak_db"]        = new_peak_db
        st.state["meter_peak_time"]      = new_peak_time
        st.state["clip_active"]          = clip_active
        st.state["clip_level"]           = clip_level
        st.state["clip_last_active_time"] = clip_last_time
        
    # TEMPORARY DEBUG — remove after verifying Phase 2 math works (take off # # for debugging a good clipping calibre)
    #if clip_active:
        #log.warning(f"CLIP! level={clip_level:.2f} smoothed={smoothed_db:.1f}dB peak={new_peak_db:.1f}dB")

    # For now, use the OLD meter drawing (Phase 4 will replace this)
    # The old draw_channel_meter expects raw 0-1 values, not dB
    old_peak = max(meter_left, meter_right)
    with st._lock:
        old_peak_val = st.state.get("eq_meter_peak", 0.0)
        old_peak_time = st.state.get("eq_meter_peak_time", 0.0)
    new_old_peak, new_old_peak_time = update_meter_peak(
        old_peak, old_peak_val, old_peak_time, now
    )
    with st._lock:
        st.state["eq_meter_peak"] = new_old_peak
        st.state["eq_meter_peak_time"] = new_old_peak_time

    draw_channel_meter(lbl["eq_channel_meter"], current_level, new_old_peak)

    # ── FX PANEL TITLE ──
    fx_color = int_to_hex_color(fx_track_color, ABL_TEXT)
    if fx_idx < 0:
        set_label(lbl["fx_title"], "fx_title", "⚡ FX MACHINE", fg=ABL_TEXT_FAINT)
        set_label(lbl["fx_track"], "fx_track",
                  f"add track '{FX_TRACK_NAME}'", fg=ABL_TEXT_FAINT)
        lbl["fx_glow"].config(bg=ABL_BG)
    elif not fx_ready:
        set_label(lbl["fx_title"], "fx_title", "⚡ FX MACHINE", fg=ABL_TEXT_DIM)
        set_label(lbl["fx_track"], "fx_track",
                  f"loading…  [t{fx_idx}]", fg=ABL_TEXT_DIM)
        lbl["fx_glow"].config(bg=ABL_BG)
    elif l1_held:
        set_label(lbl["fx_title"], "fx_title", "⚡ FX MODE ACTIVE", fg=ABL_YELLOW)
        set_label(lbl["fx_track"], "fx_track",
                  f"{fx_name}  [t{fx_idx}]", fg=ABL_YELLOW)
        lbl["fx_glow"].config(bg=ABL_YELLOW)
    else:
        set_label(lbl["fx_title"], "fx_title", "⚡ FX MACHINE", fg=ABL_TEXT)
        set_label(lbl["fx_track"], "fx_track",
                  f"{fx_name}  [t{fx_idx}]", fg=fx_color)
        lbl["fx_glow"].config(bg=ABL_BG)

    if baseline_ready:
        if (now - baseline_captured_at) < 1.0:
            set_label(lbl["baseline"], "baseline", "✓ BASELINE SAVED", fg=ABL_GREEN)
        else:
            set_label(lbl["baseline"], "baseline", "✓ baseline", fg=ABL_TEXT_DIM)
    else:
        set_label(lbl["baseline"], "baseline", "✗ no baseline", fg=ABL_TEXT_FAINT)

    if filter_locked:
        set_label(lbl["lock_filter"], "lock_filter", "🔒 filter", fg=ABL_YELLOW)
    else:
        set_label(lbl["lock_filter"], "lock_filter", "filter: free", fg=ABL_TEXT_FAINT)

    if wet_locked:
        set_label(lbl["lock_wet"], "lock_wet", "🔒 wet", fg=ABL_YELLOW)
    else:
        set_label(lbl["lock_wet"], "lock_wet", "wet: free", fg=ABL_TEXT_FAINT)

    # ── FX KNOBS ──
    for slot in range(8):
        cell, canvas, name_lbl, value_lbl = lbl["fx_cells"][slot]
        accent  = ABL_ORANGE if slot < 4 else ABL_BLUE
        name    = fx_names[slot] if slot < len(fx_names) else ""
        value_string = fx_strings[slot] if slot < len(fx_strings) else "—"

        is_active   = (slot == active_slot)
        is_recover  = (now < recovery_until[slot])
        is_locked   = ((slot == FX_SLOT_FX_SEND and wet_locked) or
                       (slot == FX_SLOT_FILTER_FREQ and filter_locked))
        is_moment   = ((slot == FX_SLOT_STUTTER and moment_stutter) or
                       (slot in (FX_SLOT_FILTER_FREQ, FX_SLOT_FILTER_MODE) and moment_bass_cut) or
                       (slot == FX_SLOT_FX_SEND and moment_throw))

        if slot < len(fx_values) and slot < len(fx_mins) and slot < len(fx_maxs):
            val = fx_values[slot]
            min_val = fx_mins[slot]
            max_val = fx_maxs[slot]
            macro_range = max_val - min_val
            if macro_range > 0:
                value_frac = (val - min_val) / macro_range
                value_frac = max(0.0, min(1.0, value_frac))
            else:
                value_frac = 0.0
        else:
            value_frac = 0.0

        if is_moment:
            cell_bg = ABL_CELL_MOMENT
        elif is_active:
            cell_bg = ABL_CELL_HOT
        elif is_recover:
            cell_bg = ABL_CELL_REC
        elif is_locked:
            cell_bg = ABL_CELL_LOCK
        else:
            cell_bg = ABL_CELL

        if cell.cget("bg") != cell_bg:
            cell.config(bg=cell_bg)
            canvas.config(bg=cell_bg)
            name_lbl.config(bg=cell_bg)
            value_lbl.config(bg=cell_bg)

        if name:
            draw_knob(canvas, slot, value_frac, accent,
                      active=is_active, locked=is_locked, moment=is_moment)
        else:
            draw_knob(canvas, slot, 0.0, ABL_TEXT_FAINT)

        if not name:
            expected = FX_MACRO_NAMES_EXPECTED[slot]
            set_label(name_lbl,  f"fx_name_{slot}",  expected, fg=ABL_TEXT_FAINT)
            set_label(value_lbl, f"fx_value_{slot}", "—",      fg=ABL_TEXT_FAINT)
        else:
            display_name = name
            if is_locked:
                display_name = "🔒 " + name
            elif is_moment:
                display_name = "💥 " + name
            set_label(name_lbl,  f"fx_name_{slot}", display_name, fg=ABL_TEXT_DIM)
            set_label(value_lbl, f"fx_value_{slot}", value_string, fg=accent)

    root.after(UI_REFRESH_MS, update_ui, root, lbl)