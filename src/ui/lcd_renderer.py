"""TN/terminal-style Session Navigator renderer.

This renderer owns visual treatment only. It receives a plain state snapshot from
``ui.updater``; it never reads shared state and never performs OSC work.
"""

from __future__ import annotations

import time
import tkinter as tk

# Muted TN LCD colours. Amber/green/red are reserved for small status lamps.
LCD_BASE = "#101813"
LCD_SCANLINE = "#0a100c"
LCD_GRID = "#142119"
LCD_TEXT = "#acc99b"
LCD_DIM = "#60735c"
LCD_GHOST = "#334536"
LCD_SELECTED = "#d5dca5"
LCD_AMBER = "#d2a64d"
LCD_GREEN = "#73b777"
LCD_RED = "#c94e45"
LCD_BORDER = "#3d5142"

_FONT_SMALL = ("Consolas", 7, "bold")
_FONT_TEXT = ("Consolas", 9, "bold")
_FONT_VALUE = ("Consolas", 11, "bold")

_state: dict[int, dict] = {}


def _canvas_state(canvas: tk.Canvas) -> dict:
    key = id(canvas)
    width = max(1, canvas.winfo_width())
    height = max(1, canvas.winfo_height())
    state = _state.get(key)
    if state is None or state["size"] != (width, height):
        canvas.delete("all")
        canvas.create_rectangle(0, 0, width, height, fill=LCD_BASE, outline=LCD_BORDER, width=1, tags="static")
        # TN panels look structured rather than emissive: a faint fixed scanline
        # pattern, no animation-heavy CRT effect.
        for y in range(3, height, 4):
            canvas.create_line(1, y, width - 1, y, fill=LCD_SCANLINE, tags="static")
        for x in range(12, width, 28):
            canvas.create_line(x, 1, x, height - 1, fill=LCD_GRID, tags="static")
        state = {"size": (width, height), "last": None, "previous": None, "ghost_until": 0.0}
        _state[key] = state
    return state


def _text(canvas: tk.Canvas, x: int, y: int, text: str, *, fill: str = LCD_TEXT,
          font=_FONT_TEXT, anchor: str = "w", tag: str = "dynamic") -> None:
    canvas.create_text(x, y, text=text, fill=fill, font=font, anchor=anchor, tags=tag)


def _divider(canvas: tk.Canvas, y: int, width: int) -> None:
    canvas.create_line(10, y, width - 10, y, fill=LCD_BORDER, tags="dynamic")


def _status_lamp(canvas: tk.Canvas, x: int, y: int, label: str, online: bool, warning: bool = False) -> None:
    colour = LCD_RED if warning else (LCD_GREEN if online else LCD_DIM)
    canvas.create_rectangle(x, y, x + 5, y + 5, fill=colour, outline="", tags="dynamic")
    _text(canvas, x + 9, y + 3, label, fill=colour, font=_FONT_SMALL, tag="dynamic")


def draw_session_lcd(canvas: tk.Canvas, data: dict) -> None:
    """Draw one snapshot with restrained TN ghosting and tiny status backlights."""
    state = _canvas_state(canvas)
    now = time.perf_counter()
    width, height = state["size"]

    # Only textual/session values participate in ghosting. Meter-like fast
    # animation is intentionally absent: this is a legible navigation display.
    key_data = tuple(sorted(data.items()))
    changed = key_data != state["last"]
    if changed:
        state["previous"] = state["last"]
        state["last"] = key_data
        state["ghost_until"] = now + 0.14

    canvas.delete("dynamic")

    # A short 1-pixel afterimage makes value changes feel like a slow TN panel.
    if state["previous"] is not None and now < state["ghost_until"]:
        previous = dict(state["previous"])
        _text(canvas, 13, 17, str(previous.get("track", ""))[:34], fill=LCD_GHOST, font=_FONT_TEXT, tag="dynamic")
        _text(canvas, 13, 35, str(previous.get("scene", ""))[:34], fill=LCD_GHOST, font=_FONT_TEXT, tag="dynamic")

    _text(canvas, 12, 13, "SESSION NAVIGATOR", fill=LCD_SELECTED, font=_FONT_SMALL)
    _text(canvas, width - 12, 13, "TN LIVE VIEW", fill=LCD_DIM, font=_FONT_SMALL, anchor="e")
    _divider(canvas, 23, width)

    _text(canvas, 12, 37, "BMARK", fill=LCD_DIM, font=_FONT_SMALL)
    _text(canvas, 70, 37, data["bookmark"][:30], fill=LCD_AMBER)
    _text(canvas, width - 12, 37, data["bookmark_pos"], fill=LCD_AMBER, font=_FONT_SMALL, anchor="e")
    _text(canvas, 12, 56, "GROUP", fill=LCD_DIM, font=_FONT_SMALL)
    _text(canvas, 70, 56, data["group"][:30], fill=LCD_TEXT)
    _text(canvas, width - 12, 56, data["group_pos"], fill=LCD_DIM, font=_FONT_SMALL, anchor="e")
    _divider(canvas, 66, width)

    _text(canvas, 12, 82, "TRACK", fill=LCD_DIM, font=_FONT_SMALL)
    _text(canvas, 70, 82, data["track"][:34], fill=LCD_SELECTED)
    _text(canvas, 12, 103, "SCENE", fill=LCD_DIM, font=_FONT_SMALL)
    _text(canvas, 70, 103, data["scene"][:34], fill=LCD_TEXT)
    _text(canvas, 12, 124, "CLIP", fill=LCD_DIM, font=_FONT_SMALL)
    _text(canvas, 70, 124, data["clip"][:34], fill=LCD_TEXT if data["clip"] != "— empty —" else LCD_DIM)
    _divider(canvas, 135, width)

    # Compact instrument readout rather than large dashboard cards.
    third = width // 3
    for x, label, value, colour in (
        (third // 2, "SCENE", data["scene_number"], LCD_TEXT),
        (third + third // 2, "TRACK", data["track_number"], LCD_TEXT),
        (2 * third + third // 2, "BMARK", data["bookmark_number"], LCD_AMBER),
    ):
        _text(canvas, x, 151, label, fill=LCD_DIM, font=_FONT_SMALL, anchor="center")
        _text(canvas, x, 169, value, fill=colour, font=_FONT_VALUE, anchor="center")

    _divider(canvas, 180, width)
    _text(canvas, 12, 198, f"VOL {data['volume']}", fill=data["volume_colour"], font=_FONT_VALUE)
    mode_colour = LCD_AMBER if data["eq_active"] else LCD_DIM
    _text(canvas, width - 12, 198, data["mode"], fill=mode_colour, font=_FONT_SMALL, anchor="e")

    _divider(canvas, 209, width)
    _status_lamp(canvas, 12, 219, "OSC", data["osc_online"])
    _status_lamp(canvas, 75, 219, "CTRL", data["controller_online"])
    _status_lamp(canvas, 153, 219, "CLIP", False, data["clip_active"])
    _text(canvas, 12, 240, data["status"][:56], fill=LCD_DIM, font=_FONT_SMALL)

    # The EQ strip is taller than the base readout. Centre this compact
    # terminal block in any extra vertical screen space rather than leaving
    # an accidental blank area below it.
    canvas.move("dynamic", 0, max(0, (height - 248) // 2))
