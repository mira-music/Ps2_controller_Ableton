#!/usr/bin/env python3
"""Standalone EQ-channel geometry concept for FX Machine.

This is deliberately a fresh, code-drawn module study. It does not import the
existing app, its textures, Ableton, OSC, pygame, or controller code.
"""

from __future__ import annotations

import math
import time
from pathlib import Path
import tkinter as tk

W, H = 390, 700

# Material / display colours — the geometry is the point of this study, so
# textures will be added only after this arrangement is approved.
FACE = "#151817"
PANEL = "#242928"
PANEL_INSET = "#0b0e0d"
EDGE_LIGHT = "#59635e"
EDGE_DARK = "#060807"
TEXT = "#ded9cd"
TEXT_DIM = "#87908a"
AMBER = "#d3a34b"
AMBER_DIM = "#60461f"
GREEN = "#78ba70"
YELLOW = "#d8ae3d"
RED = "#d04f43"


class EqChannelConcept:
    """One independently testable EQ strip with fixed coordinate geometry."""

    # Physical geometry contract for the first EQ strip concept.
    PANEL = (25, 25, 365, 665)
    METER_X = 66
    KNOB_X = 255
    KNOB_YS = (165, 295, 425, 555)
    SOCKET_R = 54
    KNOB_R = 40

    BANDS = ("TRIM", "HIGH", "MID", "LOW")
    VALUES = ("-0.2 dB", "+0.0 dB", "+0.0 dB", "+0.0 dB")

    def __init__(self, root: tk.Tk):
        self.root = root
        self.selected = 1
        self.clip = False
        self.signal_active = True
        self.started = time.perf_counter()
        self.assets = Path(__file__).resolve().parent / "assets" / "eq_final"
        self._load_skin()

        root.title("FX Machine — EQ Channel Concept (standalone)")
        root.configure(bg=FACE)
        root.resizable(False, False)
        root.geometry(f"{W}x{H}")
        root.bind("e", self._cycle_band)
        root.bind("c", self._toggle_clip)
        root.bind("<space>", self._toggle_signal)
        root.bind("<Escape>", lambda _event: root.destroy())

        self.canvas = tk.Canvas(root, width=W, height=H, bg=FACE,
                                highlightthickness=0)
        self.canvas.pack()
        self._draw_static()
        self._tick()

    def _load_skin(self) -> None:
        """Load the approved 2× panel texture and whole-knob rotation frames."""
        try:
            self.panel_image = tk.PhotoImage(file=self.assets / "eq_channel_panel_680x1280.png").subsample(2, 2)
            self.knob_frames = [
                tk.PhotoImage(file=self.assets / "knob_frames" / f"{index:02d}.png").subsample(2, 2)
                for index in range(12)
            ]
        except tk.TclError as exc:
            raise SystemExit(f"Could not load EQ concept skin: {exc}") from exc

    def _draw_static(self) -> None:
        c = self.canvas
        x1, y1, x2, y2 = self.PANEL

        # Approved final panel texture: exactly 340 × 640 logical pixels.
        c.create_image(x1, y1, anchor="nw", image=self.panel_image)
        c.create_text(x1 + 16, y1 + 17, text="INPUT / EQ", anchor="w",
                      fill=TEXT, font=("Consolas", 9, "bold"))
        c.create_text(x2 - 16, y1 + 17, text="CH 01", anchor="e",
                      fill=TEXT_DIM, font=("Consolas", 8, "bold"))
        c.create_text(66, 80, text="CLIP", fill="#81504a",
                      font=("Consolas", 7, "bold"))
        c.create_text(66, 102, text="OUT", fill=TEXT_DIM,
                      font=("Consolas", 7, "bold"))

        self.knob_items = []
        for index, y in enumerate(self.KNOB_YS):
            self.knob_items.append(c.create_image(self.KNOB_X, y, anchor="center",
                                                   image=self.knob_frames[0]))
            c.create_text(self.KNOB_X, y - 68, text=self.BANDS[index],
                          fill=TEXT, font=("Consolas", 9, "bold"))
            c.create_text(self.KNOB_X, y + 68, text=self.VALUES[index],
                          fill=TEXT_DIM, font=("Consolas", 8, "bold"))

        c.create_line(x1 + 14, 639, x2 - 14, 639, fill=EDGE_DARK)
        c.create_text(x1 + 16, 650, text="E SELECT   C CLIP   SPACE SIGNAL",
                      anchor="w", fill=TEXT_DIM, font=("Consolas", 7, "bold"))

    def _draw_knob(self, index: int, y: int, value: float, selected: bool) -> None:
        c = self.canvas
        frame = min(11, max(0, round(value * 11)))
        c.itemconfig(self.knob_items[index], image=self.knob_frames[frame])
        if selected:
            c.create_oval(self.KNOB_X - self.SOCKET_R - 4, y - self.SOCKET_R - 4,
                          self.KNOB_X + self.SOCKET_R + 4, y + self.SOCKET_R + 4,
                          outline=AMBER, width=2, tags="dynamic")

    def _draw_meter(self, level: float) -> None:
        c = self.canvas
        segments, seg_h, gap = 22, 14, 7
        bottom = 600
        lit = round(level * segments)
        for index in range(segments):
            y2 = bottom - index * (seg_h + gap)
            y1 = y2 - seg_h
            if index < 14:
                on, off = GREEN, "#183019"
            elif index < 19:
                on, off = YELLOW, "#382e13"
            else:
                on, off = RED, "#351513"
            c.create_rectangle(57, y1, 75, y2,
                               fill=on if index < lit else off,
                               outline="", tags="dynamic")

        if self.clip:
            c.create_rectangle(46, 69, 86, 91, fill=RED, outline="#ff8b76", tags="dynamic")
            c.create_text(66, 80, text="CLIP", fill="#fff6ed",
                          font=("Consolas", 7, "bold"), tags="dynamic")

    def _draw_dynamic(self) -> None:
        self.canvas.delete("dynamic")
        elapsed = time.perf_counter() - self.started
        level = 0.44 + 0.36 * abs(math.sin(elapsed * 1.2)) if self.signal_active else 0.0
        if self.clip:
            level = 0.97
        self._draw_meter(level)
        for index, y in enumerate(self.KNOB_YS):
            value = 0.5 + 0.14 * math.sin(elapsed * 0.55 + index)
            self._draw_knob(index, y, value, selected=index == self.selected)

    def _tick(self) -> None:
        if self.root.winfo_exists():
            self._draw_dynamic()
            self.root.after(40, self._tick)

    def _cycle_band(self, _event=None) -> None:
        self.selected = (self.selected + 1) % len(self.BANDS)

    def _toggle_clip(self, _event=None) -> None:
        self.clip = not self.clip

    def _toggle_signal(self, _event=None) -> None:
        self.signal_active = not self.signal_active


def main() -> int:
    root = tk.Tk()
    EqChannelConcept(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
