"""
================================================================================
  src/engine/navigation.py — Scene/Track/Bookmark/Group Navigation
================================================================================
  Pure navigation logic. Called by axis handlers and D-pad handlers.
  All four functions follow the same pattern:
    - acquire lock, compute new position, set state, schedule queries
    - flash UI on boundary errors
    - send OSC update on success
================================================================================
"""

import time

from src import state as st
from src.config import DPAD_DEBOUNCE
from src.helpers import flash, clamp
from src.osc.client import (
    osc_update_view, schedule_position_query, osc_query_group_previews,
)
from src.osc.discovery import _sync_bookmark_cursor_locked

# ═══════════════════════════════════════════════════════════════════════════
#  SCENE NAVIGATION
# ═══════════════════════════════════════════════════════════════════════════

def navigate_scene(direction):
    with st._lock:
        old   = st.state["scene"]
        limit = st.state["_real_scene_count"] - 1
        new   = clamp(old + direction, 0, limit)
        if new == old:
            st.state["last_action"] = "⚠ First scene" if direction < 0 else "⚠ Last scene"
            do_flash = "flash_scene"
        else:
            st.state["scene"]        = new
            _sync_bookmark_cursor_locked(new)
            st.state["last_action"]  = f"Scene {'↓' if direction > 0 else '↑'}  [{new + 1}]"
            st.ableton["clip_name"]  = "…"
            st.ableton["clip_empty"] = False
            schedule_position_query()
            do_flash = None

    if do_flash:
        flash(do_flash)
    else:
        osc_update_view()

# ═══════════════════════════════════════════════════════════════════════════
#  TRACK NAVIGATION
# ═══════════════════════════════════════════════════════════════════════════

def navigate_track(direction):
    with st._lock:
        old   = st.state["track"]
        limit = st.state["_real_track_count"] - 1
        new   = clamp(old + direction, 0, limit)
        if new == old:
            st.state["last_action"] = "⚠ First track" if direction < 0 else "⚠ Last track"
            do_flash = "flash_track"
        else:
            st.state["track"] = new
            for i, g in enumerate(st.state["groups"]):
                if g["track_index"] <= new:
                    st.state["track_group"]  = i
                    st.state["group_cursor"] = i
            if st.state["groups"]:
                st.state["_group_memory"][st.state["group_cursor"]] = new
            st.state["last_action"]  = f"Track {'→' if direction > 0 else '←'}  [{new + 1}]"
            st.ableton["track_name"] = "…"
            st.ableton["clip_name"]  = "…"
            st.ableton["clip_empty"] = False
            schedule_position_query()
            do_flash = None

    if do_flash:
        flash(do_flash)
    else:
        osc_update_view()

# ═══════════════════════════════════════════════════════════════════════════
#  BOOKMARK NAVIGATION
# ═══════════════════════════════════════════════════════════════════════════

def navigate_bookmark(direction):
    now = time.perf_counter()
    with st._lock:
        if now - st.state["_last_dpad_v"] < DPAD_DEBOUNCE:
            return
        st.state["_last_dpad_v"] = now
        bmarks   = st.state["bookmarks"]
        do_nav   = False
        do_flash = None

        if not bmarks:
            st.state["last_action"] = "⚠ No bookmarks (prefix scenes with §)"
            do_flash = "flash_bmark"
        else:
            cursor           = st.state["bookmark_cursor"]
            current_scene    = st.state["scene"]
            current_bm_scene = bmarks[cursor]["scene_index"]

            if direction < 0 and current_scene > current_bm_scene:
                bm = bmarks[cursor]
                st.state["scene"]        = bm["scene_index"]
                st.state["last_action"]  = (
                    f"▸ {bm['name']}  [snap back, scene {bm['scene_index'] + 1}]"
                )
                st.ableton["clip_name"]  = "…"
                st.ableton["clip_empty"] = False
                schedule_position_query()
                do_nav = True
            else:
                old = cursor
                new = clamp(old + direction, 0, len(bmarks) - 1)
                if new == old:
                    st.state["last_action"] = "⚠ First bookmark" if direction < 0 else "⚠ Last bookmark"
                    do_flash = "flash_bmark"
                else:
                    st.state["bookmark_cursor"] = new
                    bm                          = bmarks[new]
                    st.state["scene"]           = bm["scene_index"]
                    st.state["last_action"]     = (
                        f"▸ {bm['name']}  [scene {bm['scene_index'] + 1}]"
                    )
                    st.ableton["clip_name"]  = "…"
                    st.ableton["clip_empty"] = False
                    schedule_position_query()
                    do_nav = True

    if do_flash:
        flash(do_flash)
    elif do_nav:
        osc_update_view()

# ═══════════════════════════════════════════════════════════════════════════
#  GROUP NAVIGATION
# ═══════════════════════════════════════════════════════════════════════════

def navigate_track_group(direction, force_lead=False):
    now = time.perf_counter()
    with st._lock:
        if now - st.state["_last_dpad_h"] < DPAD_DEBOUNCE:
            return
        st.state["_last_dpad_h"] = now
        groups   = st.state["groups"]
        do_nav   = False
        do_flash = None

        if groups:
            old_gc = st.state["group_cursor"]
            new_gc = clamp(old_gc + direction, 0, len(groups) - 1)
            if new_gc == old_gc:
                st.state["last_action"] = "⚠ First group" if direction < 0 else "⚠ Last group"
                do_flash = "flash_group"
            else:
                st.state["group_cursor"] = new_gc
                g = groups[new_gc]

                if force_lead:
                    target = g["track_index"]
                    mode_tag = " ⊕ lead"
                else:
                    target = st.state["_group_memory"].get(new_gc, g["track_index"])
                    mode_tag = " ⤴ memory" if new_gc in st.state["_group_memory"] else " ⊕ lead"

                st.state["track"]       = clamp(target, 0, st.state["_real_track_count"] - 1)
                st.state["track_group"] = new_gc
                st.state["prev_group_name"] = (
                    groups[new_gc - 1]["name"][:14] if new_gc > 0 else "—"
                )
                st.state["next_group_name"] = (
                    groups[new_gc + 1]["name"][:14] if new_gc + 1 < len(groups) else "—"
                )
                arrow = "→" if direction > 0 else "←"
                st.state["last_action"]  = f"Group {arrow}  {g['name']}{mode_tag}"
                st.ableton["track_name"] = "…"
                st.ableton["clip_name"]  = "…"
                st.ableton["clip_empty"] = False
                schedule_position_query()
                do_nav = True
        else:
            FALLBACK_SIZE = 4
            max_groups    = st.state["_real_track_count"] // FALLBACK_SIZE
            old_g = st.state["track_group"]
            new_g = clamp(old_g + direction, 0, max_groups - 1)
            if new_g == old_g:
                st.state["last_action"] = "⚠ Group min" if direction < 0 else "⚠ Group max"
                do_flash = "flash_track"
            else:
                st.state["track_group"] = new_g
                if force_lead:
                    target = new_g * FALLBACK_SIZE
                else:
                    target = st.state["_group_memory"].get(new_g, new_g * FALLBACK_SIZE)
                st.state["track"]       = clamp(target, 0, st.state["_real_track_count"] - 1)
                arrow = "→" if direction > 0 else "←"
                st.state["last_action"]  = f"Group {arrow}  [{new_g + 1}]"
                st.ableton["track_name"] = "…"
                st.ableton["clip_name"]  = "…"
                st.ableton["clip_empty"] = False
                schedule_position_query()
                do_nav = True

    if do_flash:
        flash(do_flash)
    if do_nav:
        osc_update_view()
        osc_query_group_previews()