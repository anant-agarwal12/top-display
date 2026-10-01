"""Visual design tokens and small UI helpers for the overlay, in one place so
the look can be tuned without touching the window logic.

Direction (from the ui-ux-pro-max design system for a dark audio product):
minimal and high-contrast, a near-black panel with a cool tint, slate for
secondary text, green kept as the product accent and a blue accent reserved for
"unlocked" (editing) chrome so the mode is obvious at a glance.
"""
import ctypes
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap

# ---------- colour tokens ----------
PANEL_RGB = (13, 13, 24)            # window background (alpha comes from the opacity slider)
TEXT = "#F8FAFC"                    # primary text / current lyric line
TEXT_MUTED = "#94A3B8"              # secondary text (artist, hints), 6.9:1 on the panel
ACCENT_UNLOCKED = "#60A5FA"         # border, chip and slider fill while unlocked
DESTRUCTIVE = "#EF4444"             # close button hover

# ---------- type ----------
# System fonts only: nothing to bundle, and Segoe UI's fallback chain covers
# Devanagari and other scripts the song list contains.
_FAMILIES = ["Segoe UI Variable Text", "Segoe UI"]
LINE_SIZE = 15
ACTIVE_LINE_SIZE = 20


def make_font(point_size: float, weight: QFont.Weight = QFont.Normal) -> QFont:
    font = QFont()
    font.setFamilies(_FAMILIES)
    font.setPointSizeF(point_size)
    font.setWeight(weight)
    return font


def line_font(active: bool) -> QFont:
    return make_font(ACTIVE_LINE_SIZE, QFont.DemiBold) if active else make_font(LINE_SIZE)


# ---------- lyric emphasis ----------
_NEAR_ALPHA = 0.72      # the line right next to the current one
_ALPHA_STEP = 0.06      # how fast lines fade with distance
_ALPHA_FLOOR = 0.40     # far lines stay readable (about 3.9:1), never vanish
FADE_RANGE = 8          # lines further than this from the active one are already at the floor


def line_alpha(distance: int) -> float:
    if distance <= 0:
        return 1.0
    return max(_ALPHA_FLOOR, _NEAR_ALPHA - _ALPHA_STEP * (distance - 1))


def text_color(alpha: float) -> QColor:
    color = QColor(TEXT)
    color.setAlphaF(max(0.0, min(1.0, alpha)))
    return color


# ---------- motion ----------
def animations_enabled() -> bool:
    """Honours Windows' "Animation effects" setting (the desktop equivalent of
    prefers-reduced-motion). Falls back to enabled if it can't be read."""
    flag = ctypes.c_int(1)
    try:
        ok = ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(flag), 0)  # SPI_GETCLIENTAREAANIMATION
    except Exception:
        return True
    return bool(flag.value) if ok else True


def motion_ms(duration_ms: int) -> int:
    return duration_ms if animations_enabled() else 0


# ---------- icons (drawn, not font glyphs, so they stay crisp and centred) ----------
def make_icon(kind: str, normal: str = TEXT_MUTED, active: str = TEXT) -> QIcon:
    icon = QIcon()
    for mode, color in ((QIcon.Normal, normal), (QIcon.Active, active)):
        icon.addPixmap(_draw_icon(kind, color), mode)
    return icon


def _draw_icon(kind: str, color: str) -> QPixmap:
    scale = 2                       # drawn at 2x so it stays sharp on high-DPI screens
    size = 14
    pixmap = QPixmap(size * scale, size * scale)
    pixmap.setDevicePixelRatio(scale)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor(color), 1.6)
    pen.setCapStyle(Qt.RoundCap)
    painter.setPen(pen)
    if kind == "minimize":
        painter.drawLine(3, 10, 11, 10)
    elif kind == "close":
        painter.drawLine(3, 3, 11, 11)
        painter.drawLine(11, 3, 3, 11)
    painter.end()
    return pixmap


# ---------- stylesheets ----------
def button_qss(hover_bg: str = "rgba(255,255,255,40)") -> str:
    return (
        "QPushButton { background: transparent; border: 1px solid transparent; border-radius: 6px; }"
        f"QPushButton:hover {{ background: {hover_bg}; }}"
        "QPushButton:pressed { background: rgba(255,255,255,24); }"
        f"QPushButton:focus {{ border: 1px solid {ACCENT_UNLOCKED}; }}"
    )


CLOSE_BUTTON_QSS = button_qss("rgba(239,68,68,200)")

CHIP_QSS = (
    f"QLabel {{ color: {ACCENT_UNLOCKED}; background: rgba(96,165,250,36);"
    f" border: 1px solid rgba(96,165,250,110); border-radius: 8px;"
    f" padding: 1px 7px; font-size: 8pt; font-weight: 600; letter-spacing: 1px; }}"
)

SLIDER_QSS = (
    "QSlider::groove:horizontal { height: 4px; background: rgba(255,255,255,45); border-radius: 2px; }"
    f"QSlider::sub-page:horizontal {{ background: {ACCENT_UNLOCKED}; border-radius: 2px; }}"
    f"QSlider::handle:horizontal {{ background: {TEXT}; width: 12px; height: 12px;"
    " margin: -4px 0; border-radius: 6px; border: 1px solid transparent; }"
    "QSlider::handle:horizontal:hover { background: white; }"
    f"QSlider::handle:horizontal:focus {{ border: 2px solid {ACCENT_UNLOCKED}; }}"
)

SCROLLBAR_QSS = (
    "QScrollBar:vertical { background: transparent; width: 8px; margin: 2px; }"
    "QScrollBar::handle:vertical { background: rgba(255,255,255,70); border-radius: 3px; min-height: 24px; }"
    "QScrollBar::handle:vertical:hover { background: rgba(255,255,255,130); }"
    "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
    "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }"
)
