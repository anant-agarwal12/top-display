"""Visual design tokens and small UI helpers for the overlay, in one place so
the look can be tuned without touching the window logic.

Direction (from the ui-ux-pro-max design system for a dark audio product):
minimal and high-contrast, a near-black panel with a cool tint, slate for
secondary text, green kept as the product accent and a blue accent reserved for
"unlocked" (editing) chrome so the mode is obvious at a glance.
"""
from typing import Optional

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QTransform

# ---------- colour tokens ----------
PANEL_RGB = (13, 13, 24)            # window background (alpha comes from the opacity slider)
TEXT = "#F8FAFC"                    # primary text / current lyric line
TEXT_MUTED = "#94A3B8"              # secondary text (artist, hints), 6.9:1 on the panel
ACCENT_UNLOCKED = "#60A5FA"         # border and slider fill while unlocked
ACCENT_SING = "#22C55E"             # karaoke sweep: the "sung" colour

# ---------- type ----------
# System fonts only: nothing to bundle, and Segoe UI's fallback chain covers
# Devanagari and other scripts the song list contains.
_FAMILIES = ["Segoe UI Variable Text", "Segoe UI"]
LINE_SIZE = 16          # resting size of every lyric line; the current line is *painted* larger


def make_font(point_size: float, weight: QFont.Weight = QFont.Normal) -> QFont:
    font = QFont()
    font.setFamilies(_FAMILIES)
    font.setPointSizeF(point_size)
    font.setWeight(weight)
    return font


def lyric_font() -> QFont:
    return make_font(LINE_SIZE, QFont.Medium)


def text_color(alpha: float) -> QColor:
    color = QColor(TEXT)
    color.setAlphaF(max(0.0, min(1.0, alpha)))
    return color


def draw_gear(painter: QPainter, cx: float, cy: float, radius: float, color: QColor, teeth: int = 8):
    """A cog: round body, `teeth` rounded teeth, and a hole in the middle."""
    body = QPainterPath()
    body.addEllipse(QRectF(cx - radius * 0.68, cy - radius * 0.68, radius * 1.36, radius * 1.36))
    tooth_w = radius * 0.46
    for i in range(teeth):
        tooth = QPainterPath()
        tooth.addRoundedRect(QRectF(-tooth_w / 2, -radius, tooth_w, radius * 0.62), tooth_w * 0.25, tooth_w * 0.25)
        rotate = QTransform().translate(cx, cy).rotate(360.0 * i / teeth)
        body = body.united(rotate.map(tooth))
    hole = QPainterPath()
    hole.addEllipse(QRectF(cx - radius * 0.3, cy - radius * 0.3, radius * 0.6, radius * 0.6))
    painter.setPen(Qt.NoPen)
    painter.setBrush(color)
    painter.drawPath(body.subtracted(hole))


# ---------- stylesheets ----------
SLIDER_QSS = (
    "QSlider::groove:horizontal { height: 4px; background: rgba(255,255,255,45); border-radius: 2px; }"
    f"QSlider::sub-page:horizontal {{ background: {ACCENT_UNLOCKED}; border-radius: 2px; }}"
    f"QSlider::handle:horizontal {{ background: {TEXT}; width: 12px; height: 12px;"
    " margin: -4px 0; border-radius: 6px; border: 1px solid transparent; }"
    "QSlider::handle:horizontal:hover { background: white; }"
    f"QSlider::handle:horizontal:focus {{ border: 2px solid {ACCENT_UNLOCKED}; }}"
)
