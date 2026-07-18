#!/usr/bin/env python3
"""Standalone FX Machine hardware-skin preview.

This preview deliberately has **no dependency on Ableton, OSC, pygame, or the
main FX Machine application**. It is a visual test bench for the fixed 760 ×
900 logical hardware UI and its editable 2× PNG skin assets.

Run:
    python preview_ui.py

Keys:
    Space  toggle PLAYING / STOPPED
    E      cycle selected EQ band
    F      toggle FX mode
    C      toggle CLIP warning
    Esc    close
"""

from __future__ import annotations

import math
import random
import sys
import time
from pathlib import Path
import tkinter as tk


ROOT = Path(__file__).resolve().parent
SKIN = ROOT / "assets" / "ui_textures" / "ui_pngs" / "hd_default"
W, H = 760, 900

# TN/terminal palette used only by this standalone visual preview.
FACE = "#151817"
LCD_TEXT = "#acc99b"
LCD_DIM = "#60735c"
LCD_AMBER = "#d2a64d"
LCD_GREEN = "#73b777"
LCD_RED = "#c94e45"


class HardwarePreview:
    """Fixed-resolution visual mock-up with simulated controls and meter data."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.playing = True
        self.fx_active = False
        self.clip = False
        self.eq_band = 1
        self.started_at = time.perf_counter()
        self.last_draw = 0.0
        self.images: dict[str, tk.PhotoImage] = {}

        root.title("FX Machine — Hardware Skin Preview (standalone)")
        root.configure(bg=FACE)
        root.resizable(False, False)
        root.geometry(f"{W}x{H}")

        self.canvas = tk.Canvas(root, width=W, height=H, bg=FACE,
                                highlightthickness=0)
        self.canvas.pack()
        self._load_images()
        self._bind_keys()
        self._draw_static()
        self._tick()

    def _load_hd(self, filename: str) -> tk.PhotoImage:
        path = SKIN / filename
        if not path.is_file():
            raise FileNotFoundError(f"Missing preview skin asset: {path}")
        # Every source image in hd_default is exactly 2× its logical size.
        return tk.PhotoImage(file=path).subsample(2, 2)

    def _load_images(self) -> None:
        try:
            self.images = {
                "faceplate": self._load_hd("faceplate_1520x1800.png"),
                "eq_panel": self._load_hd("eq_channel_400x1000.png"),
                "lcd_bezel": self._load_hd("session_lcd_bezel_1000x500.png"),
                "fx_panel": self._load_hd("fx_module_1440x480.png"),
                "eq_knob": self._load_hd("eq_knob_164x164.png"),
                "fx_knob": self._load_hd("fx_knob_112x112.png"),
            }
        except (tk.TclError, FileNotFoundError) as exc:
            raise SystemExit(f"Cannot load the standalone UI skin:\n{exc}") from exc

    def _bind_keys(self) -> None:
        self.root.bind("<space>", lambda _event: self._toggle("play"))
        self.root.bind("e", lambda _event: self._toggle("eq"))
        self.root.bind("f", lambda _event: self._toggle("fx"))
        self.root.bind("c", lambda _event: self._toggle("clip"))
        self.root.bind("<Escape>", lambda _event: self.root.destroy())

    def _toggle(self, action: str) -> None:
        if action == "play":
            self.playing = not self.playing
        elif action == "eq":
            self.eq_band = (self.eq_band + 1) % 4
        elif action == "fx":
            self.fx_active = not self.fx_active
        elif action == "clip":
            self.clip = not self.clip
        self._draw_dynamic(force=True)

    def _draw_static(self) -> None:
        c = self.canvas
        c.create_image(0, 0, anchor="nw", image=self.images["faceplate"], tags="base")

        # Physical module placements use the 760×900 logical design grid.
        c.create_image(12, 104, anchor="nw", image=self.images["eq_panel"], tags="base")
        c.create_image(242, 104, anchor="nw", image=self.images["lcd_bezel"], tags="base")
        c.create_image(20, 642, anchor="nw", image=self.images["fx_panel"], tags="base")

        # Faceplate labels are static material labels; real values remain dynamic.
        c.create_text(16, 22, text="FX MACHINE", anchor="w", fill="#e4ded2",
                      font=("Segoe UI", 11, "bold"), tags="base")
        c.create_text(744, 22, text="SKIN PREVIEW", anchor="e", fill="#7d877e",
                      font=("Consolas", 7, "bold"), tags="base")
        c.create_line(12, 42, 748, 42, fill="#3e5146", width=2, tags="base")
        c.create_text(20, 91, text="INPUT / EQ", anchor="w", fill="#a6b19f",
                      font=("Consolas", 7, "bold"), tags="base")
        c.create_text(25, 630, text="FX ENGINE", anchor="w", fill="#a6b19f",
                      font=("Consolas", 7, "bold"), tags="base")
        c.create_text(25, 890, text="STANDALONE VISUAL TEST  •  NO ABLETON / OSC / CONTROLLER REQUIRED",
                      anchor="w", fill="#7c8880", font=("Consolas", 7, "bold"), tags="base")

        # Physical knob caps placed exactly over their panel wells.
        self.eq_positions = [(150, 180), (150, 300), (150, 420), (150, 540)]
        self.fx_positions = [(130, 706), (290, 706), (455, 706), (625, 706),
                             (130, 814), (290, 814), (455, 814), (625, 814)]
        for x, y in self.eq_positions:
            c.create_image(x, y, anchor="center", image=self.images["eq_knob"], tags="knobcap")
        for x, y in self.fx_positions:
            c.create_image(x, y, anchor="center", image=self.images["fx_knob"], tags="knobcap")

    def _lcd_text(self, x: int, y: int, text: str, fill: str = LCD_TEXT,
                  size: int = 8, anchor: str = "w") -> None:
        self.canvas.create_text(x, y, text=text, fill=fill, anchor=anchor,
                                font=("Consolas", size, "bold"), tags="dynamic")

    def _indicator(self, x: int, y: int, value: float, colour: str, radius: int) -> None:
        angle = math.radians(-90 + 270 * value)
        end_x = x + math.cos(angle) * radius
        end_y = y + math.sin(angle) * radius
        self.canvas.create_line(x, y, end_x, end_y, fill=colour, width=2,
                                capstyle="round", tags="dynamic")

    def _draw_meter(self, level: float) -> None:
        c = self.canvas
        # Align with the left well in the EQ texture.
        x1, x2, bottom = 53, 62, 594
        segments, height, gap = 22, 10, 3
        lit = int(level * segments)
        for index in range(segments):
            y2 = bottom - index * (height + gap)
            y1 = y2 - height
            if index < 14:
                on, off = "#7ab44d", "#173018"
            elif index < 19:
                on, off = "#d6a83d", "#382d13"
            else:
                on, off = "#cf4e42", "#3a1514"
            c.create_rectangle(x1, y1, x2, y2, fill=on if index < lit else off,
                               outline="", tags="dynamic")
        c.create_rectangle(39, 136, 77, 147,
                           fill="#72231f" if self.clip else "#1d1010",
                           outline="#9f4238" if self.clip else "#42201d",
                           tags="dynamic")
        c.create_text(58, 142, text="CLIP", fill="#fff0e6" if self.clip else "#75413d",
                      font=("Consolas", 6, "bold"), tags="dynamic")

    def _draw_lcd(self) -> None:
        c = self.canvas
        # These coordinates map to the INNER screen area of the 500×250 bezel.
        x0, y0, x1, y1 = 284, 143, 696, 313
        # The bezel already supplies its material screen texture. Draw only
        # subtle TN scanlines and terminal data above it.
        for y in range(y0 + 2, y1, 4):
            c.create_line(x0, y, x1, y, fill="#0a100c", tags="dynamic")
        for x in range(x0 + 12, x1, 28):
            c.create_line(x, y0, x, y1, fill="#142119", tags="dynamic")

        self._lcd_text(x0 + 8, y0 + 10, "SESSION NAVIGATOR", "#d4dca5", 7)
        self._lcd_text(x1 - 8, y0 + 10, "TN LIVE VIEW", LCD_DIM, 7, "e")
        c.create_line(x0 + 7, y0 + 18, x1 - 7, y0 + 18, fill="#3d5142", tags="dynamic")
        self._lcd_text(x0 + 8, y0 + 33, "BMARK", LCD_DIM, 6)
        self._lcd_text(x0 + 62, y0 + 33, "SONG1 END", LCD_AMBER, 8)
        self._lcd_text(x1 - 8, y0 + 33, "02/02", LCD_AMBER, 6, "e")
        self._lcd_text(x0 + 8, y0 + 50, "GROUP", LCD_DIM, 6)
        self._lcd_text(x0 + 62, y0 + 50, "DRUMS", LCD_TEXT, 8)
        self._lcd_text(x0 + 8, y0 + 69, "TRACK", LCD_DIM, 6)
        self._lcd_text(x0 + 62, y0 + 69, "* TOM KICK", "#d4dca5", 8)
        self._lcd_text(x0 + 8, y0 + 86, "SCENE", LCD_DIM, 6)
        self._lcd_text(x0 + 62, y0 + 86, "§ SONG1 END", LCD_TEXT, 8)
        self._lcd_text(x0 + 8, y0 + 103, "CLIP", LCD_DIM, 6)
        self._lcd_text(x0 + 62, y0 + 103, "TOM  KICK", LCD_TEXT, 8)
        c.create_line(x0 + 7, y0 + 112, x1 - 7, y0 + 112, fill="#3d5142", tags="dynamic")
        self._lcd_text(x0 + 70, y0 + 128, "SCENE", LCD_DIM, 6, "center")
        self._lcd_text(x0 + 210, y0 + 128, "TRACK", LCD_DIM, 6, "center")
        self._lcd_text(x0 + 350, y0 + 128, "BMARK", LCD_DIM, 6, "center")
        self._lcd_text(x0 + 70, y0 + 145, "08", LCD_TEXT, 10, "center")
        self._lcd_text(x0 + 210, y0 + 145, "02", LCD_TEXT, 10, "center")
        self._lcd_text(x0 + 350, y0 + 145, "02", LCD_AMBER, 10, "center")
        self._lcd_text(x0 + 8, y0 + 160,
                       "● OSC     ● CTRL     ■ CLIP", LCD_GREEN if not self.clip else LCD_RED, 6)

    def _draw_dynamic(self, force: bool = False) -> None:
        now = time.perf_counter()
        if not force and now - self.last_draw < 0.075:
            return
        self.last_draw = now
        c = self.canvas
        c.delete("dynamic")

        transport = "▶ PLAYING" if self.playing else "■ STOPPED"
        transport_colour = LCD_GREEN if self.playing else LCD_RED
        c.create_text(16, 61, text=transport, anchor="w", fill=transport_colour,
                      font=("Consolas", 10, "bold"), tags="dynamic")
        c.create_text(744, 61, text="124.0 BPM", anchor="e", fill="#e1dbca",
                      font=("Consolas", 9, "bold"), tags="dynamic")

        elapsed = now - self.started_at
        meter = 0.38 + 0.48 * abs(math.sin(elapsed * 1.3))
        if self.clip:
            meter = 0.96
        self._draw_meter(meter)

        bands = ("TRIM", "HIGH", "MID", "LOW")
        for index, ((x, y), label) in enumerate(zip(self.eq_positions, bands)):
            selected = index == self.eq_band
            value = 0.50 + 0.16 * math.sin(elapsed * 0.45 + index)
            self._indicator(x, y, value, LCD_AMBER if selected else "#ded8c9", 31)
            c.create_text(x, y - 51, text=label, fill=LCD_AMBER if selected else "#d9d5ca",
                          font=("Consolas", 8, "bold"), tags="dynamic")
            c.create_text(x, y + 51, text=("+0.0 dB" if index else "-0.2 dB"),
                          fill=LCD_TEXT, font=("Consolas", 7, "bold"), tags="dynamic")

        fx_names = ("FILTER", "MODE", "RES", "STUTTER", "REVERB", "SEND", "DELAY", "WIDTH")
        for index, ((x, y), name) in enumerate(zip(self.fx_positions, fx_names)):
            value = 0.15 + 0.7 * ((math.sin(elapsed * 0.4 + index) + 1) / 2)
            accent = LCD_AMBER if index < 4 else "#5e9fc8"
            self._indicator(x, y, value, accent, 20)
            c.create_text(x, y + 35, text=name, fill="#c4c8bd", font=("Consolas", 6, "bold"), tags="dynamic")
            c.create_text(x, y + 48, text=f"{int(value * 127):03}", fill=accent,
                          font=("Consolas", 7, "bold"), tags="dynamic")

        self._draw_lcd()
        c.create_text(25, 614, text="EQ MODE: " + bands[self.eq_band], anchor="w",
                      fill=LCD_AMBER, font=("Consolas", 7, "bold"), tags="dynamic")
        c.create_text(720, 614, text="FX: " + ("ACTIVE" if self.fx_active else "READY"), anchor="e",
                      fill=LCD_AMBER if self.fx_active else LCD_DIM,
                      font=("Consolas", 7, "bold"), tags="dynamic")
        c.create_text(25, 872, text="● VISUAL SYSTEM ONLINE", anchor="w", fill=LCD_GREEN,
                      font=("Consolas", 7, "bold"), tags="dynamic")

    def _tick(self) -> None:
        if self.root.winfo_exists():
            self._draw_dynamic()
            self.root.after(40, self._tick)


def main() -> int:
    root = tk.Tk()
    HardwarePreview(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
