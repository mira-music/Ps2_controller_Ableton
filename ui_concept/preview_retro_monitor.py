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
ALERT = "#d6ff80"
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
        # 17×17 pixel dial. The ring and pointer are all quantized to the
        # virtual pixel grid—no Canvas ovals or anti-aliasing inside the CRT.
        radius, inner = 8, 6
        for py in range(-radius, radius + 1):
            for px in range(-radius, radius + 1):
                distance = math.sqrt(px * px + py * py)
                if inner <= distance <= radius:
                    self.px(x + px, y + py, ALERT if selected else DIM)
                elif distance < inner:
                    self.px(x + px, y + py, "#0e2112")
        angle = math.radians(225 - value * 270)
        for step in range(1, 7):
            self.px(x + round(math.cos(angle) * step),
                    y - round(math.sin(angle) * step), BRIGHT)

    def _draw_meter(self, level: float) -> None:
        lit = int(level * 20)
        for index in range(20):
            y = 25 + (19 - index) * 4
            if index < 12:
                on, off = GREEN, "#17361c"
            elif index < 17:
                on, off = ALERT, "#384013"
            else:
                on, off = RED, "#431714"
            self.rect(8, y, 5, 3, on if index < lit else off)
            if index < lit:
                self.line(8, y, 12, y, BRIGHT)

    def _draw_screen(self) -> None:
        now = time.perf_counter() - self.started
        self.canvas.delete("dynamic")

        # Fixed scanlines and sparse low-brightness pixel noise.
        for y in range(0, VH, 2):
            self.rect(0, y, VW, 1, GRID)
        for index in range(40):
            x = (index * 29 + int(now * 3)) % VW
            y = (index * 17) % VH
            self.px(x, y, "#0d2713")

        self.text(5, 4, "FX MACHINE", BRIGHT, 1)
        self.text(121, 4, "V 1 0", DIM, 1)
        self.line(4, 14, 155, 14, DIM)
        self.text(5, 18, "PLAYING" if self.playing else "STOPPED", GREEN if self.playing else RED, 1)
        self.text(105, 18, "124 0 BPM", BRIGHT, 1)

        # EQ channel / meter region.
        self.text(5, 25, "OUT", DIM, 1)
        level = 0.5 + 0.35 * abs(math.sin(now * 1.1)) if self.playing else 0.0
        if self.clip:
            level = 0.98
        self._draw_meter(level)
        self.text(5, 108, "CLIP" if self.clip else "SAFE", RED if self.clip else GREEN, 1)

        self.text(25, 25, "EQ CHANNEL", ALERT, 1)
        bands = ("TRIM", "HIGH", "MID", "LOW")
        values = ("-0 2", "+0 0", "+0 0", "+0 0")
        for index, (band, value) in enumerate(zip(bands, values)):
            y = 37 + index * 19
            selected = index == self.eq_band
            self.text(28, y - 9, band, ALERT if selected else GREEN, 1)
            self._draw_knob(52, y, 0.50 + 0.13 * math.sin(now * 0.5 + index), selected)
            self.text(65, y - 2, value, BRIGHT if selected else DIM, 1)

        # Central terminal session block.
        self.rect(82, 25, 73, 42, "#09160c")
        self.line(82, 25, 154, 25, DIM)
        self.line(82, 66, 154, 66, DIM)
        self.text(85, 28, "SESSION NAV", ALERT, 1)
        self.text(85, 36, "BMK SONG1", GREEN, 1)
        self.text(85, 43, "GROUP DRUMS", GREEN, 1)
        self.text(85, 50, "TRK TOM KICK", GREEN, 1)
        self.text(85, 57, "SCN SONG1", GREEN, 1)

        # Eight pixel-FX dials in a compact 4×2 bank.
        self.text(85, 72, "FX MATRIX", ALERT if self.fx_focus else GREEN, 1)
        names = ("FIL", "MOD", "RES", "STU", "REV", "SND", "DLY", "WID")
        for index, name in enumerate(names):
            col, row = index % 4, index // 4
            x, y = 91 + col * 17, 86 + row * 19
            self._draw_knob(x, y, 0.20 + 0.65 * ((math.sin(now * .4 + index) + 1) / 2), self.fx_focus and index == 0)
            self.text(x - 5, y + 10, name, DIM, 1)

        self.line(4, 113, 155, 113, DIM)
        self.text(5, 115, "> E EQ F FX C CLIP", DIM, 1)

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
