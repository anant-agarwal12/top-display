"""Loads/saves overlay settings (opacity, window geometry) to a local JSON
file so preferences persist between runs."""
import json
import os
from pathlib import Path

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
}


def load_settings() -> dict:
    if _SETTINGS_FILE.exists():
        try:
            data = json.loads(_SETTINGS_FILE.read_text(encoding="utf-8"))
            merged = dict(DEFAULTS)
            merged.update(data)
            return merged
        except Exception:
            pass
    return dict(DEFAULTS)


def save_settings(settings: dict) -> None:
    try:
        _SETTINGS_FILE.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    except Exception:
        pass
