"""The floating settings gear and its attached pane.

One top-level window holds both, so the pane is attached to the gear by
construction: there is a single position, a single drag, and a single hole in
the screen-dim layer. The window is only the size of the gear while the pane is
closed, and grows to include the pane (on whichever side has room) when open.

The pane is organised in tabs (Lyrics, Shortcuts, General) under a header that always
shows the current song, with Quit always at the bottom -- so more settings can be added
later as new tabs or new rows without the pane growing taller or turning into one long
list. It does not apply anything itself: it reports changes through signals and a
validator callback supplied by the overlay, which owns the real state.
"""
from typing import Callable, Optional

from PySide6.QtCore import QEvent, Qt, QPoint, QRect, QRectF, QSize, QTimer, Signal
from PySide6.QtGui import QColor, QFontMetrics, QGuiApplication, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QButtonGroup, QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy,
    QStackedWidget, QVBoxLayout, QWidget,
)

import hotkey_spec
import lyric_styles
import theme
from version import get_version

GEAR_SIZE = 40
GAP = 6                 # between the gear and the pane it opens
PANE_WIDTH = 300
DRAG_THRESHOLD = 4      # px of movement before a press counts as a drag, not a click
_PANEL = theme.PANEL_RGB
_ERROR_COLOR = "#F87171"

_PANE_QSS = f"""
QComboBox {{ color: {theme.TEXT}; background: rgba(255,255,255,18);
    border: 1px solid rgba(255,255,255,36); border-radius: 7px;
    padding: 3px 22px 3px 8px; min-height: 20px; }}
QComboBox:hover {{ background: rgba(255,255,255,30); }}
QComboBox:focus {{ border: 1px solid {theme.ACCENT_UNLOCKED}; }}
QComboBox::drop-down {{ border: none; width: 20px; }}
QComboBox QAbstractItemView {{ background: #14141f; color: {theme.TEXT};
    border: 1px solid rgba(255,255,255,40); outline: 0; padding: 3px;
    selection-background-color: rgba(96,165,250,90); selection-color: {theme.TEXT}; }}
QPushButton#linkButton {{ color: {theme.TEXT_MUTED}; background: transparent; border: none;
    padding: 2px 4px; text-align: right; }}
QPushButton#linkButton:hover {{ color: {theme.TEXT}; }}
QPushButton#linkButton:focus {{ color: {theme.TEXT}; border: 1px solid {theme.ACCENT_UNLOCKED}; border-radius: 4px; }}
QPushButton#tabButton {{ color: {theme.TEXT_MUTED}; background: transparent;
    border: 1px solid transparent; border-radius: 7px; padding: 4px 0; }}
QPushButton#tabButton:hover {{ color: {theme.TEXT}; }}
QPushButton#tabButton:checked {{ color: {theme.TEXT}; background: rgba(255,255,255,30); }}
QPushButton#tabButton:focus {{ border: 1px solid {theme.ACCENT_UNLOCKED}; }}
QPushButton#actionButton {{ color: {theme.TEXT}; background: rgba(255,255,255,16);
    border: 1px solid rgba(255,255,255,34); border-radius: 8px; padding: 6px 10px; text-align: left; }}
QPushButton#actionButton:hover {{ background: rgba(255,255,255,30); }}
QPushButton#actionButton:focus {{ border: 1px solid {theme.ACCENT_UNLOCKED}; }}
"""


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


class _Combo(QComboBox):
    """A dropdown whose popup list reports itself.

    The popup is its own top-level window. While the screen is dimmed, the dim
    layer would otherwise sit on top of it (it is re-pinned topmost every few
    hundred ms) and swallow its clicks, so the overlay is told when it opens
    and closes and keeps it above the dim layer like any other window of ours.
    """
    popup_shown = Signal(QWidget)
    popup_hidden = Signal(QWidget)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.PointingHandCursor)
        self.setMaxVisibleItems(9)

    def showPopup(self):
        super().showPopup()
        self.popup_shown.emit(self.view().window())

    def hidePopup(self):
        self.popup_hidden.emit(self.view().window())
        super().hidePopup()

    def wheelEvent(self, event):
        event.ignore()   # scrolling over the pane must not change a setting by accident

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor(theme.TEXT_MUTED), 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        x, y = self.width() - 13.0, self.height() / 2.0
        painter.drawPolyline([QPoint(int(x) - 3, int(y) - 1), QPoint(int(x), int(y) + 2), QPoint(int(x) + 3, int(y) - 1)])


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


class _HotkeyRow(QWidget):
    """One shortcut: a modifier dropdown and a key dropdown (no key capture --
    a registered shortcut never reaches a capture field, and pressing the
    current start/stop shortcut would stop the app)."""
    edited = Signal(str, str)          # kind, new canonical shortcut
    popup_shown = Signal(QWidget)
    popup_hidden = Signal(QWidget)

    def __init__(self, kind: str, title: str, combo: str, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.committed = combo
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        label = QLabel(title)
        label.setFont(theme.make_font(9.5))
        label.setStyleSheet(f"color: {theme.TEXT};")
        label.setFixedWidth(80)
        row.addWidget(label)
        self.mods = _Combo()
        for mod in hotkey_spec.MODIFIER_SETS:
            self.mods.addItem(mod.replace("+", " + "), mod)
        self.keys = _Combo()
        for key in hotkey_spec.KEYS:
            self.keys.addItem(key, key)
        self.keys.setFixedWidth(66)
        for combo_box, name in ((self.mods, "modifier keys"), (self.keys, "key")):
            combo_box.setAccessibleName(f"{title} shortcut, {name}")
            combo_box.popup_shown.connect(self.popup_shown)
            combo_box.popup_hidden.connect(self.popup_hidden)
            combo_box.activated.connect(self._on_activated)
        row.addWidget(self.mods, stretch=1)
        row.addWidget(self.keys)
        self.set_value(combo)

    def value(self) -> str:
        return hotkey_spec.join(self.mods.currentData(), self.keys.currentData())

    def set_value(self, combo: str):
        parts = hotkey_spec.split(combo) or hotkey_spec.split(hotkey_spec.DEFAULT_TOGGLE)
        for box, data in ((self.mods, parts[0]), (self.keys, parts[1])):
            box.blockSignals(True)
            box.setCurrentIndex(max(0, box.findData(data)))
            box.blockSignals(False)
        self.committed = hotkey_spec.join(*parts)

    def _on_activated(self, _index):
        self.edited.emit(self.kind, self.value())


class _TabBar(QWidget):
    """A segmented control: one button per settings page. Left/Right arrows move between
    tabs when one has keyboard focus."""
    changed = Signal(int)

    def __init__(self, names, parent=None):
        super().__init__(parent)
        self.setFixedHeight(34)
        row = QHBoxLayout(self)
        row.setContentsMargins(3, 3, 3, 3)
        row.setSpacing(2)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self.buttons = []
        self._index = 0
        for i, name in enumerate(names):
            button = QPushButton(name)
            button.setObjectName("tabButton")
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.setFont(theme.make_font(9.5, theme.QFont.DemiBold))
            button.setAccessibleName(f"{name} settings")
            button.clicked.connect(lambda _checked=False, k=i: self.set_current(k))
            button.installEventFilter(self)
            self._group.addButton(button)
            row.addWidget(button, 1)
            self.buttons.append(button)
        self.buttons[0].setChecked(True)

    def current(self) -> int:
        return self._index

    def set_current(self, index: int):
        index = max(0, min(len(self.buttons) - 1, index))
        self.buttons[index].setChecked(True)
        if index != self._index:
            self._index = index
            self.changed.emit(index)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.KeyPress and event.key() in (Qt.Key_Left, Qt.Key_Right) and obj in self.buttons:
            target = self.buttons.index(obj) + (1 if event.key() == Qt.Key_Right else -1)
            if 0 <= target < len(self.buttons):
                self.set_current(target)
                self.buttons[target].setFocus()
            return True
        return super().eventFilter(obj, event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 10, 10)
        painter.fillPath(path, QColor(255, 255, 255, 14))


class _Pane(QFrame):
    animation_changed = Signal(str)
    reset_hotkeys_requested = Signal()
    reset_window_requested = Signal()
    open_folder_requested = Signal()
    popup_shown = Signal(QWidget)
    popup_hidden = Signal(QWidget)
    quit_requested = Signal()

    TAB_NAMES = ("Lyrics", "Shortcuts", "General")

    def __init__(self, parent, animation_key: str, toggle_combo: str, lock_combo: str):
        super().__init__(parent)
        self.setObjectName("settingsPane")
        self.setFixedWidth(PANE_WIDTH)
        self.setStyleSheet(_PANE_QSS)
        self._hotkey_handler: Optional[Callable[[str, str], str]] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(0)

        # ---- always visible: what is playing ----
        layout.addWidget(self._caption("NOW PLAYING"))
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

        # ---- the tabs ----
        self.tabs = _TabBar(self.TAB_NAMES)
        layout.addWidget(self.tabs)
        layout.addSpacing(12)
        self.stack = QStackedWidget()
        self.pages = [self._build_lyrics_page(animation_key),
                      self._build_shortcuts_page(toggle_combo, lock_combo),
                      self._build_general_page()]
        for page in self.pages:
            self.stack.addWidget(page)
        self.fit_pages()
        self.tabs.changed.connect(self.stack.setCurrentIndex)
        layout.addWidget(self.stack)

        # ---- always visible: quit ----
        layout.addSpacing(10)
        layout.addWidget(self._divider())
        layout.addSpacing(12)
        quit_btn = QPushButton("Quit Top Display")
        quit_btn.setCursor(Qt.PointingHandCursor)
        quit_btn.setFont(theme.make_font(9.5, theme.QFont.DemiBold))
        quit_btn.setStyleSheet(
            f"QPushButton {{ color: {theme.TEXT}; background: rgba(255,255,255,16);"
            " border: 1px solid rgba(255,255,255,34); border-radius: 8px; padding: 7px; }"
            "QPushButton:hover { background: rgba(239,68,68,210); border-color: transparent; }"
            f"QPushButton:focus {{ border: 1px solid {theme.ACCENT_UNLOCKED}; }}"
        )
        quit_btn.clicked.connect(self.quit_requested)
        layout.addWidget(quit_btn)

    def fit_pages(self):
        """Every tab gets the same height (the tallest), so switching tabs never moves or
        resizes the pane. Measured after the stylesheet has been applied: before that, the
        pages report smaller sizes than they really need and their content gets clipped.
        A page that outgrows this later should scroll rather than push the pane taller."""
        self.ensurePolished()
        height = max(page.sizeHint().height() for page in self.pages)
        if height != self.stack.height():
            self.stack.setFixedHeight(height)

    # ---------- pages ----------
    @staticmethod
    def _new_page():
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        return page, layout

    def _build_lyrics_page(self, animation_key: str) -> QWidget:
        page, layout = self._new_page()
        layout.addWidget(self._caption("ANIMATION"))
        layout.addSpacing(6)
        self.style_box = _Combo()
        for key, style in lyric_styles.STYLES.items():
            self.style_box.addItem(style["label"], key)
        self.style_box.setAccessibleName("Lyric animation style")
        self.style_box.setCurrentIndex(max(0, self.style_box.findData(lyric_styles.normalize(animation_key))))
        self.style_box.popup_shown.connect(self.popup_shown)
        self.style_box.popup_hidden.connect(self.popup_hidden)
        self.style_box.activated.connect(self._on_style_activated)
        layout.addWidget(self.style_box)
        layout.addSpacing(6)
        self.style_hint = QLabel()
        self.style_hint.setWordWrap(True)
        self.style_hint.setFont(theme.make_font(8.5))
        self.style_hint.setStyleSheet(f"color: {theme.TEXT_MUTED};")
        self.style_hint.setFixedHeight(32)   # two lines, so the page never changes height
        self.style_hint.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        layout.addWidget(self.style_hint)
        self._update_style_hint()
        layout.addStretch(1)
        return page

    def _build_shortcuts_page(self, toggle_combo: str, lock_combo: str) -> QWidget:
        page, layout = self._new_page()
        layout.addWidget(self._caption("KEYBOARD SHORTCUTS"))
        layout.addSpacing(8)
        self.toggle_row = _HotkeyRow("toggle", "Start / stop", toggle_combo)
        self.lock_row = _HotkeyRow("lock", "Lock / unlock", lock_combo)
        for row in (self.toggle_row, self.lock_row):
            row.edited.connect(self._on_hotkey_edited)
            row.popup_shown.connect(self.popup_shown)
            row.popup_hidden.connect(self.popup_hidden)
        layout.addWidget(self.toggle_row)
        layout.addSpacing(8)
        layout.addWidget(self.lock_row)
        layout.addSpacing(6)

        footer = QHBoxLayout()
        self.message = QLabel()
        self.message.setFont(theme.make_font(8.5))
        self.message.setWordWrap(True)
        self.message.setFixedHeight(32)
        self.message.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        footer.addWidget(self.message, stretch=1)
        reset = QPushButton("Reset")
        reset.setObjectName("linkButton")
        reset.setCursor(Qt.PointingHandCursor)
        reset.setFont(theme.make_font(8.5))
        reset.setToolTip("Put both shortcuts back to Ctrl+Alt+P and Ctrl+Alt+L")
        reset.clicked.connect(self.reset_hotkeys_requested)
        footer.addWidget(reset, alignment=Qt.AlignTop)
        layout.addLayout(footer)
        self._message_timer = QTimer(self)
        self._message_timer.setSingleShot(True)
        self._message_timer.timeout.connect(lambda: self.message.setText(""))
        layout.addStretch(1)
        return page

    def _build_general_page(self) -> QWidget:
        page, layout = self._new_page()
        layout.addWidget(self._caption("WINDOW"))
        layout.addSpacing(6)
        reset_window = QPushButton("Reset window position and size")
        reset_window.setObjectName("actionButton")
        reset_window.setCursor(Qt.PointingHandCursor)
        reset_window.setFont(theme.make_font(9.5))
        reset_window.clicked.connect(self.reset_window_requested)
        layout.addWidget(reset_window)
        layout.addSpacing(14)
        layout.addWidget(self._caption("FILES"))
        layout.addSpacing(6)
        open_folder = QPushButton("Open settings folder")
        open_folder.setObjectName("actionButton")
        open_folder.setCursor(Qt.PointingHandCursor)
        open_folder.setFont(theme.make_font(9.5))
        open_folder.setToolTip("Settings and the error log live here")
        open_folder.clicked.connect(self.open_folder_requested)
        layout.addWidget(open_folder)
        layout.addStretch(1)
        layout.addSpacing(8)
        self.version_label = QLabel(f"Top Display {get_version()}  \u00b7  GPL-3.0")
        self.version_label.setFont(theme.make_font(8.5))
        self.version_label.setStyleSheet(f"color: {theme.TEXT_MUTED};")
        layout.addWidget(self.version_label)
        return page

    # ---------- small builders ----------
    @staticmethod
    def _caption(text: str) -> QLabel:
        label = QLabel(text)
        label.setFont(theme.make_font(7.5, theme.QFont.DemiBold))
        label.setStyleSheet(f"color: {theme.TEXT_MUTED}; letter-spacing: 1.5px;")
        return label

    @staticmethod
    def _divider() -> QFrame:
        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet("background: rgba(255,255,255,26);")
        return line

    # ---------- state ----------
    def set_tab(self, index: int):
        self.tabs.set_current(index)
        self.stack.setCurrentIndex(self.tabs.current())

    def set_now_playing(self, title: Optional[str], artist: Optional[str]):
        if title is None:
            self.title.set_full_text("Nothing playing")
            self.artist.set_full_text("Start a song in Spotify")
        else:
            self.title.set_full_text(title)
            self.artist.set_full_text(artist or "")

    def set_hotkey_handler(self, handler: Callable[[str, str], str]):
        """handler(kind, combo) -> "" if applied, else a short reason it was refused."""
        self._hotkey_handler = handler

    def set_hotkeys(self, toggle: str, lock: str):
        self.toggle_row.set_value(toggle)
        self.lock_row.set_value(lock)

    def show_message(self, text: str, error: bool = True):
        # Shortcut messages belong on the Shortcuts tab; make sure the user can see them.
        self.set_tab(1)
        color = _ERROR_COLOR if error else theme.TEXT_MUTED
        self.message.setStyleSheet(f"color: {color};")
        self.message.setText(text)
        self._message_timer.start(7000)

    def _update_style_hint(self):
        key = self.style_box.currentData()
        self.style_hint.setText(lyric_styles.get(key)["hint"])

    def _on_style_activated(self, _index):
        self._update_style_hint()
        self.animation_changed.emit(self.style_box.currentData())

    def _on_hotkey_edited(self, kind: str, combo: str):
        row = self.toggle_row if kind == "toggle" else self.lock_row
        error = self._hotkey_handler(kind, combo) if self._hotkey_handler else ""
        if error:
            row.set_value(row.committed)       # put the dropdowns back
            self.show_message(error)
        else:
            row.committed = combo
            self.show_message("Saved." if kind == "lock" else "Saved. Applies in a moment.", error=False)

    # A click on the panel's empty space must not fall through to the overlay.
    def mousePressEvent(self, event):
        event.accept()

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
    animation_changed = Signal(str)
    reset_hotkeys_requested = Signal()
    reset_window_requested = Signal()
    open_folder_requested = Signal()
    popup_opened = Signal(QWidget)       # a dropdown list opened (it needs a hole in the dim layer)
    popup_closed = Signal(QWidget)
    quit_requested = Signal()

    def __init__(self, gear_pos: QPoint, animation_key: str, toggle_combo: str, lock_combo: str):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)

        self._gear_pos = QPoint(gear_pos)       # top-left of the gear, in screen coordinates
        self._drag_start_pos = QPoint(gear_pos)
        self._open = False

        self.gear = _GearButton(self)
        self.pane = _Pane(self, animation_key, toggle_combo, lock_combo)
        self.pane.hide()
        self.gear.clicked.connect(self.toggle_pane)
        self.gear.drag_begin.connect(self._on_drag_begin)
        self.gear.drag_to.connect(self._on_drag_to)
        self.gear.drag_end.connect(self._on_drag_end)
        self.pane.animation_changed.connect(self.animation_changed)
        self.pane.reset_hotkeys_requested.connect(self.reset_hotkeys_requested)
        self.pane.reset_window_requested.connect(self.reset_window_requested)
        self.pane.open_folder_requested.connect(self.open_folder_requested)
        self.pane.popup_shown.connect(self.popup_opened)
        self.pane.popup_hidden.connect(self.popup_closed)
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

    def set_hotkey_handler(self, handler: Callable[[str, str], str]):
        self.pane.set_hotkey_handler(handler)

    def set_hotkeys(self, toggle: str, lock: str):
        self.pane.set_hotkeys(toggle, lock)

    def show_message(self, text: str, error: bool = True):
        self.pane.show_message(text, error)

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

    def _pane_height(self) -> int:
        self.pane.fit_pages()
        layout = self.pane.layout()
        return layout.totalHeightForWidth(PANE_WIDTH) if layout.hasHeightForWidth() else self.pane.sizeHint().height()

    def _relayout(self):
        if not self._open:
            self.setGeometry(QRect(self._gear_pos, QSize(GEAR_SIZE, GEAR_SIZE)))
            self.gear.move(0, 0)
            return
        avail = self._screen_rect()
        pane_h = self._pane_height()
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
