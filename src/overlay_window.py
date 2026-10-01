"""The transparent, always-on-top, scrollable lyrics overlay window."""
import bisect
import ctypes
import time
from typing import List, Optional, Tuple

from PySide6.QtCore import (
    Qt, QThread, Signal, QTimer, QPropertyAnimation, QVariantAnimation, QEasingCurve,
    QPoint, QRect, QEvent,
)
from PySide6.QtGui import (
    QBrush, QColor, QPainter, QPainterPath, QPen, QGuiApplication, QRegion, QLinearGradient,
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QScrollArea, QSlider, QSizePolicy,
)

from media_session import fetch_now_playing, NowPlaying
from lyrics_fetcher import fetch_lyrics
import settings as settings_store
import theme
import hotkey as hotkey_api
import hotkey_spec
import lyric_styles
from lyric_label import LyricLabel
from gear_window import GearWindow


POLL_INTERVAL_SEC = 1.0
TICK_MS = 16   # ~60 fps: the karaoke sweep and typewriter progress are driven from this tick
FADE_RANGE = 9  # lines further than this from the current one are already at their resting look
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
        window_pos, gear_pos = self._initial_positions()
        self.move(window_pos)
        self._clamp_to_screens()

        self.bg_opacity = self.cfg["bg_opacity"]
        self.edit_mode = False
        self._resize_margin = 10
        self._drag_state: Optional[dict] = None
        self._dimmer = ScreenDimmer()
        self._min_size = (160, 120)

        # Every top-level widget this project owns and wants clickable while
        # the screen is dimmed goes here. Any future window/button just calls
        # register_interactive_window(widget) -- it does not need to touch
        # ScreenDimmer or know the dim layer exists at all.
        self._interactive_windows: List[QWidget] = [self]

        # The floating settings gear + its pane live in their own window,
        # shown only while unlocked. It is registered like any other
        # interactive window so it stays clickable through the dim layer.
        self.lock_hotkey = None   # set by main.py: the live lock/unlock shortcut, so it can be rebound
        self.gear_window = GearWindow(
            gear_pos, self.cfg["animation"], self.cfg["hotkey_toggle"], self.cfg["hotkey_lock"],
        )
        self.gear_window.clamp_to_screens()
        self.gear_window.geometry_changed.connect(self._refresh_dim_mask)
        self.gear_window.position_saved.connect(self._on_gear_moved)
        self.gear_window.animation_changed.connect(self.set_animation_style)
        self.gear_window.set_hotkey_handler(self._change_hotkey)
        self.gear_window.reset_hotkeys_requested.connect(self._reset_hotkeys)
        # A dropdown's list is its own window; keep it above the dim layer while it is open.
        self.gear_window.popup_opened.connect(self.register_interactive_window)
        self.gear_window.popup_closed.connect(self.unregister_interactive_window)
        self.gear_window.quit_requested.connect(self._quit_app)
        self.register_interactive_window(self.gear_window)

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
        self._style = lyric_styles.get(self.cfg["animation"])   # see lyric_styles.py
        self._timestamps: List[float] = []     # start time of every lyric line, for bisect
        self._line_alpha: List[float] = []     # current text alpha of each lyric line
        self._line_emph: List[float] = []      # current emphasis (0 resting .. 1 current) of each line
        self._styled_index = -1                # which line the styling currently treats as current
        self._line_fade: Optional[QVariantAnimation] = None
        self._fade_gen = 0                     # bumped whenever a fade is superseded
        self._scroll_anim: Optional[QPropertyAnimation] = None
        self._scroll_gen = 0

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

        # The opacity slider is the only control left on the lyrics window. It
        # floats over the top edge instead of sitting in a layout row, so
        # locking/unlocking never changes the lyrics viewport's height (which
        # used to re-centre the current line every time).
        self.opacity_slider = QSlider(Qt.Horizontal, self)
        self.opacity_slider.setStyleSheet(theme.SLIDER_QSS)
        self.opacity_slider.setToolTip("Background opacity")
        self.opacity_slider.setAccessibleName("Background opacity")
        self.opacity_slider.setRange(0, 100)
        self.opacity_slider.setValue(int(self.bg_opacity * 100))
        self.opacity_slider.valueChanged.connect(self._on_opacity_changed)
        self._place_opacity_slider()

        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QScrollArea.NoFrame)
        self.scroll_area.setStyleSheet("background: transparent; border: none;")
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
        self.lyrics_layout.setSpacing(10)
        self.lyrics_layout.setContentsMargins(6, 30, 6, 30)

        self.scroll_area.setWidget(self.lyrics_container)
        root.addWidget(self.scroll_area, stretch=1)

        # Clicks on the lyrics viewport target that child widget directly, not
        # this window -- filter its events so dragging/resizing still works
        # from anywhere on the overlay (edges resize, the middle moves).
        self.scroll_area.viewport().installEventFilter(self)

        self._set_status_line("Waiting for Spotify...")
        self._apply_edit_mode_visuals()

    def _update_dynamic_padding(self):
        """Top/bottom padding scales with the available viewport height, so
        the amount of previous/next lyric context shown adapts to the
        window's current size instead of assuming a fixed amount of space,
        while always leaving room to center the current line. The side
        margins leave room for the current line to be painted larger without
        touching the window edge."""
        viewport = self.scroll_area.viewport()
        pad = max(24, viewport.height() // 2)
        side = 6
        margins = self.lyrics_layout.contentsMargins()
        if margins.top() == pad and margins.left() == side:
            return
        self.lyrics_layout.setContentsMargins(side, pad, side, pad)
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
        self.opacity_slider.setVisible(self.edit_mode)
        if self.edit_mode:
            # Shown first so its rectangle gets a hole in the dim layer.
            self.gear_window.show_for_edit()
            self._dimmer.show_all(self._exclude_rects())
            self.raise_()
            self.activateWindow()
            self._reassert_topmost()
            self._topmost_timer.start()
        else:
            self._topmost_timer.stop()
            self._dimmer.hide_all()
            self.gear_window.hide_for_lock()
            self._drag_state = None
            self.setCursor(Qt.ArrowCursor)
        self._update_track_label()
        self.update()

        # Nothing here changes the lyrics viewport's size any more, but this
        # keeps the current line centred if anything ever does.
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
        """The song title/artist live in the settings pane, not on the window."""
        if self.now_playing is None:
            self.gear_window.set_now_playing(None, None)
        else:
            self.gear_window.set_now_playing(self.now_playing.title, self.now_playing.artist)

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
        if obj is self.scroll_area.viewport():
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
        self._place_opacity_slider()
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
        if opacity > 0.05:
            # "Glass" is a surface treatment, not a blur (Windows will not blur
            # behind a see-through Qt window): light falling from the top
            # edge, and a rim that is brighter on top and fades towards the
            # bottom. Both scale with the tint, so opacity 0 is still text-only.
            sheen = QLinearGradient(0, 0, 0, self.height() * 0.45)
            sheen.setColorAt(0.0, QColor(255, 255, 255, int(34 * opacity)))
            sheen.setColorAt(1.0, QColor(255, 255, 255, 0))
            painter.fillPath(path, sheen)
        if self.edit_mode:
            edge = QColor(theme.ACCENT_UNLOCKED)
            edge.setAlpha(230)
            painter.setPen(QPen(edge, 2))
            painter.drawPath(path)
        elif opacity > 0.05:
            rim = QLinearGradient(0, 0, 0, self.height())
            rim.setColorAt(0.0, QColor(255, 255, 255, int(88 * opacity)))
            rim.setColorAt(0.5, QColor(255, 255, 255, int(26 * opacity)))
            rim.setColorAt(1.0, QColor(255, 255, 255, int(46 * opacity)))
            painter.setPen(QPen(QBrush(rim), 1))
            painter.drawPath(path)

    def _on_opacity_changed(self, value: int):
        self.bg_opacity = value / 100.0
        self.cfg["bg_opacity"] = self.bg_opacity
        settings_store.save_settings(self.cfg)
        self.update()

    def _place_opacity_slider(self):
        self.opacity_slider.setGeometry(18, 12, max(40, self.width() - 36), 18)
        self.opacity_slider.raise_()

    # ---------- keyboard shortcuts (edited in the settings pane) ----------
    def _change_hotkey(self, kind: str, combo: str) -> str:
        """Apply a new shortcut. Returns "" on success, else a short reason it was refused.

        The lock/unlock shortcut belongs to this process and is rebound live. The
        start/stop shortcut belongs to the tray launcher (another process), so it
        is only checked for availability here and saved; the launcher notices the
        settings file change and rebinds itself.
        """
        combo = hotkey_spec.normalize(combo)
        if combo is None:
            return "That shortcut isn't allowed."
        key, other = ("hotkey_toggle", "hotkey_lock") if kind == "toggle" else ("hotkey_lock", "hotkey_toggle")
        if combo == self.cfg[key]:
            return ""
        if combo == self.cfg[other]:
            return "That's already the other shortcut."
        modifiers, vk = hotkey_spec.to_win32(combo)
        if kind == "lock":
            if self.lock_hotkey is not None and not self.lock_hotkey.rebind(modifiers, vk):
                return "Another program already uses that shortcut."
        elif not hotkey_api.is_available(modifiers, vk):
            return "Another program already uses that shortcut."
        self.cfg[key] = combo
        settings_store.save_settings(self.cfg)
        return ""

    def _reset_hotkeys(self):
        errors = [
            error for error in (
                self._change_hotkey("lock", hotkey_spec.DEFAULT_LOCK),
                self._change_hotkey("toggle", hotkey_spec.DEFAULT_TOGGLE),
            ) if error
        ]
        self.gear_window.set_hotkeys(self.cfg["hotkey_toggle"], self.cfg["hotkey_lock"])
        if errors:
            self.gear_window.show_message("Couldn't reset everything: " + errors[0].lower())
        else:
            self.gear_window.show_message("Shortcuts reset.", error=False)

    def _on_gear_moved(self, x: int, y: int):
        self.cfg["gear_x"], self.cfg["gear_y"] = x, y
        settings_store.save_settings(self.cfg)

    # ---------- first-run placement ----------
    def _initial_positions(self):
        """Saved positions win. On a first run the lyrics window sits at the
        top-right of the primary screen and the gear on its left edge, 30% of
        the way down (i.e. 70% of the screen height above the bottom)."""
        avail = QGuiApplication.primaryScreen().availableGeometry()

        def saved(key):
            value = self.cfg.get(key)
            return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None

        wx, wy = saved("window_x"), saved("window_y")
        gx, gy = saved("gear_x"), saved("gear_y")
        if wx is None or wy is None:
            wx, wy = avail.right() + 1 - self.width() - 24, avail.top() + 24
        if gx is None or gy is None:
            gx, gy = avail.left() + 24, avail.top() + int(avail.height() * 0.30)
        return QPoint(wx, wy), QPoint(gx, gy)

    def _clamp_to_screens(self):
        """A saved position on a monitor that is no longer connected would
        leave the overlay unreachable; pull it back onto a real screen."""
        geo = self.geometry()
        for screen in QGuiApplication.screens():
            visible = screen.availableGeometry().intersected(geo)
            if visible.width() >= 80 and visible.height() >= 40:
                return
        avail = QGuiApplication.primaryScreen().availableGeometry()
        self.setGeometry(
            avail.x() + 40, avail.y() + 40,
            min(geo.width(), avail.width() - 80), min(geo.height(), avail.height() - 80),
        )

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
        self._timestamps = [t for t, _ in self.synced_lines]
        for _timestamp, text in self.synced_lines:
            label = LyricLabel(text)
            label.configure(self._style["scale"], self._style["mode"], self._peak_scale())
            self.lyrics_layout.addWidget(label)
            self.line_labels.append(label)
        self._styled_index = -1
        self._active_index = -1
        self._apply_look(-1)
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

        # The cue is moved slightly earlier by the style's lead, so that the
        # highlight has finished arriving at the line's real timestamp instead
        # of only starting to.
        idx = bisect.bisect_right(self._timestamps, position + self._style["lead"]) - 1
        idx = max(0, min(idx, len(self.synced_lines) - 1))

        if idx != self._active_index:
            self._active_index = idx
            self._highlight_active_line(idx)
            if self._auto_follow:
                self._scroll_to_line(idx)

        self._update_line_progress(idx, position)

        if not self._auto_follow and (time.time() - self._last_manual_scroll_time) > AUTO_FOLLOW_PAUSE_SEC:
            self._auto_follow = True
            self._scroll_to_line(self._active_index)

    def _update_line_progress(self, idx: int, position: float):
        """Karaoke sweep / typewriter: how far through the current line we are."""
        mode = self._style["mode"]
        if mode == "none" or not (0 <= idx < len(self.line_labels)):
            return
        start = self._timestamps[idx]
        gap = (self._timestamps[idx + 1] - start) if idx + 1 < len(self._timestamps) else 4.0
        if mode == "sweep":
            duration = min(max(0.6, gap) * 0.85, 7.0)      # finishes just before the next line
        else:
            chars = len(self.synced_lines[idx][1])
            duration = min(max(0.6, chars * 0.045), max(0.6, gap) * 0.8)
        self.line_labels[idx].set_progress((position - start) / duration)

    # ---------- line looks ----------
    def _look_for(self, i: int, current: int):
        """(opacity, emphasis) a line should have when `current` is the current line."""
        distance = i - current
        if distance == 0:
            return 1.0, 1.0
        return lyric_styles.line_alpha(self._style, abs(distance), upcoming=distance > 0), 0.0

    def _apply_look(self, current: int):
        """Puts every line straight into the look for `current` (no animation)."""
        self._stop_line_fade()
        mode = self._style["mode"]
        self._line_alpha, self._line_emph = [], []
        for i, label in enumerate(self.line_labels):
            alpha, emphasis = self._look_for(i, current if current >= 0 else -1)
            self._line_alpha.append(alpha)
            self._line_emph.append(emphasis)
            label.set_look(emphasis, alpha)
            label.set_progress(1.0 if (mode != "none" and i < current) else 0.0)

    def _stop_line_fade(self):
        """Stops the running fade. Qt still fires `finished` on a stopped
        animation, so each fade carries a generation number and a superseded
        one's late signals are ignored (they would otherwise overwrite the new
        line's look with stale values)."""
        self._fade_gen += 1
        if self._line_fade is not None:
            self._line_fade.stop()
            self._line_fade.deleteLater()
            self._line_fade = None

    def _emphasis_curve(self) -> QEasingCurve:
        curve = QEasingCurve(getattr(QEasingCurve, self._style["emph_ease"]))
        if self._style["overshoot"] is not None:
            curve.setOvershoot(self._style["overshoot"])
        return curve

    def _highlight_active_line(self, idx: int):
        """Moves the emphasis from the old current line to the new one. Nothing
        here changes any label's size in the layout (emphasis is painted), so
        the list never jumps; only brightness and scale animate."""
        old = self._styled_index
        self._styled_index = idx
        mode = self._style["mode"]
        if mode != "none":
            for i, label in enumerate(self.line_labels):
                if i != idx:
                    label.set_progress(1.0 if i < idx else 0.0)

        targets = {}
        for i in range(len(self.line_labels)):
            alpha, emphasis = self._look_for(i, idx)
            near = abs(i - idx) <= FADE_RANGE or (old >= 0 and abs(i - old) <= FADE_RANGE)
            if near or abs(self._line_alpha[i] - alpha) > 0.005 or abs(self._line_emph[i] - emphasis) > 0.005:
                targets[i] = (alpha, emphasis)
        starts = {i: (self._line_alpha[i], self._line_emph[i]) for i in targets}

        self._stop_line_fade()
        duration = self._style["emph_ms"]
        if duration == 0:
            for i, (alpha, emphasis) in targets.items():
                self._line_alpha[i], self._line_emph[i] = alpha, emphasis
                self.line_labels[i].set_look(emphasis, alpha)
            return

        gen = self._fade_gen

        def step(u):
            if gen != self._fade_gen:
                return
            u = float(u)   # eased progress; an overshooting ease goes past 1.0 on purpose
            for i, (alpha, emphasis) in targets.items():
                a0, e0 = starts[i]
                self._line_alpha[i] = a0 + (alpha - a0) * u
                self._line_emph[i] = e0 + (emphasis - e0) * u
                self.line_labels[i].set_look(self._line_emph[i], self._line_alpha[i])

        def finish():
            if gen != self._fade_gen:
                return
            for i, (alpha, emphasis) in targets.items():
                self._line_alpha[i], self._line_emph[i] = alpha, emphasis
                self.line_labels[i].set_look(emphasis, alpha)

        fade = QVariantAnimation(self)
        fade.setStartValue(0.0)
        fade.setEndValue(1.0)
        fade.setDuration(duration)
        fade.setEasingCurve(self._emphasis_curve())
        fade.valueChanged.connect(step)
        fade.finished.connect(finish)
        self._line_fade = fade
        fade.start()

    def _peak_scale(self) -> float:
        """Largest scale a line is painted at: an overshooting ease bounces ~30% past its target."""
        return 1.0 + (self._style["scale"] - 1.0) * (1.35 if self._style["overshoot"] else 1.0)

    def set_animation_style(self, key: str):
        """Switch the lyric animation style while playing (from the settings pane)."""
        key = lyric_styles.normalize(key)
        self.cfg["animation"] = key
        self._style = lyric_styles.get(key)
        settings_store.save_settings(self.cfg)
        for label in self.line_labels:
            label.configure(self._style["scale"], self._style["mode"], self._peak_scale())
        self._styled_index = self._active_index
        self._apply_look(self._active_index)
        if self._auto_follow and 0 <= self._active_index < len(self.line_labels):
            self._scroll_to_line_deferred(self._active_index)

    def _scroll_to_line(self, idx: int):
        if idx < 0 or idx >= len(self.line_labels):
            return
        label = self.line_labels[idx]

        # Labels keep a fixed size in the layout, but a resize or new lyrics
        # still change it. Force the layout to settle *now* so pos()/height()
        # below are current, or the line ends up mis-centred.
        self.lyrics_container.updateGeometry()
        self.lyrics_layout.activate()

        bar = self.scroll_area.verticalScrollBar()
        target_y = label.pos().y() + label.height() / 2 - self.scroll_area.viewport().height() / 2
        target_y = int(max(0, min(target_y, bar.maximum())))

        self._scroll_gen += 1
        if self._scroll_anim is not None:
            self._scroll_anim.stop()
            self._scroll_anim.deleteLater()
            self._scroll_anim = None

        duration = self._style["scroll_ms"]
        if duration == 0:
            self._programmatic_scroll = True
            bar.setValue(target_y)
            self._programmatic_scroll = False
            return

        self._programmatic_scroll = True
        anim = QPropertyAnimation(bar, b"value", self)
        anim.setDuration(duration)
        curve = QEasingCurve(getattr(QEasingCurve, self._style["scroll_ease"]))
        if self._style["scroll_overshoot"] is not None:
            curve.setOvershoot(self._style["scroll_overshoot"])
        anim.setEasingCurve(curve)
        anim.setStartValue(bar.value())
        anim.setEndValue(target_y)
        scroll_gen = self._scroll_gen
        anim.finished.connect(
            lambda: setattr(self, "_programmatic_scroll", False) if scroll_gen == self._scroll_gen else None
        )
        anim.start()
        self._scroll_anim = anim
