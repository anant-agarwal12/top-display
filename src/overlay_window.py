"""The transparent, always-on-top, scrollable lyrics overlay window."""
import bisect
import ctypes
import html
import time
from typing import List, Optional, Tuple

from PySide6.QtCore import (
    Qt, QThread, Signal, QTimer, QPropertyAnimation, QVariantAnimation, QEasingCurve,
    QPoint, QRect, QEvent,
)
from PySide6.QtGui import (
    QColor, QPainter, QPainterPath, QFont, QFontMetrics, QPen, QGuiApplication, QRegion, QPalette,
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QSlider,
    QPushButton, QSizeGrip, QSizePolicy,
)

from media_session import fetch_now_playing, NowPlaying
from lyrics_fetcher import fetch_lyrics
import settings as settings_store
import theme


POLL_INTERVAL_SEC = 1.0
TICK_MS = 33
AUTO_FOLLOW_PAUSE_SEC = 4.0
# Backoff between retries when the lyrics server is unreachable; the last
# value repeats until it recovers or the track changes.
_LYRICS_RETRY_DELAYS_SEC = (3, 8, 20, 45)

_HWND_TOPMOST = -1
_SWP_NOMOVE = 0x0002
_SWP_NOSIZE = 0x0001
_SWP_NOACTIVATE = 0x0010


def _pin_topmost(widget: QWidget):
    """Qt's WindowStaysOnTopHint alone doesn't guarantee a window stays above
    every other app at the OS level -- z-order among "always on top" windows
    is otherwise just "whoever was raised most recently". This pins a window
    into Windows' real topmost band directly, which is what actually decides
    which window receives a click or scroll at a given screen point."""
    hwnd = int(widget.winId())
    ctypes.windll.user32.SetWindowPos(
        hwnd, _HWND_TOPMOST, 0, 0, 0, 0,
        _SWP_NOMOVE | _SWP_NOSIZE | _SWP_NOACTIVATE,
    )


class MediaPollWorker(QThread):
    now_playing = Signal(object)

    def __init__(self):
        super().__init__()
        self._running = True

    def run(self):
        while self._running:
            snapshot = fetch_now_playing()
            self.now_playing.emit(snapshot)
            self.msleep(int(POLL_INTERVAL_SEC * 1000))

    def stop(self):
        self._running = False


class LyricsFetchWorker(QThread):
    lyrics_ready = Signal(str, list, str, str)  # track_key, synced_lines, plain_text, state

    def __init__(self, artist, title, album, duration_sec, track_key):
        super().__init__()
        self.artist = artist
        self.title = title
        self.album = album
        self.duration_sec = duration_sec
        self.track_key = track_key

    def run(self):
        synced, plain, state = fetch_lyrics(
            self.artist, self.title, self.album, self.duration_sec, self.track_key
        )
        synced = [(float(t), str(txt)) for t, txt in synced]
        self.lyrics_ready.emit(self.track_key, synced, plain, state)


class _DimPane(QWidget):
    """A single monitor's dim layer. Paints manually -- a plain QWidget does
    not render a QSS background-color without WA_StyledBackground, which was
    silently making the dim invisible."""

    def __init__(self, alpha: int):
        super().__init__()
        self._alpha = alpha
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
            | Qt.Tool | Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, self._alpha))


class ScreenDimmer:
    """Dims every monitor (like the Windows Snip & Sketch capture screen)
    while the overlay is unlocked for repositioning/resizing. Since it is a
    real opaque-to-input window (not click-through), clicks on the dimmed
    background never reach the desktop underneath -- only the holes cut into
    its mask are interactive. A hole is cut for every rect in `exclude_rects`,
    so any window this project registers as "interactive" (see
    LyricsOverlay.register_interactive_window) stays clickable through the
    dim layer without this class needing to know about it."""

    def __init__(self, alpha: int = 130):
        self.alpha = alpha
        self._entries = []

    def show_all(self, exclude_rects: List[QRect]):
        self.hide_all()
        for screen in QGuiApplication.screens():
            screen_geo = screen.geometry()
            dim = _DimPane(self.alpha)
            dim.setGeometry(screen_geo)
            self._entries.append({"widget": dim, "screen_geo": screen_geo})
        self.update_mask(exclude_rects)
        for entry in self._entries:
            entry["widget"].show()
            _pin_topmost(entry["widget"])

    def update_mask(self, exclude_rects: List[QRect]):
        for entry in self._entries:
            screen_geo = entry["screen_geo"]
            region = QRegion(0, 0, screen_geo.width(), screen_geo.height())
            for rect in exclude_rects:
                local_exclude = rect.translated(-screen_geo.topLeft())
                region = region.subtracted(QRegion(local_exclude))
            entry["widget"].setMask(region)

    def hide_all(self):
        for entry in self._entries:
            entry["widget"].close()
            entry["widget"].deleteLater()
        self._entries = []

    def pin_all(self):
        for entry in self._entries:
            _pin_topmost(entry["widget"])


class LyricsOverlay(QWidget):
    def __init__(self):
        super().__init__()
        self.cfg = settings_store.load_settings()

        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setMouseTracking(True)

        self.resize(self.cfg["window_w"], self.cfg["window_h"])
        self.move(self.cfg["window_x"], self.cfg["window_y"])

        self.bg_opacity = self.cfg["bg_opacity"]
        self.edit_mode = False
        self._resize_margin = 8
        self._drag_state: Optional[dict] = None
        self._dimmer = ScreenDimmer()
        self._min_size = (160, 120)

        # Every top-level widget this project owns and wants clickable while
        # the screen is dimmed goes here. Any future window/button just calls
        # register_interactive_window(widget) -- it does not need to touch
        # ScreenDimmer or know the dim layer exists at all.
        self._interactive_windows: List[QWidget] = [self]

        # A one-time SetWindowPos(HWND_TOPMOST) isn't sticky -- Windows can
        # let some other window reclaim the topmost band shortly afterwards
        # (e.g. around activation events), which is what let background
        # clicks/drags leak through. Re-assert continuously while unlocked.
        self._topmost_timer = QTimer(self)
        self._topmost_timer.setInterval(400)
        self._topmost_timer.timeout.connect(self._reassert_topmost)

        self.current_track_key = None
        self.synced_lines: List[Tuple[float, str]] = []
        self.line_labels: List[QLabel] = []
        self.plain_state = "not_found"
        self.now_playing: Optional[NowPlaying] = None

        self._auto_follow = True
        self._last_manual_scroll_time = 0.0
        self._active_index = -1
        self._last_shown_position: Optional[float] = None
        self._line_alpha: List[float] = []      # current text alpha of each lyric line
        self._styled_index = -1                # which line the styling currently treats as active
        self._line_fade: Optional[QVariantAnimation] = None

        self._build_ui()

        self.poll_worker = MediaPollWorker()
        self.poll_worker.now_playing.connect(self._on_now_playing)
        self.poll_worker.start()

        self._lyrics_workers: set = set()
        self._fetch_args: Optional[tuple] = None
        self._fetch_attempt = 0
        self._showing_fallback = False
        self._retry_timer = QTimer(self)
        self._retry_timer.setSingleShot(True)
        self._retry_timer.timeout.connect(self._start_lyrics_fetch)

        self.tick_timer = QTimer(self)
        self.tick_timer.timeout.connect(self._on_tick)
        self.tick_timer.start(TICK_MS)

    # ---------- UI construction ----------
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 6, 10, 10)
        root.setSpacing(4)

        self.title_bar = QWidget(self)
        self.title_bar.setFixedHeight(32)
        self.title_bar.setMouseTracking(True)
        title_layout = QHBoxLayout(self.title_bar)
        title_layout.setContentsMargins(4, 0, 4, 0)
        title_layout.setSpacing(8)

        # The title bar only exists while unlocked, so this chip is the
        # always-visible "you are in edit mode" cue.
        self.unlocked_chip = QLabel("UNLOCKED")
        self.unlocked_chip.setStyleSheet(theme.CHIP_QSS)
        self.unlocked_chip.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        title_layout.addWidget(self.unlocked_chip)

        self.track_label = QLabel("Waiting for Spotify...")
        self.track_label.setStyleSheet("background: transparent;")
        self.track_label.setFont(theme.make_font(9))
        self.track_label.setTextFormat(Qt.RichText)
        self.track_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        # Ignored so its (potentially long) unwrapped text can't force the
        # whole window to stay wider than the user wants -- it'll just clip.
        self.track_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.track_label.setMinimumWidth(0)
        title_layout.addWidget(self.track_label, stretch=1)

        self.opacity_slider = QSlider(Qt.Horizontal)
        # Shrinks in a narrow window so the song title keeps some room.
        self.opacity_slider.setMinimumWidth(48)
        self.opacity_slider.setMaximumWidth(96)
        self.opacity_slider.setStyleSheet(theme.SLIDER_QSS)
        self.opacity_slider.setToolTip("Background opacity")
        self.opacity_slider.setAccessibleName("Background opacity")
        self.opacity_slider.setRange(0, 100)
        self.opacity_slider.setValue(int(self.bg_opacity * 100))
        self.opacity_slider.valueChanged.connect(self._on_opacity_changed)
        title_layout.addWidget(self.opacity_slider)

        self.hide_btn = QPushButton()
        self.hide_btn.setIcon(theme.make_icon("minimize"))
        self.hide_btn.setFixedSize(24, 24)
        self.hide_btn.setToolTip("Hide the overlay (use the tray icon to bring it back)")
        self.hide_btn.setAccessibleName("Hide overlay")
        self.hide_btn.setCursor(Qt.PointingHandCursor)
        self.hide_btn.clicked.connect(self.hide)
        self._style_btn(self.hide_btn)
        title_layout.addWidget(self.hide_btn)

        self.close_btn = QPushButton()
        self.close_btn.setIcon(theme.make_icon("close"))
        self.close_btn.setFixedSize(24, 24)
        self.close_btn.setToolTip("Quit Top Display")
        self.close_btn.setAccessibleName("Quit Top Display")
        self.close_btn.setCursor(Qt.PointingHandCursor)
        self.close_btn.clicked.connect(self._quit_app)
        self._style_btn(self.close_btn, theme.CLOSE_BUTTON_QSS)
        title_layout.addWidget(self.close_btn)

        root.addWidget(self.title_bar)

        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QScrollArea.NoFrame)
        self.scroll_area.setStyleSheet("background: transparent; border: none;" + theme.SCROLLBAR_QSS)
        self.scroll_area.viewport().setStyleSheet("background: transparent;")
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        # valueChanged fires for ANY change, including Qt clamping the value
        # when the scroll range shifts (title bar show/hide, padding
        # changes) -- that isn't the user scrolling. sliderPressed/sliderMoved
        # only fire from someone actually dragging the handle.
        self.scroll_area.verticalScrollBar().sliderPressed.connect(self._on_manual_scroll)
        self.scroll_area.verticalScrollBar().sliderMoved.connect(lambda _value: self._on_manual_scroll())
        self._programmatic_scroll = False

        self.lyrics_container = QWidget()
        self.lyrics_container.setStyleSheet("background: transparent;")
        self.lyrics_container.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.lyrics_layout = QVBoxLayout(self.lyrics_container)
        self.lyrics_layout.setSpacing(16)
        self.lyrics_layout.setContentsMargins(6, 30, 6, 30)

        self.scroll_area.setWidget(self.lyrics_container)
        root.addWidget(self.scroll_area, stretch=1)

        # Clicks on the title bar and the lyrics viewport target those child
        # widgets directly, not this window -- filter their events so
        # dragging/resizing still works from anywhere on the overlay.
        self.title_bar.installEventFilter(self)
        self.scroll_area.viewport().installEventFilter(self)
        self.track_label.installEventFilter(self)

        self.grip_container = QWidget(self)
        grip_row = QHBoxLayout(self.grip_container)
        grip_row.setContentsMargins(4, 0, 0, 0)
        self.lock_hint = QLabel("Ctrl+Alt+L to lock")
        self.lock_hint.setStyleSheet(f"color: {theme.TEXT_MUTED}; background: transparent;")
        self.lock_hint.setFont(theme.make_font(8))
        self.lock_hint.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        grip_row.addWidget(self.lock_hint)
        grip_row.addStretch(1)
        self.size_grip = QSizeGrip(self.grip_container)
        grip_row.addWidget(self.size_grip)
        root.addWidget(self.grip_container)

        self._set_status_line("Waiting for Spotify...")
        self._apply_edit_mode_visuals()

    def _update_dynamic_padding(self):
        """Top/bottom padding scales with the available viewport height, so
        the amount of previous/next lyric context shown adapts to the
        window's current size instead of assuming a fixed amount of space,
        while always leaving room to center the current line."""
        viewport_h = self.scroll_area.viewport().height()
        pad = max(24, viewport_h // 2)
        margins = self.lyrics_layout.contentsMargins()
        if margins.top() == pad:
            return
        self.lyrics_layout.setContentsMargins(6, pad, 6, pad)
        if 0 <= self._active_index < len(self.line_labels):
            self._scroll_to_line_deferred(self._active_index)

    def _scroll_to_line_deferred(self, idx: int):
        """Scroll-to-center right after a bulk layout change (new lyrics
        rendered, padding/visibility changed) can read a stale scrollbar
        range -- QScrollArea only recomputes it once it processes the
        pending layout request. Deferring to the next event-loop tick lets
        that settle first, so the very first scroll attempt lands correctly
        instead of silently waiting for some later trigger to fix it."""
        QTimer.singleShot(0, lambda idx=idx: self._scroll_to_line(idx))

    def _style_btn(self, btn: QPushButton, qss: Optional[str] = None):
        btn.setStyleSheet(qss or theme.button_qss())

    def _set_status_line(self, text: str, content: bool = False):
        """Shows a message in the lyrics area. `content=True` is for actual
        (plain, unsynced) lyrics, which should read brighter than a status
        message like "Loading lyrics...". """
        self._clear_lines()
        label = QLabel(text)
        label.setAlignment(Qt.AlignCenter)
        color = "rgba(248,250,252,215)" if content else theme.TEXT_MUTED
        label.setStyleSheet(f"color: {color}; background: transparent;")
        label.setFont(theme.make_font(14))
        label.setWordWrap(True)
        label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.lyrics_layout.addWidget(label)
        self.line_labels = []

    def _clear_lines(self):
        while self.lyrics_layout.count():
            item = self.lyrics_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self.line_labels = []

    # ---------- event handlers ----------
    def register_interactive_window(self, widget: QWidget):
        """Call this for any future top-level window/popup this project adds
        so it stays clickable through the dim layer while unlocked."""
        if widget not in self._interactive_windows:
            self._interactive_windows.append(widget)
            if self.edit_mode:
                self._refresh_dim_mask()
                _pin_topmost(widget)

    def unregister_interactive_window(self, widget: QWidget):
        if widget in self._interactive_windows:
            self._interactive_windows.remove(widget)
            if self.edit_mode:
                self._refresh_dim_mask()

    def _exclude_rects(self) -> List[QRect]:
        return [w.geometry() for w in self._interactive_windows if w.isVisible()]

    def _refresh_dim_mask(self):
        self._dimmer.update_mask(self._exclude_rects())

    def toggle_edit_mode(self):
        self.edit_mode = not self.edit_mode
        self._apply_edit_mode_visuals()

    def _apply_edit_mode_visuals(self):
        self.title_bar.setVisible(self.edit_mode)
        self.grip_container.setVisible(self.edit_mode)
        self.scroll_area.setVerticalScrollBarPolicy(
            Qt.ScrollBarAsNeeded if self.edit_mode else Qt.ScrollBarAlwaysOff
        )
        if self.edit_mode:
            self._dimmer.show_all(self._exclude_rects())
            self.raise_()
            self.activateWindow()
            self._reassert_topmost()
            self._topmost_timer.start()
        else:
            self._topmost_timer.stop()
            self._dimmer.hide_all()
            self._drag_state = None
            self.setCursor(Qt.ArrowCursor)
        self._update_track_label()
        self.update()

        # Showing/hiding the title bar and grip changes the scroll area's
        # available height without changing this window's own outer size, so
        # it never fires resizeEvent -- nothing else would re-center the
        # current line after a lock/unlock without this.
        self._update_dynamic_padding()
        if 0 <= self._active_index < len(self.line_labels):
            self._scroll_to_line_deferred(self._active_index)

    def _reassert_topmost(self):
        _pin_topmost(self)
        self._dimmer.pin_all()
        for widget in self._interactive_windows:
            if widget is not self and widget.isVisible():
                _pin_topmost(widget)

    def _update_track_label(self):
        """Song title in white, artist in slate, each trimmed with an ellipsis
        to the room the title bar leaves (the title keeps priority)."""
        muted = f"color:{theme.TEXT_MUTED};"
        if self.now_playing is None:
            self.track_label.setText(f"<span style='{muted}'>Nothing playing on Spotify</span>")
            return
        title, artist = self.now_playing.title, self.now_playing.artist
        room = self.track_label.width()
        if 0 < room < 56:  # too narrow for even a clipped title: show nothing rather than "C..."
            self.track_label.setText("")
            return
        if room <= 0:  # not laid out yet
            self.track_label.setText(
                f"<span style='color:{theme.TEXT};font-weight:600'>{html.escape(title)}</span>"
                f"&nbsp;&nbsp;<span style='{muted}'>{html.escape(artist)}</span>"
            )
            return
        bold = QFont(self.track_label.font())
        bold.setWeight(QFont.DemiBold)
        title_fm, artist_fm = QFontMetrics(bold), QFontMetrics(self.track_label.font())
        gap = 10
        shown_title = title_fm.elidedText(title, Qt.ElideRight, room)
        left = room - title_fm.horizontalAdvance(shown_title) - gap
        shown_artist = artist_fm.elidedText(artist, Qt.ElideRight, left) if left > 24 and artist else ""
        parts = f"<span style='color:{theme.TEXT};font-weight:600'>{html.escape(shown_title)}</span>"
        if shown_artist:
            parts += f"&nbsp;&nbsp;<span style='{muted}'>{html.escape(shown_artist)}</span>"
        self.track_label.setText(parts)

    def _edge_at(self, pos: QPoint):
        margin = self._resize_margin
        rect = self.rect()
        edges = Qt.Edges()
        if pos.x() <= margin:
            edges |= Qt.LeftEdge
        if pos.x() >= rect.width() - margin:
            edges |= Qt.RightEdge
        if pos.y() <= margin:
            edges |= Qt.TopEdge
        if pos.y() >= rect.height() - margin:
            edges |= Qt.BottomEdge
        return edges

    def _cursor_for_edges(self, edges):
        diag1 = (edges & Qt.LeftEdge and edges & Qt.TopEdge) or (edges & Qt.RightEdge and edges & Qt.BottomEdge)
        diag2 = (edges & Qt.RightEdge and edges & Qt.TopEdge) or (edges & Qt.LeftEdge and edges & Qt.BottomEdge)
        if diag1:
            return Qt.SizeFDiagCursor
        if diag2:
            return Qt.SizeBDiagCursor
        if edges & (Qt.LeftEdge | Qt.RightEdge):
            return Qt.SizeHorCursor
        if edges & (Qt.TopEdge | Qt.BottomEdge):
            return Qt.SizeVerCursor
        return Qt.ArrowCursor

    def _effective_min_size(self):
        # Qt's layout enforces its own minimum (title bar controls, etc.) on
        # top of whatever we ask for -- computing our resize math against a
        # smaller number than that caused a mismatch where the window
        # appeared to jump/move once the real floor was hit.
        hint = self.minimumSizeHint()
        return max(self._min_size[0], hint.width()), max(self._min_size[1], hint.height())

    # All move/resize is done manually with tracked mouse deltas rather than
    # the OS-native startSystemMove/startSystemResize, which misbehaved
    # (horizontal moves were dropped) on this frameless translucent window.
    def _begin_interaction(self, event) -> bool:
        if not self.edit_mode or event.button() != Qt.LeftButton:
            return False
        global_pos = event.globalPosition().toPoint()
        local_pos = self.mapFromGlobal(global_pos)
        self._drag_state = {
            "edges": self._edge_at(local_pos),
            "start_global": global_pos,
            "start_geo": QRect(self.geometry()),
        }
        return True

    def _update_interaction(self, event) -> bool:
        if self._drag_state is None:
            if self.edit_mode:
                local_pos = self.mapFromGlobal(event.globalPosition().toPoint())
                edges = self._edge_at(local_pos)
                self.setCursor(self._cursor_for_edges(edges) if edges else Qt.ArrowCursor)
            return False
        if not (event.buttons() & Qt.LeftButton):
            return False

        global_pos = event.globalPosition().toPoint()
        delta = global_pos - self._drag_state["start_global"]
        start_geo = self._drag_state["start_geo"]
        edges = self._drag_state["edges"]
        min_w, min_h = self._effective_min_size()

        if edges:
            geo = QRect(start_geo)
            if edges & Qt.LeftEdge:
                geo.setLeft(min(start_geo.left() + delta.x(), start_geo.right() - min_w))
            if edges & Qt.RightEdge:
                geo.setRight(max(start_geo.right() + delta.x(), start_geo.left() + min_w))
            if edges & Qt.TopEdge:
                geo.setTop(min(start_geo.top() + delta.y(), start_geo.bottom() - min_h))
            if edges & Qt.BottomEdge:
                geo.setBottom(max(start_geo.bottom() + delta.y(), start_geo.top() + min_h))
            self.setGeometry(geo)
        else:
            self.move(start_geo.topLeft() + delta)

        self._refresh_dim_mask()
        return True

    def _end_interaction(self) -> bool:
        had_drag = self._drag_state is not None
        self._drag_state = None
        if had_drag:
            self._save_geometry()
        return had_drag

    def eventFilter(self, obj, event):
        if obj is self.track_label and event.type() == QEvent.Resize:
            self._update_track_label()
            return False
        if obj in (self.title_bar, self.scroll_area.viewport()):
            if event.type() == QEvent.MouseButtonPress:
                if self._begin_interaction(event):
                    return True
            elif event.type() == QEvent.MouseMove:
                if self._update_interaction(event):
                    return True
            elif event.type() == QEvent.MouseButtonRelease:
                if self._end_interaction():
                    return True
            elif event.type() == QEvent.Wheel and obj is self.scroll_area.viewport():
                self._on_manual_scroll()
                # Don't consume it -- let the scroll area handle it normally.
        return super().eventFilter(obj, event)

    def mousePressEvent(self, event):
        self._begin_interaction(event)

    def mouseMoveEvent(self, event):
        self._update_interaction(event)

    def mouseReleaseEvent(self, event):
        self._end_interaction()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.size_grip.raise_()
        self._update_dynamic_padding()

    def moveEvent(self, event):
        super().moveEvent(event)
        # Geometry is persisted once in _end_interaction when a drag/resize
        # actually finishes. Saving here too meant writing settings.json on
        # every single mouse-move tick of a drag (dozens of times/sec) --
        # wasteful, and risky since this project folder lives under OneDrive
        # sync.

    def _save_geometry(self):
        self.cfg["window_x"] = self.x()
        self.cfg["window_y"] = self.y()
        self.cfg["window_w"] = self.width()
        self.cfg["window_h"] = self.height()
        settings_store.save_settings(self.cfg)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(self.rect(), 14, 14)

        if self.edit_mode:
            # Windows hit-tests layered windows per pixel: alpha 0 is
            # click-through. With opacity at 0 (or at the rounded corners),
            # clicks fell through the dim layer's hole to the app underneath.
            # An invisible alpha-1 fill over the full rect makes it solid.
            painter.fillRect(self.rect(), QColor(0, 0, 0, 1))

        opacity = max(0.0, min(1.0, self.bg_opacity))
        painter.fillPath(path, QColor(*theme.PANEL_RGB, int(opacity * 255)))
        if self.edit_mode:
            edge = QColor(theme.ACCENT_UNLOCKED)
            edge.setAlpha(230)
            painter.setPen(QPen(edge, 2))
            painter.drawPath(path)
        elif opacity > 0.05:
            # A faint rim so the panel reads as a surface on any wallpaper;
            # it fades out together with the background.
            painter.setPen(QPen(QColor(255, 255, 255, int(28 * opacity)), 1))
            painter.drawPath(path)

    def _on_opacity_changed(self, value: int):
        self.bg_opacity = value / 100.0
        self.cfg["bg_opacity"] = self.bg_opacity
        settings_store.save_settings(self.cfg)
        self.update()

    def _on_manual_scroll(self):
        if self._programmatic_scroll:
            return
        self._auto_follow = False
        self._last_manual_scroll_time = time.time()

    def _quit_app(self):
        self._retry_timer.stop()
        self.poll_worker.stop()
        self.poll_worker.wait(1500)
        for worker in list(self._lyrics_workers):
            worker.wait(1000)
        from PySide6.QtWidgets import QApplication
        QApplication.instance().quit()

    # ---------- data handling ----------
    def _on_now_playing(self, snapshot: Optional[NowPlaying]):
        self.now_playing = snapshot
        self._update_track_label()
        if snapshot is None:
            if self.current_track_key is not None:
                self.current_track_key = None
                self._set_status_line("Nothing playing on Spotify")
            return

        if snapshot.track_key != self.current_track_key:
            self.current_track_key = snapshot.track_key
            self.synced_lines = []
            self._active_index = -1
            self._auto_follow = True
            self._last_shown_position = None
            self._retry_timer.stop()
            self._fetch_attempt = 0
            self._showing_fallback = False

            # Spotify Free ads report a title but no artist -- nothing to look up.
            if not snapshot.artist:
                self._fetch_args = None
                self._set_status_line("No lyrics for this track.")
                return

            self._fetch_args = (
                snapshot.artist, snapshot.title, snapshot.album,
                snapshot.duration_sec, snapshot.track_key,
            )
            self._start_lyrics_fetch()

    def _start_lyrics_fetch(self):
        if self._fetch_args is None or self._fetch_args[4] != self.current_track_key:
            return
        # A background retry for timed lyrics shouldn't wipe the plain
        # fallback lyrics already on screen.
        if not self._showing_fallback:
            self._set_status_line("Loading lyrics...")
        worker = LyricsFetchWorker(*self._fetch_args)
        worker.lyrics_ready.connect(self._on_lyrics_ready)
        # The fetch is a blocking call with no event loop, so it can't be
        # cancelled on a track skip. Hold a reference until it really
        # finishes: dropping it mid-run lets Python destroy a running
        # QThread, which aborts the process. Stale results are discarded by
        # the track_key check in _on_lyrics_ready.
        self._lyrics_workers.add(worker)
        worker.finished.connect(lambda w=worker: self._on_worker_finished(w))
        worker.start()

    def _on_worker_finished(self, worker: "LyricsFetchWorker"):
        self._lyrics_workers.discard(worker)
        worker.deleteLater()

    def _on_lyrics_ready(self, track_key, synced, plain, state):
        if track_key != self.current_track_key:
            return  # stale result from a track we've already moved on from

        if state in ("error", "fallback"):
            # lrclib was unreachable. Show the plain fallback if we got one
            # (or keep showing one we already have), and keep retrying lrclib
            # in the background so timed lyrics replace it once it's back.
            delay = _LYRICS_RETRY_DELAYS_SEC[min(self._fetch_attempt, len(_LYRICS_RETRY_DELAYS_SEC) - 1)]
            self._fetch_attempt += 1
            if state == "fallback" and plain:
                if not self._showing_fallback:
                    self._set_status_line(plain, content=True)
                    self._showing_fallback = True
            elif not self._showing_fallback:
                self._set_status_line(f"Lyrics server unavailable. Retrying in {delay}s...")
            self._retry_timer.start(delay * 1000)
            return

        self._showing_fallback = False
        if state == "synced" and synced:
            self.synced_lines = synced
            self._render_synced_lines()
        elif state == "plain" and plain:
            self._set_status_line(plain, content=True)
        elif state == "instrumental":
            self._set_status_line("(Instrumental -- no lyrics)")
        else:
            self._set_status_line("No lyrics found for this track.")

    def _render_synced_lines(self):
        self._clear_lines()
        self.line_labels = []
        self._stop_line_fade()
        for i, (_timestamp, text) in enumerate(self.synced_lines):
            label = QLabel(text)
            label.setAlignment(Qt.AlignCenter)
            label.setWordWrap(True)
            label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            label.setFont(theme.line_font(False))
            self.lyrics_layout.addWidget(label)
            self.line_labels.append(label)
        # Colour lives in the palette, not a stylesheet: re-styling dozens of
        # labels from a stylesheet every animation frame would be far costlier.
        self._line_alpha = [theme.line_alpha(i + 1) for i in range(len(self.line_labels))]
        for label, alpha in zip(self.line_labels, self._line_alpha):
            self._set_label_alpha(label, alpha)
        self._styled_index = -1
        self._active_index = -1
        self._update_dynamic_padding()

    # ---------- playback-synced scrolling ----------
    def _on_tick(self):
        if not self.synced_lines or self.now_playing is None:
            return

        position = self.now_playing.interpolated_position()

        # A fresh poll can report a position slightly behind what we were
        # already displaying (the OS timestamp is coarse). Ignore small
        # backward jitter so the highlighted line doesn't flicker back and
        # forth; a large jump (an actual seek) is still honored immediately.
        if self._last_shown_position is not None:
            regression = self._last_shown_position - position
            if 0 < regression < 2.5:
                position = self._last_shown_position
        self._last_shown_position = position

        timestamps = [t for t, _ in self.synced_lines]
        idx = bisect.bisect_right(timestamps, position) - 1
        idx = max(0, min(idx, len(self.synced_lines) - 1))

        if idx != self._active_index:
            self._active_index = idx
            self._highlight_active_line(idx)
            if self._auto_follow:
                self._scroll_to_line(idx)

        if not self._auto_follow and (time.time() - self._last_manual_scroll_time) > AUTO_FOLLOW_PAUSE_SEC:
            self._auto_follow = True
            self._scroll_to_line(self._active_index)

    def _set_label_alpha(self, label: QLabel, alpha: float):
        palette = label.palette()
        palette.setColor(QPalette.WindowText, theme.text_color(alpha))
        label.setPalette(palette)

    def _stop_line_fade(self):
        if self._line_fade is not None:
            self._line_fade.stop()
            self._line_fade = None

    def _highlight_active_line(self, idx: int):
        """Fonts switch at once (they change the layout the scroll target is
        measured against); colours cross-fade, so the highlight moves smoothly
        instead of snapping."""
        old = self._styled_index
        self._styled_index = idx
        for i, label in enumerate(self.line_labels):
            label.setFont(theme.line_font(i == idx))

        targets = {}
        for i in range(len(self.line_labels)):
            near = (i - idx) ** 2 <= theme.FADE_RANGE ** 2 or (i - old) ** 2 <= theme.FADE_RANGE ** 2
            target = theme.line_alpha(abs(i - idx) if idx >= 0 else i + 1)
            if near or abs(self._line_alpha[i] - target) > 0.005:
                targets[i] = target
        starts = {i: self._line_alpha[i] for i in targets}

        self._stop_line_fade()
        duration = theme.motion_ms(240)
        if duration == 0:
            for i, target in targets.items():
                self._line_alpha[i] = target
                self._set_label_alpha(self.line_labels[i], target)
            return

        def step(t):
            for i, target in targets.items():
                alpha = starts[i] + (target - starts[i]) * t
                self._line_alpha[i] = alpha
                self._set_label_alpha(self.line_labels[i], alpha)

        fade = QVariantAnimation(self)
        fade.setStartValue(0.0)
        fade.setEndValue(1.0)
        fade.setDuration(duration)
        fade.setEasingCurve(QEasingCurve.OutCubic)
        fade.valueChanged.connect(step)
        self._line_fade = fade
        fade.start()

    def _scroll_to_line(self, idx: int):
        if idx < 0 or idx >= len(self.line_labels):
            return
        label = self.line_labels[idx]

        # A font/style change (becoming the active line) or a resize can
        # change how many lines this label wraps to. Force the layout to
        # settle *now* so pos()/height() below reflect the new wrapped size
        # instead of stale pre-change values -- otherwise a line that just
        # grew to 2-3 lines gets mis-centered and its edges end up outside
        # the visible viewport.
        self.lyrics_container.updateGeometry()
        self.lyrics_layout.activate()

        target_y = label.pos().y() + label.height() / 2 - self.scroll_area.viewport().height() / 2
        target_y = max(0, min(target_y, self.scroll_area.verticalScrollBar().maximum()))

        self._programmatic_scroll = True
        anim = QPropertyAnimation(self.scroll_area.verticalScrollBar(), b"value", self)
        anim.setDuration(theme.motion_ms(350))
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.setStartValue(self.scroll_area.verticalScrollBar().value())
        anim.setEndValue(int(target_y))
        anim.finished.connect(lambda: setattr(self, "_programmatic_scroll", False))
        anim.start()
        self._scroll_anim = anim
