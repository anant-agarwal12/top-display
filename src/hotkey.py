"""Registers a system-wide hotkey using the Win32 API directly -- no extra
dependency needed, works even when the target window isn't focused. Shared
by the overlay (lock/unlock) and the launcher (start/stop the overlay
process) -- each owns its own shortcut and hotkey id, since Windows hotkey
registration is exclusive per combo system-wide.

Which key combinations are allowed, and how they are written down
("Ctrl+Alt+P"), lives in hotkey_spec.py.
"""
import ctypes
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter

import hotkey_spec

MOD_ALT = hotkey_spec.MOD_ALT
MOD_CONTROL = hotkey_spec.MOD_CONTROL
MOD_SHIFT = hotkey_spec.MOD_SHIFT
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312

VK_L = 0x4C
VK_P = 0x50

DEFAULT_MODIFIERS = MOD_CONTROL | MOD_ALT

_PROBE_ID = 0x7FF0   # a spare id, only used to test whether a combo is free


def is_available(modifiers: int, vk_code: int) -> bool:
    """True if no other program currently owns this combination. Registers it
    for an instant and releases it again."""
    user32 = ctypes.windll.user32
    if not user32.RegisterHotKey(None, _PROBE_ID, modifiers | MOD_NOREPEAT, vk_code):
        return False
    user32.UnregisterHotKey(None, _PROBE_ID)
    return True


class GlobalHotkey(QAbstractNativeEventFilter):
    def __init__(self, callback, vk_code: int, modifiers: int = DEFAULT_MODIFIERS, hotkey_id: int = 1):
        super().__init__()
        self._callback = callback
        self._hotkey_id = hotkey_id
        self._modifiers = modifiers
        self._vk = vk_code
        self._registered = bool(
            ctypes.windll.user32.RegisterHotKey(
                None, hotkey_id, modifiers | MOD_NOREPEAT, vk_code
            )
        )

    @property
    def registered(self) -> bool:
        return self._registered

    def rebind(self, modifiers: int, vk_code: int) -> bool:
        """Switch to a new combination. If another program owns it, the previous
        one is put back and False is returned, so a failed change never leaves
        the app without a working shortcut. Must run on the thread that created
        this hotkey (Windows ties the registration to the calling thread)."""
        user32 = ctypes.windll.user32
        if self._registered:
            user32.UnregisterHotKey(None, self._hotkey_id)
            self._registered = False
        if user32.RegisterHotKey(None, self._hotkey_id, modifiers | MOD_NOREPEAT, vk_code):
            self._modifiers, self._vk = modifiers, vk_code
            self._registered = True
            return True
        # Roll back to what we had.
        self._registered = bool(
            user32.RegisterHotKey(None, self._hotkey_id, self._modifiers | MOD_NOREPEAT, self._vk)
        )
        return False

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
