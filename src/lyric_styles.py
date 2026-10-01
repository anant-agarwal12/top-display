"""The lyric animation styles the user can pick from the settings pane.

Pure data (no Qt) so the settings file can validate the saved choice and the
pane can list them. Easing curves are named by their QEasingCurve type and
turned into curves in overlay_window.

Each style answers the same questions: how big the current line gets, how the
current line arrives (duration / easing), how the list scrolls, how strongly the
other lines fade with distance, and whether the current line also shows
progress through the line (a colour sweep, or letters typing in).
"""
from typing import Dict

DEFAULT_STYLE = "smooth"

# Order here is the order in the dropdown.
STYLES: Dict[str, dict] = {
    "smooth": dict(
        label="Smooth",
        hint="The current line grows and brightens while the list glides to it.",
        scale=1.22, emph_ms=280, emph_ease="OutCubic", overshoot=None,
        scroll_ms=480, scroll_ease="OutCubic", scroll_overshoot=None,
        near=0.72, step=0.06, floor=0.40, future=None, mode="none", lead=0.15,
    ),
    "karaoke": dict(
        label="Karaoke",
        hint="Colour sweeps across each line as it is sung, and stays on lines already sung.",
        scale=1.14, emph_ms=240, emph_ease="OutCubic", overshoot=None,
        scroll_ms=480, scroll_ease="OutCubic", scroll_overshoot=None,
        near=0.60, step=0.06, floor=0.32, future=None, mode="sweep", lead=0.10,
    ),
    "typewriter": dict(
        label="Typewriter",
        hint="Each line types itself out as it starts. Upcoming lines stay hidden.",
        scale=1.12, emph_ms=200, emph_ease="OutCubic", overshoot=None,
        scroll_ms=420, scroll_ease="OutCubic", scroll_overshoot=None,
        near=0.55, step=0.07, floor=0.28, future=0.0, mode="type", lead=0.0,
    ),
    "pop": dict(
        label="Pop",
        hint="Each new line bounces in with a little overshoot.",
        scale=1.30, emph_ms=560, emph_ease="OutBack", overshoot=3.4,
        scroll_ms=560, scroll_ease="OutBack", scroll_overshoot=0.9,
        near=0.72, step=0.06, floor=0.40, future=None, mode="none", lead=0.15,
    ),
    "spotlight": dict(
        label="Spotlight",
        hint="Only the current line stands out; everything else fades into the background.",
        scale=1.26, emph_ms=340, emph_ease="OutCubic", overshoot=None,
        scroll_ms=520, scroll_ease="OutCubic", scroll_overshoot=None,
        near=0.24, step=0.06, floor=0.09, future=None, mode="none", lead=0.15,
    ),
    "instant": dict(
        label="Instant",
        hint="No animation: lines switch and scroll immediately.",
        scale=1.22, emph_ms=0, emph_ease="Linear", overshoot=None,
        scroll_ms=0, scroll_ease="Linear", scroll_overshoot=None,
        near=0.72, step=0.06, floor=0.40, future=None, mode="none", lead=0.0,
    ),
}


def normalize(key) -> str:
    return key if isinstance(key, str) and key in STYLES else DEFAULT_STYLE


def get(key) -> dict:
    return STYLES[normalize(key)]


def line_alpha(style: dict, distance: int, upcoming: bool) -> float:
    """Text opacity of a line `distance` lines from the current one (0 = current)."""
    if distance <= 0:
        return 1.0
    if upcoming and style["future"] is not None:
        return style["future"]
    return max(style["floor"], style["near"] - style["step"] * (distance - 1))
