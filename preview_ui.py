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
        # The design itself stays a 760×900 logical canvas. On a small laptop
        # the preview chooses a 75% display-only fit mode; source skin files
        # are never stretched or resized at runtime.
        self.scale = 0.75 if root.winfo_screenheight() < 900 else 1.0
        self.ui_w = round(W * self.scale)
        self.ui_h = round(H * self.scale)
        self.compact = self.scale < 1.0
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
        root.geometry(f"{self.ui_w}x{self.ui_h}")

        self.canvas = tk.Canvas(root, width=self.ui_w, height=self.ui_h, bg=FACE,
                                highlightthickness=0)
        self.canvas.pack()
        self._load_images()
        self._bind_keys()
        self._draw_static()
        self._tick()

    def _load_2x(self, filename: str) -> tk.PhotoImage:
        path = SKIN / filename
        if not path.is_file():
            raise FileNotFoundError(f"Missing preview skin asset: {path}")
        return tk.PhotoImage(file=path).subsample(2, 2)

    def _load_frame_set(self, size: str, kind: str) -> list[tk.PhotoImage]:
        folder = SKIN / "knob_frames" / size / kind
        return [self._load_2x(str(Path("knob_frames") / size / kind / f"{index:02d}.png"))
                for index in range(12)]

    def _load_images(self) -> None:
        try:
            master = "faceplate_master_1140x1350.png" if self.compact else str(Path("..") / "panel_masters" / "faceplate_master.png")
            frame_size = "compact" if self.compact else "full"
            self.images = {"hardware": self._load_2x(master)}
            self.eq_frames = self._load_frame_set(frame_size, "eq")
            self.fx_frames = self._load_frame_set(frame_size, "fx")
        except (tk.TclError, FileNotFoundError) as exc:
            raise SystemExit(f"Cannot load the standalone UI skin:\n{exc}") from exc

    def _point(self, x: float, y: float) -> tuple[int, int]:
        return round(x * self.scale), round(y * self.scale)

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
        c.create_image(0, 0, anchor="nw", image=self.images["hardware"], tags="hardware")

        # Faceplate labels are screen-printed material labels. Knob caps rotate
        # as complete sprites in _draw_dynamic(), rather than using a fake line.
        c.create_text(16, 22, text="FX MACHINE", anchor="w", fill="#e4ded2",
                      font=("Segoe UI", 11, "bold"), tags="base")
        c.create_text(744, 22, text="SKIN PREVIEW", anchor="e", fill="#7d877e",
                      font=("Consolas", 7, "bold"), tags="base")
        c.create_line(12, 42, 748, 42, fill="#3e5146", width=2, tags="base")
        c.create_text(20, 91, text="INPUT / EQ", anchor="w", fill="#a6b19f",
                      font=("Consolas", 7, "bold"), tags="base")
        c.create_text(285, 418, text="FX ENGINE", anchor="w", fill="#a6b19f",
                      font=("Consolas", 7, "bold"), tags="base")
        c.create_text(25, 890, text="STANDALONE VISUAL TEST  •  NO ABLETON / OSC / CONTROLLER REQUIRED",
                      anchor="w", fill="#7c8880", font=("Consolas", 7, "bold"), tags="base")
        if self.compact:
            c.scale("base", 0, 0, self.scale, self.scale)

        # These are logical 760×900 positions; _point applies preview-only fit.
        self.eq_positions = [(178, 210), (178, 323), (178, 444), (178, 566)]
        self.fx_positions = [(355, 502), (460, 502), (565, 502), (670, 502),
                             (355, 605), (460, 605), (565, 605), (670, 605)]
        self.eq_knob_items = []
        self.fx_knob_items = []
        for x, y in self.eq_positions:
            px, py = self._point(x, y)
            self.eq_knob_items.append(c.create_image(px, py, anchor="center", image=self.eq_frames[0], tags="knobcap"))
        for x, y in self.fx_positions:
            px, py = self._point(x, y)
            self.fx_knob_items.append(c.create_image(px, py, anchor="center", image=self.fx_frames[0], tags="knobcap"))

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
        x1, x2, bottom = 52, 63, 626
        segments, height, gap = 22, 14, 8
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
        c.create_rectangle(34, 134, 72, 145,
                           fill="#72231f" if self.clip else "#1d1010",
                           outline="#9f4238" if self.clip else "#42201d",
                           tags="dynamic")
        c.create_text(53, 140, text="CLIP", fill="#fff0e6" if self.clip else "#75413d",
                      font=("Consolas", 6, "bold"), tags="dynamic")

    def _draw_lcd(self) -> None:
        c = self.canvas
        # These coordinates map to the INNER screen area of the 500×250 bezel.
        x0, y0, x1, y1 = 305, 135, 710, 305
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
            frame = min(11, max(0, round(value * 11)))
            c.itemconfig(self.eq_knob_items[index], image=self.eq_frames[frame])
            if selected:
                c.create_oval(x - 43, y - 43, x + 43, y + 43, outline=LCD_AMBER, width=2, tags="dynamic")
            c.create_text(x, y - 51, text=label, fill=LCD_AMBER if selected else "#d9d5ca",
                          font=("Consolas", 8, "bold"), tags="dynamic")
            c.create_text(x, y + 51, text=("+0.0 dB" if index else "-0.2 dB"),
                          fill=LCD_TEXT, font=("Consolas", 7, "bold"), tags="dynamic")

        fx_names = ("FILTER", "MODE", "RES", "STUTTER", "REVERB", "SEND", "DELAY", "WIDTH")
        for index, ((x, y), name) in enumerate(zip(self.fx_positions, fx_names)):
            value = 0.15 + 0.7 * ((math.sin(elapsed * 0.4 + index) + 1) / 2)
            accent = LCD_AMBER if index < 4 else "#5e9fc8"
            frame = min(11, max(0, round(value * 11)))
            c.itemconfig(self.fx_knob_items[index], image=self.fx_frames[frame])
            c.create_text(x, y + 35, text=name, fill="#c4c8bd", font=("Consolas", 6, "bold"), tags="dynamic")
            c.create_text(x, y + 48, text=f"{int(value * 127):03}", fill=accent,
                          font=("Consolas", 7, "bold"), tags="dynamic")

        self._draw_lcd()
        c.create_text(32, 775, text="EQ MODE: " + bands[self.eq_band], anchor="w",
                      fill=LCD_AMBER, font=("Consolas", 7, "bold"), tags="dynamic")
        c.create_text(720, 775, text="FX: " + ("ACTIVE" if self.fx_active else "READY"), anchor="e",
                      fill=LCD_AMBER if self.fx_active else LCD_DIM,
                      font=("Consolas", 7, "bold"), tags="dynamic")
        c.create_text(45, 815, text="● VISUAL SYSTEM ONLINE", anchor="w", fill=LCD_GREEN,
                      font=("Consolas", 7, "bold"), tags="dynamic")
        if self.compact:
            # Canvas coordinates scale, while compact sprite frames remain
            # pixel-sharp pre-rendered assets.
            c.scale("dynamic", 0, 0, self.scale, self.scale)

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
