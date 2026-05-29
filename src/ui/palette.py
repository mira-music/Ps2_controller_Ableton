"""
================================================================================
  src/ui/palette.py — Colors + Typography
================================================================================
  Centralized visual identity. All colors and fonts used by the UI
  modules live here.

  Fixes applied:
    - Added EQ_SLOT_TRIM to EQ_BAND_COLORS import and dict entry.
      Previously the dict only had LOW/MID/HIGH, which would raise KeyError
      if any code ever accessed EQ_BAND_COLORS[EQ_SLOT_TRIM].
      The dict appears unused in the current updater (which reads EQ_LABEL_COLOR
      directly), but it is kept as a complete reference in case future code
      uses it for per-band color theming.
================================================================================
"""

from src.config import EQ_SLOT_LOW, EQ_SLOT_MID, EQ_SLOT_HIGH, EQ_SLOT_TRIM


# ═══════════════════════════════════════════════════════════════════════════
#  ABLETON-STYLE BASE PALETTE
# ═══════════════════════════════════════════════════════════════════════════

ABL_BG          = "#1f1f1f"
ABL_PANEL       = "#2c2c2c"
ABL_PANEL_DARK  = "#1a1a1a"
ABL_CELL        = "#252525"
ABL_CELL_ALT    = "#2a2a2a"
ABL_DIVIDER     = "#3a3a3a"

ABL_TEXT        = "#cfcfcf"
ABL_TEXT_DIM    = "#8a8a8a"
ABL_TEXT_FAINT  = "#5a5a5a"

ABL_ORANGE      = "#ff6c2c"
ABL_BLUE        = "#4a9eff"
ABL_YELLOW      = "#f4d22b"
ABL_GREEN       = "#65d96a"
ABL_RED         = "#ff3b30"
ABL_PURPLE      = "#b878dc"

BLINK_BG_BRIGHT = "#ff3b30"
BLINK_BG_DIM    = "#3a1818"

# FX cell states
ABL_CELL_HOT    = "#3a3416"   # active (currently being moved)
ABL_CELL_REC    = "#1a3a1a"   # recovery flash after L1 release
ABL_CELL_LOCK   = "#2a2a3a"   # filter/wet locked
ABL_CELL_MOMENT = "#3a1a1a"   # momentary effect active


# ═══════════════════════════════════════════════════════════════════════════
#  DJM-900 EQ PALETTE (silver/white metallic)
# ═══════════════════════════════════════════════════════════════════════════

EQ_KNOB_RING_OUTER   = "#0d0d0d"    # outermost shadow circle
EQ_KNOB_RING_DARK    = "#1a1a1a"    # ring outline + section border color
EQ_KNOB_BODY_DARK    = "#3a3a3a"    # outer body fill
EQ_KNOB_BODY_MID     = "#5a5a5a"    # mid body fill
EQ_KNOB_BODY_LIGHT   = "#8a8a8a"    # inner highlight + tick marks
EQ_KNOB_BODY_RIM     = "#2a2a2a"    # body outline rim
EQ_KNOB_INDICATOR    = "#ffffff"    # white indicator line
EQ_KNOB_DETENT       = "#cccccc"    # 12 o'clock (0 dB) detent mark + label
EQ_KNOB_ARC_BG       = "#2a2a2a"    # full-sweep background arc
EQ_KNOB_ARC_ACTIVE   = "#dddddd"    # active (lit) portion of arc

EQ_GLOW_SELECTED     = "#454545"    # cell background when band is selected
EQ_GLOW_ARMED        = "#5a4a1a"    # cell background when band is armed (first flick)

EQ_LABEL_COLOR       = "#cfcfcf"    # default band name + value label color
EQ_LABEL_SELECTED    = "#ffffff"    # label color when band is selected
EQ_LABEL_ARMED       = "#f4d22b"    # label color when band is armed (yellow)

# Per-band accent colors (currently all use EQ_LABEL_COLOR — kept as a
# complete dict for future per-band color theming).
# EQ_SLOT_TRIM is now included so EQ_BAND_COLORS[EQ_SLOT_TRIM] never raises KeyError.
EQ_BAND_COLORS = {
    EQ_SLOT_LOW:  EQ_LABEL_COLOR,
    EQ_SLOT_MID:  EQ_LABEL_COLOR,
    EQ_SLOT_HIGH: EQ_LABEL_COLOR,
    EQ_SLOT_TRIM: EQ_LABEL_COLOR,   # Added in Build B — prevents KeyError on TRIM access
}

EQ_SELECTED_BG = "#2c2c2c"
EQ_ARMED_BG    = "#3a3416"
EQ_MODE_BG     = "#2a1a2a"


# ═══════════════════════════════════════════════════════════════════════════
#  TYPOGRAPHY
# ═══════════════════════════════════════════════════════════════════════════

F_LABEL_TINY  = ("Segoe UI", 7,  "bold")
F_LABEL_SMALL = ("Segoe UI", 8,  "bold")
F_BODY        = ("Segoe UI", 9,  "normal")
F_BODY_BOLD   = ("Segoe UI", 9,  "bold")
F_VALUE       = ("Segoe UI", 9,  "bold")
F_VALUE_BIG   = ("Segoe UI", 12, "bold")
F_TITLE       = ("Segoe UI", 11, "bold")
F_TRACK_NAME  = ("Segoe UI", 13, "bold")
F_MONO        = ("Consolas", 9,  "bold")
F_EQ_BAND     = ("Segoe UI", 10, "bold")