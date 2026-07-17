"""Visual tokens for the FX Machine modular-hardware interface."""

from __future__ import annotations

# Faceplate materials — deliberately softened rather than pure black/white.
FACEPLATE = "#141617"
PANEL = "#202426"
PANEL_RAISED = "#2A3032"
PANEL_INSET = "#0B0D0E"
PANEL_EDGE_LIGHT = "#475054"
PANEL_EDGE_DARK = "#060708"
TEXT = "#E6E1D7"
TEXT_MUTED = "#929995"
TEXT_FAINT = "#545B5B"

# LEDs. Colour has one meaning: amber = active/selected, red = unsafe,
# green = online, blue = informational/connection.
AMBER = "#F2A33A"
AMBER_DIM = "#6E471E"
AMBER_GLOW = "#FFE0A3"
GREEN = "#79D68B"
GREEN_DIM = "#285436"
RED = "#F05A4F"
RED_DIM = "#5A201D"
BLUE = "#6CA9D9"

FONT_LABEL = "Arial"
FONT_READOUT = "Courier New"

STYLE_SHEET = f"""
QWidget {{
    background: {FACEPLATE};
    color: {TEXT};
    font-family: {FONT_LABEL};
}}
QToolTip {{
    background: {PANEL_RAISED};
    color: {TEXT};
    border: 1px solid {PANEL_EDGE_LIGHT};
    padding: 5px;
}}
"""
