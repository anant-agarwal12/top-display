"""The shortcut format, shared by the settings file, the overlay, the tray
launcher, the settings pane and the installer.

Pure Python (no Qt, no Windows calls) so every one of them can import it. A
shortcut is always stored as canonical text such as ``Ctrl+Alt+P``: modifiers in
a fixed order, then one key. Only a small, deliberately conservative set is
allowed, so that anything the settings pane can save can also be shown by the
installer page, and so that Windows-reserved combinations (anything with the
Win key) are never offered.
"""
from typing import List, Optional, Tuple

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004

# Canonical order is Ctrl, Alt, Shift. Order here is also the dropdown order.
MODIFIER_SETS = ("Ctrl+Alt", "Ctrl+Shift", "Alt+Shift", "Ctrl+Alt+Shift")
KEYS: List[str] = (
    [chr(c) for c in range(ord("A"), ord("Z") + 1)]
    + [str(d) for d in range(10)]
    + [f"F{n}" for n in range(1, 13)]
)

DEFAULT_TOGGLE = "Ctrl+Alt+P"   # start / stop the overlay (handled by the tray launcher)
DEFAULT_LOCK = "Ctrl+Alt+L"     # lock / unlock the overlay (handled by the overlay)

_MOD_BITS = {"Ctrl": MOD_CONTROL, "Alt": MOD_ALT, "Shift": MOD_SHIFT}
_MOD_ORDER = ("Ctrl", "Alt", "Shift")


def _vk(key: str) -> int:
    if len(key) == 1 and key.isalpha():
        return ord(key)               # VK_A..VK_Z equal their ASCII capitals
    if len(key) == 1 and key.isdigit():
        return ord(key)               # VK_0..VK_9 equal their ASCII digits
    return 0x70 + int(key[1:]) - 1    # VK_F1 = 0x70


def split(text: str) -> Optional[Tuple[str, str]]:
    """'ctrl + alt + p' -> ('Ctrl+Alt', 'P'), or None if it is not an allowed shortcut."""
    if not isinstance(text, str):
        return None
    parts = [p.strip() for p in text.split("+") if p.strip()]
    if len(parts) < 2:
        return None
    key = parts[-1].upper()
    if key not in KEYS:
        return None
    mods = set()
    for part in parts[:-1]:
        name = part.capitalize()
        if name not in _MOD_BITS or name in mods:
            return None
        mods.add(name)
    modifier_set = "+".join(m for m in _MOD_ORDER if m in mods)
    if modifier_set not in MODIFIER_SETS:
        return None
    return modifier_set, key


def normalize(text: str) -> Optional[str]:
    """Canonical text for an allowed shortcut, else None."""
    parts = split(text)
    return f"{parts[0]}+{parts[1]}" if parts else None


def join(modifier_set: str, key: str) -> str:
    return f"{modifier_set}+{key}"


def to_win32(text: str) -> Optional[Tuple[int, int]]:
    """(modifier bit mask, virtual-key code) for RegisterHotKey, or None."""
    parts = split(text)
    if not parts:
        return None
    modifier_set, key = parts
    mask = 0
    for name in modifier_set.split("+"):
        mask |= _MOD_BITS[name]
    return mask, _vk(key)
