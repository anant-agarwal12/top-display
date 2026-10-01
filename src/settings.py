"""Loads/saves overlay settings (opacity, window geometry) to a local JSON
file so preferences persist between runs."""
import json
import os
from pathlib import Path
from typing import Optional

import hotkey_spec
import lyric_styles

_SETTINGS_DIR = Path(os.environ.get("APPDATA", Path.home())) / "TopDisplayLyricsOverlay"
_SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
_SETTINGS_FILE = _SETTINGS_DIR / "settings.json"

DEFAULTS = {
    "bg_opacity": 0.55,   # 0.0 (fully transparent) - 1.0 (opaque)
    # None = first run: the lyrics window is placed at the top-right of the
    # primary screen, and the settings gear on its left edge, 30% from the top.
    # A saved settings.json keeps whatever position the user already has.
    "window_x": None,
    "window_y": None,
    "window_w": 420,
    "window_h": 560,
    "gear_x": None,
    "gear_y": None,
    "hotkey_toggle": hotkey_spec.DEFAULT_TOGGLE,   # start / stop the overlay (tray launcher)
    "hotkey_lock": hotkey_spec.DEFAULT_LOCK,       # lock / unlock the overlay
    "animation": lyric_styles.DEFAULT_STYLE,       # how the lyrics animate (see lyric_styles)
}


def settings_dir() -> Path:
    """The folder holding settings.json and the error log."""
    return _SETTINGS_DIR


def _sanitise_hotkeys(merged: dict) -> dict:
    """A hand-edited or corrupt shortcut falls back to its default, and the two
    shortcuts can never be the same (that would make one of them dead)."""
    toggle = hotkey_spec.normalize(merged.get("hotkey_toggle"))
    lock = hotkey_spec.normalize(merged.get("hotkey_lock"))
    merged["animation"] = lyric_styles.normalize(merged.get("animation"))
    merged["hotkey_toggle"] = toggle or hotkey_spec.DEFAULT_TOGGLE
    merged["hotkey_lock"] = lock or hotkey_spec.DEFAULT_LOCK
    if merged["hotkey_toggle"] == merged["hotkey_lock"]:
        merged["hotkey_toggle"] = hotkey_spec.DEFAULT_TOGGLE
        merged["hotkey_lock"] = hotkey_spec.DEFAULT_LOCK
    return merged


def load_settings() -> dict:
    if _SETTINGS_FILE.exists():
        try:
            data = json.loads(_SETTINGS_FILE.read_text(encoding="utf-8-sig"))
            merged = dict(DEFAULTS)
            merged.update(data)
            return _sanitise_hotkeys(merged)
        except Exception:
            pass
    return _sanitise_hotkeys(dict(DEFAULTS))


def read_hotkeys_strict() -> Optional[dict]:
    """The two shortcuts exactly as saved, or None if the file is missing,
    unreadable, mid-write or holds anything invalid. The tray launcher uses
    this so a half-written file can never make it rebind to something else."""
    try:
        data = json.loads(_SETTINGS_FILE.read_text(encoding="utf-8-sig"))
        toggle = hotkey_spec.normalize(data["hotkey_toggle"])
        lock = hotkey_spec.normalize(data["hotkey_lock"])
    except Exception:
        return None
    if not toggle or not lock or toggle == lock:
        return None
    return {"hotkey_toggle": toggle, "hotkey_lock": lock}


def settings_mtime() -> float:
    try:
        return _SETTINGS_FILE.stat().st_mtime
    except OSError:
        return 0.0


def save_settings(settings: dict) -> None:
    # Write a temp file and swap it in: other processes (the tray launcher)
    # read this file, and must never see it half-written.
    tmp = _SETTINGS_FILE.with_suffix(".json.tmp")
    try:
        tmp.write_text(json.dumps(settings, indent=2), encoding="utf-8")
        os.replace(tmp, _SETTINGS_FILE)
    except Exception:
        pass


def set_hotkeys(toggle: str, lock: str) -> bool:
    """Merge two shortcuts into the existing settings file, keeping every other
    key. Used by the installer. Returns False (and writes nothing) if either is
    not an allowed shortcut or they are the same."""
    toggle_n, lock_n = hotkey_spec.normalize(toggle), hotkey_spec.normalize(lock)
    if not toggle_n or not lock_n or toggle_n == lock_n:
        return False
    data = {}
    if _SETTINGS_FILE.exists():
        try:
            loaded = json.loads(_SETTINGS_FILE.read_text(encoding="utf-8-sig"))
            data = loaded if isinstance(loaded, dict) else {}
        except Exception:
            data = {}
    data["hotkey_toggle"], data["hotkey_lock"] = toggle_n, lock_n
    save_settings(data)
    return True
