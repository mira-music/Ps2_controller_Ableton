"""
================================================================================
  src/osc/discovery.py — Session Discovery
================================================================================
  fetch_all_names() queries Ableton at startup to discover:
    - Scene count + names + colors
    - Track count + names + colors
    - Bookmarks (scenes prefixed with §)
    - Groups (tracks prefixed with *)
    - FX rack ("~ FX Macros" track)
    - EQ rack ("~ EQ Macros" track)
  
  Then registers listeners for FX, EQ, and meter updates.
================================================================================
"""

import time

from src import state as st
from src.config import (
    BOOKMARK_PREFIX, GROUP_PREFIX,
    FX_TRACK_NAME, EQ_TRACK_NAME,
)
from src.osc.client import (
    osc_query_fx_macro_names, osc_query_fx_macro_values,
    osc_query_fx_macro_mins,  osc_query_fx_macro_maxs,
    osc_query_fx_macro_value_strings,
    osc_register_fx_listeners,
    osc_query_eq_macro_names, osc_query_eq_macro_values,
    osc_query_eq_macro_mins,  osc_query_eq_macro_maxs,
    osc_query_eq_macro_value_strings,
    osc_register_eq_listeners,
    osc_register_eq_meter_listener,
    osc_query_position, osc_query_group_previews,
    osc_query_track_color,
)

# ═══════════════════════════════════════════════════════════════════════════
#  MAIN DISCOVERY
# ═══════════════════════════════════════════════════════════════════════════

def fetch_all_names():
    if not st._fetch_lock.acquire(blocking=False):
        print("  ℹ  Fetch already running — skipping.")
        return
    try:
        print("  📚 Requesting session counts…")
        st.osc.send_message("/live/song/get/num_scenes", [])
        st.osc.send_message("/live/song/get/num_tracks", [])
        time.sleep(0.6)
        with st._lock:
            scene_count = st.state["_real_scene_count"]
            track_count = st.state["_real_track_count"]
        print(f"  ℹ  {scene_count} scenes, {track_count} tracks")

        print(f"  📚 Fetching scene names + colors…")
        for i in range(min(scene_count, 256)):
            st.osc.send_message("/live/scene/get/name",  [i])
            st.osc.send_message("/live/scene/get/color", [i])
            time.sleep(0.012)
        time.sleep(0.4)
        rebuild_bookmarks()

        print(f"  📚 Fetching track names + colors…")
        for i in range(min(track_count, 64)):
            st.osc.send_message("/live/track/get/name",  [i])
            st.osc.send_message("/live/track/get/color", [i])
            time.sleep(0.012)
        time.sleep(0.4)
        rebuild_groups()
        rebuild_fx_track()
        rebuild_eq_track()

        with st._lock:
            fx_idx = st.state["fx_track_index"]
            eq_idx = st.state["eq_track_index"]

        if fx_idx >= 0:
            print(f"  ⚡ Loading FX macro metadata from track {fx_idx}…")
            osc_query_fx_macro_names()
            time.sleep(0.4)
            osc_query_fx_macro_mins()
            time.sleep(0.2)
            osc_query_fx_macro_maxs()
            time.sleep(0.2)
            osc_query_fx_macro_values()
            time.sleep(0.3)
            osc_query_fx_macro_value_strings()
            time.sleep(0.3)
            osc_query_track_color(fx_idx)
            osc_register_fx_listeners()

        if eq_idx >= 0:
            print(f"  ◇ Loading EQ macro metadata from track {eq_idx}…")
            osc_query_eq_macro_names()
            time.sleep(0.4)
            osc_query_eq_macro_mins()
            time.sleep(0.2)
            osc_query_eq_macro_maxs()
            time.sleep(0.2)
            osc_query_eq_macro_values()
            time.sleep(0.3)
            osc_query_eq_macro_value_strings()
            time.sleep(0.3)
            osc_query_track_color(eq_idx)
            osc_register_eq_listeners()
            osc_register_eq_meter_listener()

        osc_query_position()

        with st._lock:
            bm_count = len(st.state["bookmarks"])
            gr_count = len(st.state["groups"])

        print(
            f"  ✅ Ready — "
            f"{bm_count} bookmarks | {gr_count} groups | "
            f"FX: {'YES (t' + str(fx_idx) + ')' if fx_idx >= 0 else 'NO'} | "
            f"EQ: {'YES (t' + str(eq_idx) + ')' if eq_idx >= 0 else 'NO'}"
        )
        osc_query_group_previews()

    finally:
        st._fetch_lock.release()

# ═══════════════════════════════════════════════════════════════════════════
#  BOOKMARK + GROUP + RACK REBUILDS
# ═══════════════════════════════════════════════════════════════════════════

def rebuild_bookmarks():
    with st._lock:
        all_scenes    = list(st.ableton["all_scene_names"])
        was_empty     = not st.state["bookmarks"]
        current_scene = st.state["scene"]
    bmarks = []
    for idx, name in enumerate(all_scenes):
        if name.startswith(BOOKMARK_PREFIX):
            bmarks.append({"name": name[len(BOOKMARK_PREFIX):].strip(), "scene_index": idx})
    print(f"  § {len(bmarks)} bookmark(s) found")
    with st._lock:
        st.state["bookmarks"] = bmarks
        if not bmarks:
            st.state["bookmark_cursor"] = 0
            return
        if was_empty:
            st.state["bookmark_cursor"] = 0
            st.state["scene"]           = bmarks[0]["scene_index"]
        else:
            _sync_bookmark_cursor_locked(current_scene)

def _sync_bookmark_cursor_locked(scene_idx):
    bmarks = st.state["bookmarks"]
    if not bmarks:
        return
    best = 0
    for i, bm in enumerate(bmarks):
        if bm["scene_index"] <= scene_idx:
            best = i
    st.state["bookmark_cursor"] = best

def rebuild_groups():
    with st._lock:
        all_tracks    = list(st.ableton["all_track_names"])
        current_track = st.state["track"]
    groups = []
    for idx, name in enumerate(all_tracks):
        if name.startswith(GROUP_PREFIX):
            groups.append({"name": name[len(GROUP_PREFIX):].strip(), "track_index": idx})
    print(f"  * {len(groups)} group(s) found")
    with st._lock:
        st.state["groups"] = groups
        if not groups:
            return
        best = 0
        for i, g in enumerate(groups):
            if g["track_index"] <= current_track:
                best = i
        st.state["group_cursor"] = best
        st.state["track_group"]  = best
        gc = st.state["group_cursor"]
        st.state["prev_group_name"] = groups[gc - 1]["name"][:14] if gc > 0 else "—"
        st.state["next_group_name"] = groups[gc + 1]["name"][:14] if gc + 1 < len(groups) else "—"

def rebuild_fx_track():
    with st._lock:
        all_tracks = list(st.ableton["all_track_names"])
    fx_idx = -1
    for idx, name in enumerate(all_tracks):
        if name.strip() == FX_TRACK_NAME:
            fx_idx = idx
            break
    with st._lock:
        st.state["fx_track_index"] = fx_idx
        st.state["fx_track_name"]  = FX_TRACK_NAME if fx_idx >= 0 else ""
        if fx_idx < 0:
            st.state["fx_ready"] = False
    if fx_idx >= 0:
        print(f"  ⚡ FX track found at index {fx_idx}")
    else:
        print(f"  ⚠  '{FX_TRACK_NAME}' not found — FX panel inactive")

def rebuild_eq_track():
    with st._lock:
        all_tracks = list(st.ableton["all_track_names"])
    eq_idx = -1
    for idx, name in enumerate(all_tracks):
        if name.strip() == EQ_TRACK_NAME:
            eq_idx = idx
            break
    with st._lock:
        st.state["eq_track_index"] = eq_idx
        st.state["eq_track_name"]  = EQ_TRACK_NAME if eq_idx >= 0 else ""
        if eq_idx < 0:
            st.state["eq_ready"] = False
    if eq_idx >= 0:
        print(f"  ◇ EQ track found at index {eq_idx}")
    else:
        print(f"  ℹ  '{EQ_TRACK_NAME}' not found — EQ panel inactive (optional)")