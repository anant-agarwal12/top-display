"""One lyric line, painted by hand.

The label always takes up the space of its resting size in the layout. The
current line is emphasised only while painting (a scale about its centre plus
brightness), so changing which line is current never re-flows the list. That is
what makes the scroll glide look smooth: nothing jumps at a line change.

It can also show progress through the line: a colour sweep (karaoke) or letters
appearing (typewriter). Both are drawn by clipping the same laid-out text.
"""
from typing import List, Optional

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QColor, QPainter, QTextLayout, QTextLine, QTextOption
from PySide6.QtWidgets import QLabel, QSizePolicy

import theme

_MAX_EMPHASIS = 1.7   # an overshooting ease may exceed 1.0; don't let a bad curve balloon the text


class LyricLabel(QLabel):
    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignCenter)
        self.setWordWrap(True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setFont(theme.lyric_font())
        self._scale_delta = 0.22      # extra scale at full emphasis
        self._peak = 1.22             # largest scale the line is ever painted at (incl. overshoot)
        self._side_margin = 0
        self._mode = "none"           # "none" | "sweep" | "type"
        self._emphasis = 0.0
        self._alpha = 0.6
        self._progress = 0.0
        self._accent = QColor(theme.ACCENT_SING)
        self._tl: Optional[QTextLayout] = None
        self._lines: List[QTextLine] = []
        self._layout_key = None
        self._text_height = 0.0

    # ---------- state ----------
    def configure(self, scale: float, mode: str, peak: Optional[float] = None):
        self._scale_delta = scale - 1.0
        self._peak = max(scale, peak or scale)
        self._mode = mode
        self._apply_margins()
        self.updateGeometry()
        self.update()

    # A widget can only paint inside its own rectangle, so a line painted
    # larger than its resting size would be clipped at the label's edges. The
    # text is therefore wrapped a little narrower than the label, and the label
    # asks the layout for a little extra height, so the largest it ever gets
    # (peak) still fits on every side.
    def _apply_margins(self):
        margin = int(self.width() * (1.0 - 1.0 / self._peak) / 2.0) + 3 if self._peak > 1.0 else 0
        if margin != self._side_margin:
            self._side_margin = margin
            self.setContentsMargins(margin, 0, margin, 0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_margins()

    def heightForWidth(self, width: int) -> int:
        base = super().heightForWidth(width)
        return base + int(round(base * (self._peak - 1.0))) + 6

    def sizeHint(self):
        hint = super().sizeHint()
        hint.setHeight(self.heightForWidth(hint.width()))
        return hint

    def minimumSizeHint(self):
        hint = super().minimumSizeHint()
        hint.setHeight(self.heightForWidth(max(hint.width(), self.width())))
        return hint

    def set_look(self, emphasis: float, alpha: float):
        emphasis = max(0.0, min(_MAX_EMPHASIS, emphasis))
        alpha = max(0.0, min(1.0, alpha))
        if abs(emphasis - self._emphasis) > 0.002 or abs(alpha - self._alpha) > 0.002:
            self._emphasis, self._alpha = emphasis, alpha
            self.update()

    def set_progress(self, progress: float):
        progress = max(0.0, min(1.0, progress))
        if progress != self._progress and (abs(progress - self._progress) > 0.002 or progress in (0.0, 1.0)):
            self._progress = progress
            self.update()

    @property
    def emphasis(self) -> float:
        return self._emphasis

    @property
    def alpha(self) -> float:
        return self._alpha

    @property
    def progress(self) -> float:
        return self._progress

    # ---------- text layout (same wrapping rules QLabel uses for its own size) ----------
    def _ensure_layout(self, width: int):
        key = (self.text(), self.font().key(), width)
        if key == self._layout_key and self._tl is not None:
            return
        self._layout_key = key
        tl = QTextLayout(self.text(), self.font())
        option = QTextOption(Qt.AlignHCenter)
        option.setWrapMode(QTextOption.WordWrap)
        tl.setTextOption(option)
        lines, y = [], 0.0
        tl.beginLayout()
        while True:
            line = tl.createLine()
            if not line.isValid():
                break
            line.setLineWidth(max(1, width))
            line.setPosition(QPointF(0.0, y))
            y += line.height()
            lines.append(line)
        tl.endLayout()
        self._tl, self._lines, self._text_height = tl, lines, y

    def _draw_lines(self, painter: QPainter, origin: QPointF, color: QColor, reveal: Optional[List[float]]):
        """Draws the text; `reveal[k]` (if given) limits line k to its first x pixels."""
        painter.setPen(color)
        for k, line in enumerate(self._lines):
            if reveal is not None:
                limit = reveal[k]
                if limit <= 0:
                    continue
                painter.save()
                painter.setClipRect(QRectF(
                    origin.x() + line.x() - 1, origin.y() + line.y() - 1,
                    limit + 2, line.height() + 2,
                ), Qt.IntersectClip)
                line.draw(painter, origin)
                painter.restore()
            else:
                line.draw(painter, origin)

    def _sweep_widths(self, fraction: float) -> List[float]:
        """Pixels of each line that the sweep has reached, spread over the whole text."""
        total = sum(line.naturalTextWidth() for line in self._lines) or 1.0
        remaining = fraction * total
        out = []
        for line in self._lines:
            width = line.naturalTextWidth()
            out.append(max(0.0, min(width, remaining)))
            remaining -= width
        return out

    def _typed_widths(self, fraction: float) -> List[float]:
        """Pixels of each line that the typed characters cover."""
        count = len(self.text())
        typed = int(round(fraction * count))
        out = []
        for line in self._lines:
            start, length = line.textStart(), line.textLength()
            n = max(0, min(length, typed - start))
            if n <= 0:
                out.append(0.0)
            elif n >= length:
                out.append(line.naturalTextWidth())
            else:
                x = line.cursorToX(start + n)
                x = x[0] if isinstance(x, tuple) else x
                out.append(max(0.0, x - line.x()))
        return out

    # ---------- painting ----------
    def paintEvent(self, event):
        rect = QRectF(self.contentsRect())
        self._ensure_layout(int(rect.width()))
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)

        scale = 1.0 + self._scale_delta * self._emphasis
        centre = rect.center()
        painter.translate(centre)
        painter.scale(scale, scale)
        painter.translate(-centre)

        origin = QPointF(rect.left(), rect.top() + (rect.height() - self._text_height) / 2.0)
        base = theme.text_color(self._alpha)

        if self._mode == "type":
            if self._progress <= 0.0:
                return   # a line that has not started typing yet shows nothing
            reveal = None if self._progress >= 1.0 else self._typed_widths(self._progress)
            self._draw_lines(painter, origin, base, reveal)
            return

        self._draw_lines(painter, origin, base, None)
        if self._mode == "sweep" and self._progress > 0.0:
            fill = QColor(self._accent)
            fill.setAlphaF(max(self._alpha, 0.55))
            self._draw_lines(painter, origin, fill, self._sweep_widths(self._progress))
