"""
================================================================================
  src/ui/palette.py — Colors + Typography
================================================================================
  Centralized visual identity. All colors and fonts used by the UI
  modules live here.
================================================================================
"""

from src.config import EQ_SLOT_LOW, EQ_SLOT_MID, EQ_SLOT_HIGH

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
ABL_CELL_HOT    = "#3a3416"
ABL_CELL_REC    = "#1a3a1a"
ABL_CELL_LOCK   = "#2a2a3a"
ABL_CELL_MOMENT = "#3a1a1a"

# ═══════════════════════════════════════════════════════════════════════════
#  DJM-900 EQ PALETTE (silver/white metallic)
# ═══════════════════════════════════════════════════════════════════════════

EQ_KNOB_RING_OUTER   = "#0d0d0d"
EQ_KNOB_RING_DARK    = "#1a1a1a"
EQ_KNOB_BODY_DARK    = "#3a3a3a"
EQ_KNOB_BODY_MID     = "#5a5a5a"
EQ_KNOB_BODY_LIGHT   = "#8a8a8a"
EQ_KNOB_BODY_RIM     = "#2a2a2a"
EQ_KNOB_INDICATOR    = "#ffffff"
EQ_KNOB_DETENT       = "#cccccc"
EQ_KNOB_ARC_BG       = "#2a2a2a"
EQ_KNOB_ARC_ACTIVE   = "#dddddd"

EQ_GLOW_SELECTED     = "#454545"
EQ_GLOW_ARMED        = "#5a4a1a"

EQ_LABEL_COLOR       = "#cfcfcf"
EQ_LABEL_SELECTED    = "#ffffff"
EQ_LABEL_ARMED       = "#f4d22b"

EQ_BAND_COLORS = {
    EQ_SLOT_LOW:  EQ_LABEL_COLOR,
    EQ_SLOT_MID:  EQ_LABEL_COLOR,
    EQ_SLOT_HIGH: EQ_LABEL_COLOR,
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