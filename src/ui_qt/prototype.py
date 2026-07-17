"""Launch the non-destructive PySide6 visual prototype.

Run from the project root:
    python -m src.ui_qt.prototype

It uses simulated values only and never starts OSC, pygame, or Ableton control.
"""

from __future__ import annotations

import math
import sys
import time

try:
    from PySide6.QtCore import QTimer, Qt
    from PySide6.QtWidgets import QApplication, QGridLayout, QHBoxLayout, QLabel, QMainWindow, QVBoxLayout, QWidget
except ModuleNotFoundError as exc:
    if exc.name == "PySide6":
        raise SystemExit(
            "The UI prototype needs PySide6. Install it with:\n"
            f"  {sys.executable} -m pip install PySide6"
        ) from exc
    raise

from . import theme
from .widgets import AnalogKnob, HardwarePanel, LedMeter, MomentaryButton, StatusLed


class PrototypeWindow(QMainWindow):
    """Phase-one visual shell with simulated signal and macro values."""

    def __init__(self):
        super().__init__()
        self.started_at = time.monotonic()
        self.setWindowTitle("FX Machine — Modular Hardware UI Prototype")
        self.setMinimumSize(950, 700)
        self.resize(1100, 760)
        self._build()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._animate_demo)
        self.timer.start(40)

    def _build(self) -> None:
        root = QWidget()
        root.setStyleSheet(theme.STYLE_SHEET)
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(10)

        # Header: state should be information-dense without becoming a dashboard.
        header = QHBoxLayout()
        title = QLabel("FX MACHINE")
        title.setStyleSheet(f"color: {theme.TEXT}; font-size: 18px; font-weight: bold; letter-spacing: 3px;")
        subtitle = QLabel("MODULAR PERFORMANCE CONSOLE  /  UI STUDY 01")
        subtitle.setStyleSheet(f"color: {theme.TEXT_FAINT}; font-size: 8px; letter-spacing: 1px;")
        header.addWidget(title)
        header.addWidget(subtitle)
        header.addStretch()
        self.osc_led = StatusLed("Ableton OSC", True)
        self.ctrl_led = StatusLed("Controller", True)
        header.addWidget(self.osc_led)
        header.addSpacing(12)
        header.addWidget(self.ctrl_led)
        layout.addLayout(header)

        transport = QLabel("● PLAYING     124.0 BPM                              SCENE 03  /  WARM UP")
        transport.setAlignment(Qt.AlignmentFlag.AlignCenter)
        transport.setStyleSheet(
            f"background: {theme.PANEL_INSET}; border: 1px solid {theme.PANEL_EDGE_LIGHT}; "
            f"color: {theme.GREEN}; padding: 8px; font-family: '{theme.FONT_READOUT}'; font-size: 11px;"
        )
        layout.addWidget(transport)

        modules = QGridLayout()
        modules.setSpacing(10)
        layout.addLayout(modules, 1)

        # INPUT / EQ
        eq_panel = HardwarePanel("Input / EQ", "SOURCE → TONE")
        eq_layout = QHBoxLayout(eq_panel)
        eq_layout.setContentsMargins(14, 25, 14, 12)
        self.meter = LedMeter()
        eq_layout.addWidget(self.meter)
        knobs = QGridLayout()
        self.trim = AnalogKnob("Trim", -18, 10.5, 0, "dB")
        self.high = AnalogKnob("High", -19, 6, 0, "dB")
        self.mid = AnalogKnob("Mid", -19, 6, 0, "dB")
        self.low = AnalogKnob("Low", -60, 2, 0, "dB")
        self.mid.set_selected(True)
        knobs.addWidget(self.trim, 0, 0)
        knobs.addWidget(self.high, 0, 1)
        knobs.addWidget(self.mid, 1, 0)
        knobs.addWidget(self.low, 1, 1)
        eq_layout.addLayout(knobs, 1)
        modules.addWidget(eq_panel, 0, 0, 2, 1)

        # FX macro bank
        fx_panel = HardwarePanel("FX Engine", "DRY + WET PERFORMANCE PATH")
        fx_layout = QGridLayout(fx_panel)
        fx_layout.setContentsMargins(14, 25, 14, 12)
        self.fx_knobs = [
            AnalogKnob("Filter", 0, 127, 74, "", theme.AMBER),
            AnalogKnob("Resonance", 0, 127, 18, "", theme.AMBER),
            AnalogKnob("Reverb", 0, 127, 42, "", theme.BLUE),
            AnalogKnob("FX Send", 0, 100, 0, "%", theme.BLUE),
            AnalogKnob("Delay FB", 0, 92, 36, "%", theme.BLUE),
            AnalogKnob("Width", 0, 127, 64, "", theme.AMBER),
        ]
        for index, knob in enumerate(self.fx_knobs):
            fx_layout.addWidget(knob, index // 3, index % 3)
        modules.addWidget(fx_panel, 0, 1)

        # Performance / momentary effects
        perf_panel = HardwarePanel("Performance", "MOMENTARY / SAFETY")
        perf_layout = QVBoxLayout(perf_panel)
        perf_layout.setContentsMargins(14, 25, 14, 12)
        self.stutter = MomentaryButton("STUTTER", theme.AMBER)
        self.bass_cut = MomentaryButton("BASS CUT", theme.RED)
        self.fx_throw = MomentaryButton("FX THROW", theme.BLUE)
        for button in (self.stutter, self.bass_cut, self.fx_throw):
            perf_layout.addWidget(button)
        perf_layout.addStretch()
        info = QLabel("EQ MODE: MID\nBASS PROTECT: ON\nWET LOCK: OFF")
        info.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-family: '{theme.FONT_READOUT}'; font-size: 9px;")
        perf_layout.addWidget(info)
        modules.addWidget(perf_panel, 1, 1)

        flow = QLabel("SIGNAL FLOW     INPUT  →  TRIM  →  EQ  →  FILTER  →  WET SEND  →  REVERB / DELAY  →  WIDTH  →  MASTER")
        flow.setAlignment(Qt.AlignmentFlag.AlignCenter)
        flow.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 8px; letter-spacing: 1px; padding: 7px;")
        layout.addWidget(flow)

    def _animate_demo(self) -> None:
        """Subtle simulated telemetry for evaluating the visual language only."""
        elapsed = time.monotonic() - self.started_at
        level = 0.48 + 0.33 * abs(math.sin(elapsed * 1.8)) + 0.10 * math.sin(elapsed * 8.0)
        peak = min(1.0, level + 0.15)
        self.meter.set_levels(level, peak)
        self.fx_knobs[0].set_value(64 + 43 * math.sin(elapsed * 0.32))
        self.fx_knobs[3].set_value(35 + 35 * math.sin(elapsed * 0.55))
        self.fx_knobs[4].set_value(42 + 20 * math.sin(elapsed * 0.20))
        self.stutter.set_active(math.sin(elapsed * 1.0) > 0.94)
        self.fx_throw.set_active(math.sin(elapsed * 0.55) > 0.92)


def main() -> int:
    app = QApplication(sys.argv)
    window = PrototypeWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
