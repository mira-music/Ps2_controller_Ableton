"""Reusable, custom-painted widgets for the modular hardware UI prototype."""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QVBoxLayout, QWidget

from . import theme


def colour(value: str) -> QColor:
    return QColor(value)


class HardwarePanel(QFrame):
    """A labelled, bevelled module panel with a subtle engraved title."""

    def __init__(self, title: str, subtitle: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.title = title
        self.subtitle = subtitle
        self.setObjectName("hardwarePanel")
        self.setContentsMargins(12, 22, 12, 12)
        self.setMinimumHeight(100)

    def paintEvent(self, event):  # noqa: N802 - Qt API name
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(1, 1, -1, -1)
        painter.fillRect(rect, colour(theme.PANEL))
        painter.setPen(QPen(colour(theme.PANEL_EDGE_DARK), 2))
        painter.drawRect(rect)
        painter.setPen(QPen(colour(theme.PANEL_EDGE_LIGHT), 1))
        painter.drawLine(rect.left() + 1, rect.top() + 1, rect.right() - 1, rect.top() + 1)
        painter.drawLine(rect.left() + 1, rect.top() + 1, rect.left() + 1, rect.bottom() - 1)

        painter.setPen(colour(theme.TEXT_MUTED))
        painter.setFont(QFont(theme.FONT_LABEL, 8, QFont.Weight.Bold))
        painter.drawText(12, 15, self.title.upper())
        if self.subtitle:
            painter.setPen(colour(theme.TEXT_FAINT))
            painter.setFont(QFont(theme.FONT_LABEL, 7))
            painter.drawText(self.width() - 12 - painter.fontMetrics().horizontalAdvance(self.subtitle), 15, self.subtitle)
        super().paintEvent(event)


class AnalogKnob(QWidget):
    """Custom-drawn rotary display; intentionally display-only for phase one."""

    def __init__(self, label: str, minimum: float = 0, maximum: float = 127,
                 value: float = 0, unit: str = "", accent: str = theme.AMBER,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.label, self.minimum, self.maximum = label, minimum, maximum
        self.value, self.unit, self.accent = value, unit, accent
        self.selected = False
        self.setMinimumSize(112, 145)
        self.setToolTip(f"{label}: live control integration is planned for phase 3")

    def set_value(self, value: float) -> None:
        self.value = max(self.minimum, min(self.maximum, value))
        self.update()

    def set_selected(self, selected: bool) -> None:
        self.selected = selected
        self.update()

    def _fraction(self) -> float:
        span = self.maximum - self.minimum
        return 0 if span == 0 else (self.value - self.minimum) / span

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        width, height = self.width(), self.height()
        center = QPointF(width / 2, 66)
        radius = min(width, 118) / 2 - 12
        fraction = self._fraction()
        start, sweep = 225, -270

        # Label and value readout
        painter.setPen(colour(theme.AMBER_GLOW if self.selected else theme.TEXT_MUTED))
        painter.setFont(QFont(theme.FONT_LABEL, 8, QFont.Weight.Bold))
        painter.drawText(QRectF(0, 5, width, 18), Qt.AlignmentFlag.AlignCenter, self.label.upper())
        painter.setPen(colour(self.accent if self.selected else theme.TEXT))
        painter.setFont(QFont(theme.FONT_READOUT, 9, QFont.Weight.Bold))
        painter.drawText(QRectF(0, 122, width, 17), Qt.AlignmentFlag.AlignCenter, self._formatted_value())

        # Calibrated tick marks
        for index in range(13):
            angle = math.radians(start + (sweep * index / 12))
            outer = QPointF(center.x() + math.cos(angle) * (radius + 5), center.y() - math.sin(angle) * (radius + 5))
            tick_len = 7 if index in (0, 6, 12) else 4
            inner = QPointF(center.x() + math.cos(angle) * (radius + 5 - tick_len), center.y() - math.sin(angle) * (radius + 5 - tick_len))
            painter.setPen(QPen(colour(theme.TEXT_MUTED), 1))
            painter.drawLine(outer, inner)

        # Ring and value arc
        ring = QRectF(center.x() - radius, center.y() - radius, radius * 2, radius * 2)
        painter.setPen(QPen(colour(theme.PANEL_INSET), 8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawArc(ring, start * 16, sweep * 16)
        painter.setPen(QPen(colour(self.accent if self.selected else theme.AMBER_DIM), 4,
                            Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawArc(ring, start * 16, int(sweep * fraction * 16))

        # Knob cap, rim, and indicator
        painter.setBrush(colour(theme.PANEL_RAISED))
        painter.setPen(QPen(colour(theme.PANEL_EDGE_DARK), 2))
        painter.drawEllipse(center, radius - 12, radius - 12)
        painter.setPen(QPen(colour(theme.PANEL_EDGE_LIGHT), 1))
        painter.drawEllipse(center, radius - 16, radius - 16)
        angle = math.radians(start + sweep * fraction)
        indicator_end = QPointF(center.x() + math.cos(angle) * (radius - 27), center.y() - math.sin(angle) * (radius - 27))
        painter.setPen(QPen(colour(theme.AMBER_GLOW if self.selected else theme.TEXT), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(center, indicator_end)

    def _formatted_value(self) -> str:
        if self.unit == "dB":
            return f"{self.value:+.1f} dB"
        if self.unit == "%":
            return f"{self.value:.0f}%"
        return f"{self.value:.0f}{self.unit}"


class LedMeter(QWidget):
    """Segmented output meter with peak marker and danger-zone colours."""

    def __init__(self, segments: int = 22, parent: QWidget | None = None):
        super().__init__(parent)
        self.segments, self.level, self.peak = segments, 0.0, 0.0
        self.setMinimumSize(55, 210)

    def set_levels(self, level: float, peak: float | None = None) -> None:
        self.level = max(0.0, min(1.0, level))
        self.peak = max(self.level, min(1.0, peak if peak is not None else self.peak))
        self.update()

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(colour(theme.TEXT_MUTED))
        painter.setFont(QFont(theme.FONT_LABEL, 7, QFont.Weight.Bold))
        painter.drawText(QRectF(0, 0, self.width(), 15), Qt.AlignmentFlag.AlignCenter, "OUTPUT")
        top, bottom = 25, self.height() - 6
        gap = 3
        segment_h = (bottom - top - gap * (self.segments - 1)) / self.segments
        lit_count = round(self.level * self.segments)
        peak_idx = min(self.segments - 1, max(0, round(self.peak * self.segments) - 1))
        for index in range(self.segments):
            y = bottom - (index + 1) * segment_h - index * gap
            active = index < lit_count
            if index >= self.segments - 3:
                active_colour, idle_colour = theme.RED, theme.RED_DIM
            elif index >= self.segments - 8:
                active_colour, idle_colour = theme.AMBER, theme.AMBER_DIM
            else:
                active_colour, idle_colour = theme.GREEN, theme.GREEN_DIM
            painter.setBrush(colour(active_colour if active else idle_colour))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(QRectF(14, y, self.width() - 28, segment_h), 2, 2)
            if index == peak_idx:
                painter.setPen(QPen(colour(theme.TEXT), 1))
                painter.drawRoundedRect(QRectF(12, y - 1, self.width() - 24, segment_h + 2), 2, 2)


class MomentaryButton(QPushButton):
    """Hardware-like illuminated button with a latched visual active state."""

    def __init__(self, label: str, accent: str = theme.AMBER, parent: QWidget | None = None):
        super().__init__(label, parent)
        self.accent, self.active = accent, False
        self.setMinimumHeight(38)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Display prototype only; controller action wiring follows state integration.")
        self._refresh_style()

    def set_active(self, active: bool) -> None:
        self.active = active
        self._refresh_style()

    def _refresh_style(self) -> None:
        bg = self.accent if self.active else theme.PANEL_INSET
        fg = theme.FACEPLATE if self.active else theme.TEXT_MUTED
        self.setStyleSheet(f"""
            QPushButton {{ background: {bg}; color: {fg}; border: 1px solid {theme.PANEL_EDGE_LIGHT};
                           font-size: 9px; font-weight: bold; letter-spacing: 1px; }}
            QPushButton:pressed {{ background: {self.accent}; color: {theme.FACEPLATE}; }}
        """)


class StatusLed(QLabel):
    """Small state badge for connection and mode feedback."""

    def __init__(self, text: str, online: bool = False, parent: QWidget | None = None):
        super().__init__(parent)
        self.text = text
        self.set_state(online)

    def set_state(self, online: bool, warning: bool = False) -> None:
        colour_value = theme.RED if warning else (theme.GREEN if online else theme.TEXT_FAINT)
        icon = "●" if online or warning else "○"
        self.setText(f"{icon} {self.text.upper()}")
        self.setStyleSheet(f"color: {colour_value}; font-size: 8px; font-weight: bold;")
