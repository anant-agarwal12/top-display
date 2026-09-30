import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor
from PySide6.QtCore import Qt

from overlay_window import LyricsOverlay
from hotkey import GlobalHotkey, VK_L


def _make_tray_icon() -> QIcon:
    pixmap = QPixmap(32, 32)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QColor(30, 215, 96))  # Spotify-green-ish, no trademark assets used
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(2, 2, 28, 28)
    painter.end()
    return QIcon(pixmap)


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    overlay = LyricsOverlay()
    overlay.show()

    hotkey = GlobalHotkey(overlay.toggle_edit_mode, vk_code=VK_L, hotkey_id=1)
    app.installNativeEventFilter(hotkey)
    app.aboutToQuit.connect(hotkey.unregister)

    tray = QSystemTrayIcon(_make_tray_icon(), app)
    tray.setToolTip("Top Display - Lyrics Overlay")

    menu = QMenu()
    toggle_action = menu.addAction("Show/Hide Overlay")
    toggle_action.triggered.connect(
        lambda: overlay.hide() if overlay.isVisible() else overlay.show()
    )
    quit_action = menu.addAction("Quit")
    quit_action.triggered.connect(overlay._quit_app)

    tray.setContextMenu(menu)
    tray.activated.connect(
        lambda reason: (overlay.hide() if overlay.isVisible() else overlay.show())
        if reason == QSystemTrayIcon.Trigger else None
    )
    tray.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
