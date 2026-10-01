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

    @staticmethod
    def _extent(line: QTextLine):
        """(left, right) x of the text on this line, alignment included.

        QTextLine.x() is NOT that: for centred text it stays 0 and Qt adds the centring
        offset only when drawing. cursorToX() does include it."""
        left = line.cursorToX(line.textStart())
        right = line.cursorToX(line.textStart() + line.textLength())
        left = left[0] if isinstance(left, tuple) else left
        right = right[0] if isinstance(right, tuple) else right
        return left, right

    def _draw_lines(self, painter: QPainter, origin: QPointF, color: QColor,
                    reveal: Optional[List[float]], beyond: bool = False):
        """Draws the text. `reveal[k]` (if given) is the x, in layout coordinates, that line k
        is cut at: by default only the part left of it is drawn; with `beyond=True` only the
        part right of it. (The two halves meet at the same x, so a glyph is drawn in exactly
        one colour, with no fringe of the other.)"""
        painter.setPen(color)
        for k, line in enumerate(self._lines):
            if reveal is None:
                line.draw(painter, origin)
                continue
            limit = reveal[k] + 2
            left, right = self._extent(line)
            if beyond:
                if limit <= left:                     # nothing revealed yet: the whole line
                    line.draw(painter, origin)
                    continue
                if limit >= right + 2:                # everything revealed: nothing left to draw
                    continue
                clip = QRectF(origin.x() + limit, origin.y() + line.y() - 1,
                              right - limit + 8, line.height() + 2)
            else:
                if limit <= left + 2:
                    continue
                clip = QRectF(origin.x() + left - 4, origin.y() + line.y() - 1,
                              limit - left + 4, line.height() + 2)
            painter.save()
            painter.setClipRect(clip, Qt.IntersectClip)
            line.draw(painter, origin)
            painter.restore()

    def _sweep_limits(self, fraction: float) -> List[float]:
        """For each line, the x the sweep has reached: spread over all lines by their real widths."""
        extents = [self._extent(line) for line in self._lines]
        total = sum(right - left for left, right in extents) or 1.0
        remaining = fraction * total
        limits = []
        for left, right in extents:
            width = right - left
            limits.append(left + max(0.0, min(width, remaining)))
            remaining -= width
        return limits

    def _typed_limits(self, fraction: float) -> List[float]:
        """For each line, the x its typed characters reach."""
        typed = int(round(fraction * len(self.text())))
        limits = []
        for line in self._lines:
            start, length = line.textStart(), line.textLength()
            n = max(0, min(length, typed - start))
            left, right = self._extent(line)
            if n <= 0:
                limits.append(left)
            elif n >= length:
                limits.append(right)
            else:
                x = line.cursorToX(start + n)
                limits.append(x[0] if isinstance(x, tuple) else x)
        return limits

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
            reveal = None if self._progress >= 1.0 else self._typed_limits(self._progress)
            self._draw_lines(painter, origin, base, reveal)
            return

        if self._mode == "sweep" and self._progress > 0.0:
            fill = QColor(self._accent)
            fill.setAlphaF(max(self._alpha, 0.55))
            if self._progress >= 0.999:
                # A finished line is just the fill colour, drawn with no clipping at all, so
                # not one pixel can be missed.
                self._draw_lines(painter, origin, fill, None)
            else:
                limits = self._sweep_limits(self._progress)
                self._draw_lines(painter, origin, fill, limits)                  # the part sung so far
                self._draw_lines(painter, origin, base, limits, beyond=True)     # the part still to come
            return
        self._draw_lines(painter, origin, base, None)
