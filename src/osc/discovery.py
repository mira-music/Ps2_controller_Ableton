"""
================================================================================
  src/osc/discovery.py — Session Discovery
================================================================================
  fetch_all_names() — called at startup and on manual refresh.
  Queries Ableton for the full session state:
    - Scene count, names, colors
    - Track count, names, colors
    - Locates ~ FX Macros track
    - Locates ~ EQ Macros track
    - Loads macro names + values for both racks
    - Registers OSC listeners for live updates

  Build B: EQ rack now has 4 macros instead of 3 (Trim added at slot 3).

  IMPORTANT: bookmark dicts use the key "scene_index" and group dicts
  use the key "track_index". These names are established convention
  used throughout navigation.py and updater.py. Don't rename them.
================================================================================
"""

import time
from src import state as st
from src.config import (
    FX_TRACK_NAME, EQ_TRACK_NAME,
    BOOKMARK_PREFIX, GROUP_PREFIX,
    EQ_MACRO_COUNT,
)
from src.osc.client import (
    osc_query_position,
    osc_query_fx_macro_names, osc_query_fx_macro_mins,
    osc_query_fx_macro_maxs, osc_query_fx_macro_values,
    osc_query_fx_macro_value_strings,
    osc_query_eq_macro_names, osc_query_eq_macro_mins,
    osc_query_eq_macro_maxs, osc_query_eq_macro_values,
    osc_query_eq_macro_value_strings,
    osc_register_fx_listeners,
    osc_register_eq_listeners,
    osc_register_eq_meter_listener,
    osc_query_track_color,
    osc_query_group_previews,
)
from src.log_setup import get_logger

log = get_logger(__name__)


def fetch_all_names():
    """
    Full session discovery. Called once at startup and again on
    SELECT+START manual refresh. Runs in a background thread because
    it makes many OSC queries with sleeps between them.
    """
    if not st._fetch_lock.acquire(blocking=False):
        log.info("Fetch already running — skipping")
        return
    try:
        log.info("Requesting session counts…")
        st.osc.send_message("/live/song/get/num_scenes", [])
        st.osc.send_message("/live/song/get/num_tracks", [])
        time.sleep(0.6)

        with st._lock:
            sc = st.state["_real_scene_count"]
            tc = st.state["_real_track_count"]
        log.info(f"Session: {sc} scenes, {tc} tracks")

        # ─── Fetch all scene names + colors ───
        log.info("Fetching scene names + colors…")
        for i in range(sc):
            st.osc.send_message("/live/scene/get/name",  [i])
            st.osc.send_message("/live/scene/get/color", [i])
            time.sleep(0.012)
        time.sleep(0.4)
        rebuild_bookmarks()

        # ─── Fetch all track names + colors ───
        log.info("Fetching track names + colors…")
        for i in range(tc):
            st.osc.send_message("/live/track/get/name",  [i])
            st.osc.send_message("/live/track/get/color", [i])
            time.sleep(0.012)
        time.sleep(0.5)
        rebuild_groups()
        rebuild_fx_track()
        rebuild_eq_track()

        with st._lock:
            fx_idx = st.state["fx_track_index"]
            eq_idx = st.state["eq_track_index"]
            bm_count = len(st.state["bookmarks"])
            gr_count = len(st.state["groups"])

        # ─── Load FX macros if found ───
        if fx_idx >= 0:
            log.info(f"Loading FX macro metadata from track {fx_idx}…")
            osc_query_fx_macro_names()
            time.sleep(0.4)
            osc_query_fx_macro_mins()
            time.sleep(0.2)
            osc_query_fx_macro_maxs()
            time.sleep(0.2)
            osc_query_fx_macro_values()
            time.sleep(0.5)
            osc_query_fx_macro_value_strings()
            time.sleep(0.5)
            osc_register_fx_listeners()
            osc_query_track_color(fx_idx)

        # ─── Load EQ macros if found ───
        if eq_idx >= 0:
            log.info(f"Loading EQ macro metadata from track {eq_idx}…")
            osc_query_eq_macro_names()
            time.sleep(0.4)
            osc_query_eq_macro_mins()
            time.sleep(0.2)
            osc_query_eq_macro_maxs()
            time.sleep(0.2)
            osc_query_eq_macro_values()
            time.sleep(0.5)
            osc_query_eq_macro_value_strings()
            time.sleep(0.5)
            osc_register_eq_listeners()
            osc_register_eq_meter_listener()
            osc_query_track_color(eq_idx)

        # ─── Initial position query ───
        osc_query_position()
        osc_query_group_previews()

        log.info(
            f"Ready — {bm_count} bookmarks | {gr_count} groups | "
            f"FX: {'YES (t' + str(fx_idx) + ')' if fx_idx >= 0 else 'NO'} | "
            f"EQ: {'YES (t' + str(eq_idx) + ')' if eq_idx >= 0 else 'NO'}"
        )
    finally:
        st._fetch_lock.release()


def rebuild_bookmarks():
    """
    Scan all scene names; find those starting with § prefix.

    Bookmark dict format (ESTABLISHED CONVENTION — DO NOT CHANGE):
      {"scene_index": int, "name": str}

    The key "scene_index" is read by navigation.py (navigate_bookmark)
    and updater.py (UI bookmark display). Don't rename to "index".
    """
    with st._lock:
        scenes = list(st.ableton["all_scene_names"])

    bookmarks = []
    for idx, name in enumerate(scenes):
        if name and name.strip().startswith(BOOKMARK_PREFIX):
            stripped = name.strip().removeprefix(BOOKMARK_PREFIX).strip()
            bookmarks.append({"scene_index": idx, "name": stripped})

    with st._lock:
        st.state["bookmarks"] = bookmarks
    log.info(f"{len(bookmarks)} bookmark(s) found")


def rebuild_groups():
    """
    Scan all track names; find those starting with * prefix.

    Group dict format (ESTABLISHED CONVENTION — DO NOT CHANGE):
      {"track_index": int, "name": str}
    """
    with st._lock:
        tracks = list(st.ableton["all_track_names"])

    groups = []
    for idx, name in enumerate(tracks):
        if name and name.strip().startswith(GROUP_PREFIX):
            stripped = name.strip().removeprefix(GROUP_PREFIX).strip()
            groups.append({"track_index": idx, "name": stripped})

    with st._lock:
        st.state["groups"] = groups
    log.info(f"{len(groups)} group(s) found")


def rebuild_fx_track():
    """Find the FX rack track by name match."""
    with st._lock:
        tracks = list(st.ableton["all_track_names"])

    fx_idx = -1
    for i, name in enumerate(tracks):
        if name and name.strip() == FX_TRACK_NAME:
            fx_idx = i
            break

    with st._lock:
        st.state["fx_track_index"] = fx_idx
        st.state["fx_track_name"] = FX_TRACK_NAME if fx_idx >= 0 else ""

    if fx_idx >= 0:
        log.info(f"FX track found at index {fx_idx}")
    else:
        log.warning(f"FX track '{FX_TRACK_NAME}' not found in session")


def rebuild_eq_track():
    """Find the EQ rack track by name match."""
    with st._lock:
        tracks = list(st.ableton["all_track_names"])

    eq_idx = -1
    for i, name in enumerate(tracks):
        if name and name.strip() == EQ_TRACK_NAME:
            eq_idx = i
            break

    with st._lock:
        st.state["eq_track_index"] = eq_idx
        st.state["eq_track_name"] = EQ_TRACK_NAME if eq_idx >= 0 else ""

    if eq_idx >= 0:
        log.info(f"EQ track found at index {eq_idx}")
    else:
        log.warning(f"EQ track '{EQ_TRACK_NAME}' not found in session")


def _sync_bookmark_cursor_locked(scene_idx):
    """
    Move bookmark cursor to point at the bookmark that owns the
    given scene index. Called when scene changes via navigation.

    Reads bookmark dicts using "scene_index" key.
    """
    bookmarks = st.state["bookmarks"]
    cur_cursor = st.state["bookmark_cursor"]

    # Find largest scene_index <= scene_idx
    new_cursor = -1
    for i, bm in enumerate(bookmarks):
        if bm["scene_index"] <= scene_idx:
            new_cursor = i
        else:
            break

    if new_cursor >= 0 and new_cursor != cur_cursor:
        st.state["bookmark_cursor"] = new_cursor