"""The app's version, read from the VERSION file (the single source of truth that the
installer build also uses). In the packaged app the file is bundled next to the
modules; from source it sits in the project root."""
import sys
from pathlib import Path


def get_version() -> str:
    candidates = []
    bundled = getattr(sys, "_MEIPASS", None)
    if bundled:
        candidates.append(Path(bundled) / "VERSION")
    candidates.append(Path(__file__).resolve().parent.parent / "VERSION")
    for path in candidates:
        try:
            text = path.read_text(encoding="utf-8-sig").strip()
        except OSError:
            continue
        if text:
            return text
    return "unknown"
