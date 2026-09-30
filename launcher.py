"""Small always-idle helper: press Ctrl+Alt+P to start the lyrics overlay,
press it again to stop it. Run this once (e.g. from Windows startup) and
leave it running in the tray -- it's the thing that's actually listening
for the hotkey when the overlay itself isn't running yet."""
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR / "src"))

from hotkey import GlobalHotkey, VK_P  # noqa: E402

FROZEN = getattr(sys, "frozen", False)  # True inside the PyInstaller build
_SCRIPTS_DIR = BASE_DIR / ".venv" / "Scripts"
# pythonw has no console window, so the overlay can't be killed by closing one.
VENV_PYTHON = _SCRIPTS_DIR / "pythonw.exe"
if not VENV_PYTHON.exists():
    VENV_PYTHON = _SCRIPTS_DIR / "python.exe"
LOG_FILE = Path(os.environ.get("APPDATA", Path.home())) / "TopDisplayLyricsOverlay" / "overlay.log"
MAIN_SCRIPT = BASE_DIR / "src" / "main.py"
LAUNCHER_HOTKEY_ID = 2


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
    def __init__(self, tray: QSystemTrayIcon):
        self.tray = tray
        self.process: Optional[subprocess.Popen] = None
        self._set_stopped_visuals()

    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def toggle(self):
        self.stop() if self.is_running() else self.start()

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
        self.tray.setToolTip("Top Display -- running (Ctrl+Alt+P to stop)")

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
        self.tray.setToolTip("Top Display -- stopped (Ctrl+Alt+P to start)")


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    tray = QSystemTrayIcon(_make_icon(_STOPPED_COLOR), app)
    launcher = AppLauncher(tray)

    menu = QMenu()
    toggle_action = menu.addAction("Start / stop overlay (Ctrl+Alt+P)")
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

    hotkey = GlobalHotkey(launcher.toggle, vk_code=VK_P, hotkey_id=LAUNCHER_HOTKEY_ID)
    if not hotkey.registered:
        tray.showMessage(
            "Top Display",
            "Ctrl+Alt+P is already in use by another app -- use the tray menu instead.",
            QSystemTrayIcon.Warning,
        )
    app.installNativeEventFilter(hotkey)
    app.aboutToQuit.connect(hotkey.unregister)
    app.aboutToQuit.connect(launcher.stop)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
