#!/usr/bin/env python3
"""FX Machine — single-screen retro monitor UI concept.

A fully pixel-drawn standalone model: no textures, no Ableton, no OSC, no
pygame, no fonts. The interface is rendered into a 160×120 virtual monitor and
scaled with integer pixels only.

Run:
    python ui_concept\preview_retro_monitor.py

Keys: E cycle EQ selection | F toggle FX focus | Space play/stop | C clip
"""

from __future__ import annotations

import math
import time
import tkinter as tk

# 5×7 bitmap character set. Every label on the monitor is drawn from this map.
FONT = {
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    "B": ("11110", "10001", "10001", "11110", "10001", "10001", "11110"),
    "C": ("01111", "10000", "10000", "10000", "10000", "10000", "01111"),
    "D": ("11110", "10001", "10001", "10001", "10001", "10001", "11110"),
    "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    "F": ("11111", "10000", "10000", "11110", "10000", "10000", "10000"),
    "G": ("01111", "10000", "10000", "10111", "10001", "10001", "01111"),
    "H": ("10001", "10001", "10001", "11111", "10001", "10001", "10001"),
    "I": ("11111", "00100", "00100", "00100", "00100", "00100", "11111"),
    "J": ("00111", "00010", "00010", "00010", "10010", "10010", "01100"),
    "K": ("10001", "10010", "10100", "11000", "10100", "10010", "10001"),
    "L": ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
    "M": ("10001", "11011", "10101", "10101", "10001", "10001", "10001"),
    "N": ("10001", "11001", "10101", "10011", "10001", "10001", "10001"),
    "O": ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    "P": ("11110", "10001", "10001", "11110", "10000", "10000", "10000"),
    "Q": ("01110", "10001", "10001", "10001", "10101", "10010", "01101"),
    "R": ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    "S": ("01111", "10000", "10000", "01110", "00001", "00001", "11110"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    "U": ("10001", "10001", "10001", "10001", "10001", "10001", "01110"),
    "V": ("10001", "10001", "10001", "10001", "10001", "01010", "00100"),
    "W": ("10001", "10001", "10001", "10101", "10101", "10101", "01010"),
    "X": ("10001", "10001", "01010", "00100", "01010", "10001", "10001"),
    "Y": ("10001", "10001", "01010", "00100", "00100", "00100", "00100"),
    "Z": ("11111", "00001", "00010", "00100", "01000", "10000", "11111"),
    "0": ("01110", "10001", "10011", "10101", "11001", "10001", "01110"),
    "1": ("00100", "01100", "00100", "00100", "00100", "00100", "01110"),
    "2": ("01110", "10001", "00001", "00010", "00100", "01000", "11111"),
    "3": ("11110", "00001", "00001", "01110", "00001", "00001", "11110"),
    "4": ("00010", "00110", "01010", "10010", "11111", "00010", "00010"),
    "5": ("11111", "10000", "10000", "11110", "00001", "00001", "11110"),
    "6": ("01110", "10000", "10000", "11110", "10001", "10001", "01110"),
    "7": ("11111", "00001", "00010", "00100", "01000", "01000", "01000"),
    "8": ("01110", "10001", "10001", "01110", "10001", "10001", "01110"),
    "9": ("01110", "10001", "10001", "01111", "00001", "00001", "01110"),
    " ": ("000",) * 7,
    "-": ("00000", "00000", "00000", "11111", "00000", "00000", "00000"),
    "+": ("00000", "00100", "00100", "11111", "00100", "00100", "00000"),
    ".": ("00000", "00000", "00000", "00000", "00000", "00110", "00110"),
    "/": ("00001", "00010", "00100", "01000", "10000", "00000", "00000"),
    ":": ("00000", "00110", "00110", "00000", "00110", "00110", "00000"),
    "*": ("00000", "10101", "01110", "11111", "01110", "10101", "00000"),
    ">": ("10000", "01000", "00100", "00010", "00100", "01000", "10000"),
    "|": ("00100", "00100", "00100", "00100", "00100", "00100", "00100"),
    "=": ("00000", "11111", "00000", "11111", "00000", "00000", "00000"),
    "[": ("01110", "01000", "01000", "01000", "01000", "01000", "01110"),
    "]": ("01110", "00010", "00010", "00010", "00010", "00010", "01110"),
}

VW, VH, SCALE = 160, 120, 4
SCREEN_X, SCREEN_Y = 40, 35

# Phosphor palette: monochrome green, with no anti-aliased shapes.
CASE = "#202725"
CASE_EDGE = "#48534d"
CRT = "#07100a"
GRID = "#0b1d10"
DIM = "#315b35"
GREEN = "#78d47d"
BRIGHT = "#c5ffc4"
ALERT = "#b7ff9f"
RED = "#ff7969"


class PixelMonitor:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.playing = True
        self.fx_focus = False
        self.clip = False
        self.eq_band = 1
        self.started = time.perf_counter()

        root.title("FX Machine — Retro Monitor UI Concept")
        root.configure(bg="#101514")
        root.resizable(False, False)
        root.geometry("720x560")
        root.bind("e", self._cycle_eq)
        root.bind("f", self._toggle_fx)
        root.bind("c", self._toggle_clip)
        root.bind("<space>", self._toggle_play)
        root.bind("<Escape>", lambda _event: root.destroy())

        self.canvas = tk.Canvas(root, width=720, height=560, bg="#101514", highlightthickness=0)
        self.canvas.pack()
        self._draw_case()
        self._tick()

    def px(self, x: int, y: int, colour: str, tag: str = "dynamic") -> None:
        self.canvas.create_rectangle(SCREEN_X + x * SCALE, SCREEN_Y + y * SCALE,
                                     SCREEN_X + (x + 1) * SCALE - 1,
                                     SCREEN_Y + (y + 1) * SCALE - 1,
                                     fill=colour, outline="", tags=tag)

    def rect(self, x: int, y: int, w: int, h: int, colour: str, tag: str = "dynamic") -> None:
        self.canvas.create_rectangle(SCREEN_X + x * SCALE, SCREEN_Y + y * SCALE,
                                     SCREEN_X + (x + w) * SCALE - 1,
                                     SCREEN_Y + (y + h) * SCALE - 1,
                                     fill=colour, outline="", tags=tag)

    def line(self, x1: int, y1: int, x2: int, y2: int, colour: str, tag: str = "dynamic") -> None:
        self.canvas.create_line(SCREEN_X + x1 * SCALE, SCREEN_Y + y1 * SCALE,
                                SCREEN_X + x2 * SCALE, SCREEN_Y + y2 * SCALE,
                                fill=colour, width=SCALE, tags=tag)

    def text(self, x: int, y: int, value: str, colour: str = GREEN,
             scale: int = 1, tag: str = "dynamic") -> None:
        cursor = x
        for char in value.upper():
            glyph = FONT.get(char, FONT[" "])
            for gy, row in enumerate(glyph):
                for gx, bit in enumerate(row):
                    if bit == "1":
                        for sy in range(scale):
                            for sx in range(scale):
                                self.px(cursor + gx * scale + sx, y + gy * scale + sy, colour, tag)
            cursor += (6 if len(glyph[0]) >= 5 else 4) * scale

    def _draw_case(self) -> None:
        c = self.canvas
        # CRT enclosure is intentionally not pixel-perfect; the whole screen
        # inside it is. This makes it read as a real terminal monitor.
        c.create_rectangle(16, 12, 704, 548, fill=CASE, outline="#090c0b", width=5)
        c.create_rectangle(21, 17, 699, 543, outline=CASE_EDGE, width=1)
        for x, y in ((31, 27), (689, 27), (31, 533), (689, 533)):
            c.create_oval(x - 8, y - 8, x + 8, y + 8, fill="#101413", outline="#606a63")
            c.create_line(x - 4, y, x + 4, y, fill="#5b655e")
        c.create_rectangle(SCREEN_X - 6, SCREEN_Y - 6,
                           SCREEN_X + VW * SCALE + 5, SCREEN_Y + VH * SCALE + 5,
                           fill="#030604", outline="#56645a", width=2)
        c.create_rectangle(SCREEN_X, SCREEN_Y,
                           SCREEN_X + VW * SCALE - 1, SCREEN_Y + VH * SCALE - 1,
                           fill=CRT, outline="", tags="static_screen")

    def _draw_knob(self, x: int, y: int, value: float, selected: bool) -> None:
        """A minimal one-pixel-rim CRT dial: no filled pseudo-3D hardware."""
        radius = 7
        rim = BRIGHT if selected else GREEN
        for py in range(-radius, radius + 1):
            for px in range(-radius, radius + 1):
                distance = math.sqrt(px * px + py * py)
                if abs(distance - radius) <= 0.45:
                    self.px(x + px, y + py, rim)
        # Four sparse cardinal reference pixels preserve the monitor language.
        for dx, dy in ((0, -9), (9, 0), (0, 9), (-9, 0)):
            self.px(x + dx, y + dy, DIM)
        angle = math.radians(225 - value * 270)
        for step in range(1, 6):
            self.px(x + round(math.cos(angle) * step),
                    y - round(math.sin(angle) * step), BRIGHT)

    def _draw_meter(self, level: float) -> None:
        lit = int(level * 18)
        for index in range(18):
            y = 29 + (17 - index) * 4
            if index < 11:
                on, off = GREEN, "#14351a"
            elif index < 15:
                on, off = ALERT, "#344d21"
            else:
                on, off = RED, "#451a16"
            self.rect(9, y, 5, 2, on if index < lit else off)
            self.px(9, y, BRIGHT if index < lit and index < 15 else on)

    def _box(self, x: int, y: int, width: int, height: int, colour: str = DIM) -> None:
        self.line(x, y, x + width, y, colour)
        self.line(x, y + height, x + width, y + height, colour)
        self.line(x, y, x, y + height, colour)
        self.line(x + width, y, x + width, y + height, colour)
        self.text(x - 1, y - 3, "+", colour)
        self.text(x + width - 1, y - 3, "+", colour)
        self.text(x - 1, y + height - 3, "+", colour)
        self.text(x + width - 1, y + height - 3, "+", colour)

    def _draw_screen(self) -> None:
        now = time.perf_counter() - self.started
        self.canvas.delete("dynamic")

        # CRT raster: dark scan lines and sparse single-pixel phosphor noise.
        for y in range(0, VH, 2):
            self.rect(0, y, VW, 1, GRID)
        for index in range(30):
            self.px((index * 31 + int(now * 2)) % VW, (index * 19) % VH, "#0c2612")

        # Header occupies rows 4-14 exclusively.
        self.text(5, 4, "+-- FX MACHINE --+", BRIGHT)
        self.text(120, 4, "CRT 01", DIM)
        self.line(4, 14, 155, 14, DIM)
        self.text(5, 17, "PLAYING" if self.playing else "STOPPED", GREEN if self.playing else RED)
        self.text(105, 17, "124 0 BPM", BRIGHT)

        # Left output meter: title has its own row, then 18 non-overlapping LEDs.
        self.text(6, 19, "OUT", DIM)
        self._box(5, 24, 13, 84)
        meter_level = 0.5 + 0.35 * abs(math.sin(now * 1.1)) if self.playing else 0.0
        if self.clip:
            meter_level = 0.98
        self._draw_meter(meter_level)
        self.text(6, 104, "CLIP" if self.clip else "SAFE", RED if self.clip else GREEN)

        # EQ: every dial owns a 19-row band. Labels and values sit to the
        # right, never above/below or in the dial's pixel circle.
        self.text(25, 19, "EQ CHANNEL", ALERT)
        self._box(22, 24, 62, 84)
        bands = ("TRIM", "HIGH", "MID", "LOW")
        values = ("-0 2", "+0 0", "+0 0", "+0 0")
        for index, (band, value) in enumerate(zip(bands, values)):
            y = 39 + index * 19
            selected = index == self.eq_band
            self._draw_knob(42, y, 0.50 + 0.13 * math.sin(now * 0.5 + index), selected)
            self.text(53, y - 5, band, BRIGHT if selected else GREEN)
            self.text(53, y + 4, value, ALERT if selected else DIM)

        # Session monitor: title and four rows have an 8-pixel baseline grid.
        self._box(88, 24, 67, 42)
        self.text(91, 27, "SESSION NAV", ALERT)
        self.text(91, 35, "BMK SONG1", GREEN)
        self.text(91, 43, "GRP DRUMS", GREEN)
        self.text(91, 51, "TRK TOM", GREEN)
        self.text(91, 59, "SCN SONG1", GREEN)

        # FX matrix: titles, dials and one-character legends occupy separate rows.
        self._box(88, 68, 67, 40)
        self.text(91, 70, "FX", ALERT if self.fx_focus else GREEN)
        names = ("F", "M", "R", "S", "V", "N", "D", "W")
        for index, name in enumerate(names):
            col, row = index % 4, index // 4
            x, y = 98 + col * 18, 80 + row * 19
            self._draw_knob(x, y, 0.20 + 0.65 * ((math.sin(now * .4 + index) + 1) / 2), self.fx_focus and index == 0)
            self.text(x - 2, y + 7, name, BRIGHT if self.fx_focus and index == 0 else DIM)

        self.line(4, 110, 155, 110, DIM)
        self.text(5, 113, "> E EQ F FX C CLIP", DIM)

    def _tick(self) -> None:
        if self.root.winfo_exists():
            self._draw_screen()
            self.root.after(80, self._tick)

    def _cycle_eq(self, _event=None) -> None:
        self.eq_band = (self.eq_band + 1) % 4

    def _toggle_fx(self, _event=None) -> None:
        self.fx_focus = not self.fx_focus

    def _toggle_clip(self, _event=None) -> None:
        self.clip = not self.clip

    def _toggle_play(self, _event=None) -> None:
        self.playing = not self.playing


def main() -> int:
    root = tk.Tk()
    PixelMonitor(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
