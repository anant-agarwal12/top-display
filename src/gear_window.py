"""The floating settings gear and its attached pane.

One top-level window holds both, so the pane is attached to the gear by
construction: there is a single position, a single drag, and a single hole in
the screen-dim layer. The window is only the size of the gear while the pane is
closed, and grows to include the pane (on whichever side has room) when open.
"""
from typing import Optional

from PySide6.QtCore import Qt, QPoint, QRect, QRectF, QSize, Signal
from PySide6.QtGui import QColor, QFontMetrics, QGuiApplication, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

import theme

GEAR_SIZE = 40
GAP = 6                 # between the gear and the pane it opens
PANE_WIDTH = 264
DRAG_THRESHOLD = 4      # px of movement before a press counts as a drag, not a click
_PANEL = theme.PANEL_RGB


class _GearButton(QWidget):
    """Round glass button. A press that moves less than DRAG_THRESHOLD is a
    click (toggle the pane); anything more drags the whole window."""
    clicked = Signal()
    drag_begin = Signal()
    drag_to = Signal(QPoint)      # global delta from where the press started
    drag_end = Signal()

    def __init__(self, parent):
        super().__init__(parent)
        self.setFixedSize(GEAR_SIZE, GEAR_SIZE)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.TabFocus)
        self.setToolTip("Settings  (drag to move)")
        self.setAccessibleName("Settings")
        self._hover = False
        self._down = False
        self._press_pos: Optional[QPoint] = None
        self._dragging = False

    def enterEvent(self, event):
        self._hover = True
        self.update()

    def leaveEvent(self, event):
        self._hover = False
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._press_pos = event.globalPosition().toPoint()
            self._dragging = False
            self._down = True
            self.drag_begin.emit()
            self.update()

    def mouseMoveEvent(self, event):
        if self._press_pos is None:
            return
        delta = event.globalPosition().toPoint() - self._press_pos
        if not self._dragging and delta.manhattanLength() < DRAG_THRESHOLD:
            return
        self._dragging = True
        self.drag_to.emit(delta)

    def mouseReleaseEvent(self, event):
        if self._press_pos is None:
            return
        dragged = self._dragging
        self._press_pos, self._dragging, self._down = None, False, False
        self.update()
        (self.drag_end if dragged else self.clicked).emit()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter):
            self.clicked.emit()
        else:
            super().keyPressEvent(event)

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.update()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5)
        # Near-opaque tint: this window has no blur behind it, so it must hold
        # up over any wallpaper on its own.
        fill = QColor(*_PANEL, 235 if not self._down else 255)
        painter.setPen(Qt.NoPen)
        painter.setBrush(fill)
        painter.drawEllipse(rect)
        ring = QColor(theme.ACCENT_UNLOCKED) if (self._hover or self.hasFocus()) else QColor(255, 255, 255, 46)
        painter.setPen(QPen(ring, 1.5))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(rect)
        theme.draw_gear(
            painter, rect.center().x(), rect.center().y(), 9.5,
            QColor(theme.TEXT) if self._hover else QColor(theme.TEXT_MUTED),
        )


class _ElidedLabel(QLabel):
    """Single-line label that ends in an ellipsis instead of widening the pane."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._full = ""
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setMinimumWidth(0)

    def set_full_text(self, text: str):
        self._full = text
        self.setToolTip(text)
        self._elide()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._elide()

    def _elide(self):
        self.setText(QFontMetrics(self.font()).elidedText(self._full, Qt.ElideRight, max(0, self.width())))


class _Pane(QFrame):
    quit_requested = Signal()

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("settingsPane")
        self.setFixedWidth(PANE_WIDTH)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(0)

        caption = QLabel("NOW PLAYING")
        caption.setFont(theme.make_font(7.5, theme.QFont.DemiBold))
        caption.setStyleSheet(f"color: {theme.TEXT_MUTED}; letter-spacing: 1.5px;")
        layout.addWidget(caption)
        layout.addSpacing(6)
        self.title = _ElidedLabel()
        self.title.setFont(theme.make_font(11.5, theme.QFont.DemiBold))
        self.title.setStyleSheet(f"color: {theme.TEXT};")
        layout.addWidget(self.title)
        self.artist = _ElidedLabel()
        self.artist.setFont(theme.make_font(9.5))
        self.artist.setStyleSheet(f"color: {theme.TEXT_MUTED};")
        layout.addWidget(self.artist)
        self.set_now_playing(None, None)

        layout.addSpacing(12)
        layout.addWidget(self._divider())
        layout.addSpacing(12)

        layout.addLayout(self._shortcut("Ctrl+Alt+P", "Start / stop"))
        layout.addSpacing(8)
        layout.addLayout(self._shortcut("Ctrl+Alt+L", "Lock / unlock"))

        layout.addSpacing(14)
        quit_btn = QPushButton("Quit Top Display")
        quit_btn.setCursor(Qt.PointingHandCursor)
        quit_btn.setFont(theme.make_font(9.5, theme.QFont.DemiBold))
        quit_btn.setStyleSheet(
            f"QPushButton {{ color: {theme.TEXT}; background: rgba(255,255,255,16);"
            " border: 1px solid rgba(255,255,255,34); border-radius: 8px; padding: 7px; }"
            f"QPushButton:hover {{ background: rgba(239,68,68,210); border-color: transparent; }}"
            f"QPushButton:focus {{ border: 1px solid {theme.ACCENT_UNLOCKED}; }}"
        )
        quit_btn.clicked.connect(self.quit_requested)
        layout.addWidget(quit_btn)

    @staticmethod
    def _divider() -> QFrame:
        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet("background: rgba(255,255,255,26);")
        return line

    @staticmethod
    def _shortcut(keys: str, action: str) -> QHBoxLayout:
        row = QHBoxLayout()
        chip = QLabel(keys)
        chip.setFont(theme.make_font(8.5, theme.QFont.DemiBold))
        chip.setStyleSheet(
            f"color: {theme.TEXT}; background: rgba(255,255,255,20);"
            " border: 1px solid rgba(255,255,255,36); border-radius: 5px; padding: 2px 7px;"
        )
        label = QLabel(action)
        label.setFont(theme.make_font(9.5))
        label.setStyleSheet(f"color: {theme.TEXT_MUTED};")
        row.addWidget(chip)
        row.addSpacing(10)
        row.addWidget(label, stretch=1)
        return row

    def set_now_playing(self, title: Optional[str], artist: Optional[str]):
        if title is None:
            self.title.set_full_text("Nothing playing")
            self.artist.set_full_text("Start a song in Spotify")
        else:
            self.title.set_full_text(title)
            self.artist.set_full_text(artist or "")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(rect, 14, 14)
        painter.fillPath(path, QColor(*_PANEL, 240))
        painter.setPen(QPen(QColor(255, 255, 255, 40), 1))
        painter.drawPath(path)


class GearWindow(QWidget):
    geometry_changed = Signal()          # moved or resized: the dim-layer hole must follow
    position_saved = Signal(int, int)    # gear's screen position, after a drag ends
    quit_requested = Signal()

    def __init__(self, gear_pos: QPoint):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)

        self._gear_pos = QPoint(gear_pos)       # top-left of the gear, in screen coordinates
        self._drag_start_pos = QPoint(gear_pos)
        self._open = False

        self.gear = _GearButton(self)
        self.pane = _Pane(self)
        self.pane.hide()
        self.gear.clicked.connect(self.toggle_pane)
        self.gear.drag_begin.connect(self._on_drag_begin)
        self.gear.drag_to.connect(self._on_drag_to)
        self.gear.drag_end.connect(self._on_drag_end)
        self.pane.quit_requested.connect(self.quit_requested)
        self._relayout()

    # ---------- public ----------
    @property
    def gear_pos(self) -> QPoint:
        return QPoint(self._gear_pos)

    def set_gear_pos(self, pos: QPoint):
        self._gear_pos = QPoint(pos)
        self._relayout()

    def set_now_playing(self, title: Optional[str], artist: Optional[str]):
        self.pane.set_now_playing(title, artist)

    def show_for_edit(self):
        self._open = False
        self.pane.hide()
        self._relayout()
        self.show()
        self.raise_()

    def hide_for_lock(self):
        self._open = False
        self.pane.hide()
        self.hide()

    def toggle_pane(self):
        self._open = not self._open
        self.pane.setVisible(self._open)
        self._relayout()
        self.geometry_changed.emit()

    # ---------- placement ----------
    def _screen_rect(self) -> QRect:
        centre = self._gear_pos + QPoint(GEAR_SIZE // 2, GEAR_SIZE // 2)
        screen = QGuiApplication.screenAt(centre) or QGuiApplication.primaryScreen()
        return screen.availableGeometry()

    def _relayout(self):
        if not self._open:
            self.setGeometry(QRect(self._gear_pos, QSize(GEAR_SIZE, GEAR_SIZE)))
            self.gear.move(0, 0)
            return
        avail = self._screen_rect()
        pane_h = self.pane.sizeHint().height()
        # Pane goes on the right of the gear unless it would run off the screen.
        room_right = avail.right() + 1 - (self._gear_pos.x() + GEAR_SIZE + GAP)
        on_right = room_right >= PANE_WIDTH
        # Pane top lines up with the gear top; slide it up if it would hang off the bottom.
        top = max(avail.top(), min(self._gear_pos.y(), avail.bottom() + 1 - pane_h))
        gear_y = self._gear_pos.y() - top
        total_w = GEAR_SIZE + GAP + PANE_WIDTH
        height = max(pane_h, gear_y + GEAR_SIZE)
        if on_right:
            left, gear_x, pane_x = self._gear_pos.x(), 0, GEAR_SIZE + GAP
        else:
            left, gear_x, pane_x = self._gear_pos.x() - (PANE_WIDTH + GAP), PANE_WIDTH + GAP, 0
        self.setGeometry(left, top, total_w, height)
        self.gear.move(gear_x, gear_y)
        self.pane.setGeometry(QRect(QPoint(pane_x, 0), QSize(PANE_WIDTH, pane_h)))

    def clamp_to_screens(self):
        """Keeps the gear on a real screen (a saved position on an unplugged monitor)."""
        virtual = QGuiApplication.primaryScreen().virtualGeometry()
        on_screen = any(
            s.availableGeometry().intersects(QRect(self._gear_pos, QSize(GEAR_SIZE, GEAR_SIZE)))
            for s in QGuiApplication.screens()
        )
        if not on_screen:
            avail = QGuiApplication.primaryScreen().availableGeometry()
            self._gear_pos = QPoint(avail.left() + 24, avail.top() + int(avail.height() * 0.30))
        else:
            self._gear_pos = QPoint(
                max(virtual.left(), min(self._gear_pos.x(), virtual.right() + 1 - GEAR_SIZE)),
                max(virtual.top(), min(self._gear_pos.y(), virtual.bottom() + 1 - GEAR_SIZE)),
            )
        self._relayout()

    # ---------- dragging ----------
    def _on_drag_begin(self):
        self._drag_start_pos = QPoint(self._gear_pos)

    def _on_drag_to(self, delta: QPoint):
        self._gear_pos = self._drag_start_pos + delta
        virtual = QGuiApplication.primaryScreen().virtualGeometry()
        self._gear_pos = QPoint(
            max(virtual.left(), min(self._gear_pos.x(), virtual.right() + 1 - GEAR_SIZE)),
            max(virtual.top(), min(self._gear_pos.y(), virtual.bottom() + 1 - GEAR_SIZE)),
        )
        self._relayout()
        self.geometry_changed.emit()

    def _on_drag_end(self):
        self._relayout()   # re-picks the pane's side for wherever the gear ended up
        self.geometry_changed.emit()
        self.position_saved.emit(self._gear_pos.x(), self._gear_pos.y())

    # Windows hit-tests layered windows per pixel (alpha 0 = click-through). The
    # gaps in this window must still catch clicks, or they would fall through the
    # dim layer's hole to the app underneath.
    def paintEvent(self, event):
        QPainter(self).fillRect(self.rect(), QColor(0, 0, 0, 1))
