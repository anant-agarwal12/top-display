"""Registers a system-wide hotkey using the Win32 API directly -- no extra
dependency needed, works even when the target window isn't focused. Shared
by the overlay (Ctrl+Alt+L, lock/unlock) and the launcher (Ctrl+Alt+P,
start/stop the overlay process) -- each needs its own key combo and hotkey
id since Windows hotkey registration is exclusive per combo system-wide."""
import ctypes
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312

VK_L = 0x4C
VK_P = 0x50

DEFAULT_MODIFIERS = MOD_CONTROL | MOD_ALT


class GlobalHotkey(QAbstractNativeEventFilter):
    def __init__(self, callback, vk_code: int, modifiers: int = DEFAULT_MODIFIERS, hotkey_id: int = 1):
        super().__init__()
        self._callback = callback
        self._hotkey_id = hotkey_id
        self._registered = bool(
            ctypes.windll.user32.RegisterHotKey(
                None, hotkey_id, modifiers | MOD_NOREPEAT, vk_code
            )
        )

    @property
    def registered(self) -> bool:
        return self._registered

    def nativeEventFilter(self, event_type, message):
        if bytes(event_type) == b"windows_generic_MSG":
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY and msg.wParam == self._hotkey_id:
                self._callback()
        return False, 0

    def unregister(self):
        if self._registered:
            ctypes.windll.user32.UnregisterHotKey(None, self._hotkey_id)
            self._registered = False
