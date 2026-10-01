"""Small always-idle helper: press the start/stop shortcut (Ctrl+Alt+P by
default) to start the lyrics overlay, press it again to stop it. Run this once
(e.g. from Windows startup) and leave it running in the tray -- it's the thing
that's actually listening for the hotkey when the overlay itself isn't running
yet. The shortcut is a setting: change it in the overlay's settings pane or the
installer, and this picks it up within a couple of seconds."""
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR / "src"))

import hotkey_spec  # noqa: E402
import settings as settings_store  # noqa: E402
from hotkey import GlobalHotkey  # noqa: E402

FROZEN = getattr(sys, "frozen", False)  # True inside the PyInstaller build
_SCRIPTS_DIR = BASE_DIR / ".venv" / "Scripts"
# pythonw has no console window, so the overlay can't be killed by closing one.
VENV_PYTHON = _SCRIPTS_DIR / "pythonw.exe"
if not VENV_PYTHON.exists():
    VENV_PYTHON = _SCRIPTS_DIR / "python.exe"
LOG_FILE = Path(os.environ.get("APPDATA", Path.home())) / "TopDisplayLyricsOverlay" / "overlay.log"
MAIN_SCRIPT = BASE_DIR / "src" / "main.py"
LAUNCHER_HOTKEY_ID = 2
SETTINGS_POLL_MS = 1500


def _make_icon(color: QColor) -> QIcon:
    pixmap = QPixmap(32, 32)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(color)
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(2, 2, 28, 28)
    painter.end()
    return QIcon(pixmap)


_STOPPED_COLOR = QColor(140, 140, 140)
_RUNNING_COLOR = QColor(30, 215, 96)


class AppLauncher:
    def __init__(self, tray: QSystemTrayIcon, combo: str):
        self.tray = tray
        self.combo = combo            # the current start/stop shortcut, for messages
        self.process: Optional[subprocess.Popen] = None
        self._set_stopped_visuals()

    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def toggle(self):
        self.stop() if self.is_running() else self.start()

    def set_combo(self, combo: str):
        self.combo = combo
        # Refresh the tooltip for whichever state we are in.
        if self.is_running():
            self.tray.setToolTip(f"Top Display -- running ({combo} to stop)")
        else:
            self.tray.setToolTip(f"Top Display -- stopped ({combo} to start)")

    def start(self):
        if self.is_running():
            return
        if not FROZEN and not VENV_PYTHON.exists():
            self.tray.showMessage(
                "Top Display",
                "Virtual env not found. Run: python -m venv .venv && "
                ".venv\\Scripts\\pip install -r requirements.txt",
                QSystemTrayIcon.Warning,
            )
            return
        # With no console, a crash would otherwise vanish silently: keep the
        # overlay's output in a log file to look at.
        try:
            LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
            log = open(LOG_FILE, "ab")
        except OSError:
            log = subprocess.DEVNULL
        # Packaged app: run ourselves again in overlay mode (no venv exists).
        command = [sys.executable, "--overlay"] if FROZEN else [str(VENV_PYTHON), str(MAIN_SCRIPT)]
        self.process = subprocess.Popen(
            command, cwd=str(BASE_DIR),
            stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if log is not subprocess.DEVNULL:
            log.close()
        self.tray.setIcon(_make_icon(_RUNNING_COLOR))
        self.tray.setToolTip(f"Top Display -- running ({self.combo} to stop)")

    def stop(self):
        if self.process is not None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None
        self._set_stopped_visuals()

    def _set_stopped_visuals(self):
        self.tray.setIcon(_make_icon(_STOPPED_COLOR))
        self.tray.setToolTip(f"Top Display -- stopped ({self.combo} to start)")


class ShortcutWatcher:
    """Keeps the start/stop hotkey in step with settings.json.

    The settings pane (a different process) rewrites that file when the user
    picks a new shortcut; this notices and re-registers. A read that fails or
    holds anything invalid is ignored -- the current shortcut simply stays.
    """

    def __init__(self, tray, hotkey: GlobalHotkey, launcher: AppLauncher, action, combo: str):
        self.tray, self.hotkey, self.launcher, self.action = tray, hotkey, launcher, action
        self.combo = combo
        self._seen_mtime = settings_store.settings_mtime()
        self.timer = QTimer()
        self.timer.setInterval(SETTINGS_POLL_MS)
        self.timer.timeout.connect(self.check)
        self.timer.start()

    def check(self):
        mtime = settings_store.settings_mtime()
        if mtime == self._seen_mtime:
            return
        saved = settings_store.read_hotkeys_strict()
        if saved is None:
            return   # unreadable / half-written: try again on the next poll
        self._seen_mtime = mtime
        new = saved["hotkey_toggle"]
        if new == self.combo:
            return
        modifiers, vk = hotkey_spec.to_win32(new)
        if self.hotkey.rebind(modifiers, vk):
            self.combo = new
            self.launcher.set_combo(new)
            self.action.setText(f"Start / stop overlay ({new})")
        else:
            self.tray.showMessage(
                "Top Display",
                f"{new} is already used by another program, so the start/stop shortcut "
                f"stays {self.combo}. Pick another one in the overlay's settings.",
                QSystemTrayIcon.Warning,
            )


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    combo = settings_store.load_settings()["hotkey_toggle"]

    tray = QSystemTrayIcon(_make_icon(_STOPPED_COLOR), app)
    launcher = AppLauncher(tray, combo)

    menu = QMenu()
    toggle_action = menu.addAction(f"Start / stop overlay ({combo})")
    toggle_action.triggered.connect(launcher.toggle)
    quit_action = menu.addAction("Quit launcher")

    def _quit():
        launcher.stop()
        app.quit()

    quit_action.triggered.connect(_quit)
    tray.setContextMenu(menu)
    tray.activated.connect(
        lambda reason: launcher.toggle() if reason == QSystemTrayIcon.Trigger else None
    )
    tray.show()

    modifiers, vk = hotkey_spec.to_win32(combo)
    hotkey = GlobalHotkey(launcher.toggle, vk_code=vk, modifiers=modifiers, hotkey_id=LAUNCHER_HOTKEY_ID)
    if not hotkey.registered:
        tray.showMessage(
            "Top Display",
            f"{combo} is already in use by another app -- use the tray menu instead, "
            "or choose another shortcut in the overlay's settings.",
            QSystemTrayIcon.Warning,
        )
    app.installNativeEventFilter(hotkey)
    app.aboutToQuit.connect(hotkey.unregister)
    app.aboutToQuit.connect(launcher.stop)

    watcher = ShortcutWatcher(tray, hotkey, launcher, toggle_action, combo)  # noqa: F841 (kept alive)
    app._shortcut_watcher = watcher

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
