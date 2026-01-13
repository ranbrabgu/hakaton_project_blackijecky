# terminal.py
from __future__ import annotations
import sys
from dataclasses import dataclass
from typing import List, Tuple, Optional

CSI = "\033["

@dataclass
class Style:
    prefix: str = ""
    suffix: str = CSI + "0m"

# Basic styles (extend as needed)
RESET = Style(prefix=CSI + "0m")
BOLD = Style(prefix=CSI + "1m")

RED_BOLD = Style(prefix=CSI + "31m" + CSI + "1m")  # hearts/diamonds
DEFAULT = RESET

@dataclass
class Sprite:
    lines: List[str]

    @property
    def w(self) -> int:
        return max((len(s) for s in self.lines), default=0)

    @property
    def h(self) -> int:
        return len(self.lines)

class TerminalRenderer:
    def __init__(self, *, clear_each_frame: bool = True):
        self.clear_each_frame = clear_each_frame
        self._hidden_cursor = False

    def hide_cursor(self) -> None:
        if not self._hidden_cursor:
            sys.stdout.write(CSI + "?25l")
            self._hidden_cursor = True

    def show_cursor(self) -> None:
        if self._hidden_cursor:
            sys.stdout.write(CSI + "?25h")
            self._hidden_cursor = False

    def clear(self) -> None:
        # home + clear
        sys.stdout.write(CSI + "H" + CSI + "2J")

    def move(self, row_1: int, col_1: int) -> None:
        sys.stdout.write(f"{CSI}{row_1};{col_1}H")

    def flush(self) -> None:
        sys.stdout.flush()

    def get_size(self) -> Tuple[int, int]:
        # Lazy import to keep module small
        import shutil
        s = shutil.get_terminal_size(fallback=(80, 24))
        return s.columns, s.lines

    def begin(self) -> None:
        sys.stdout.write(CSI + "0m")
        self.hide_cursor()
        if self.clear_each_frame:
            self.clear()
        self.flush()

    def end(self) -> None:
        self.show_cursor()
        sys.stdout.write(CSI + "0m\n")
        self.flush()

    def draw_sprite(
        self,
        sprite: Sprite,
        x0: int,
        y0: int,
        term_w: int,
        term_h: int,
        style: Style = RESET,
    ) -> None:
        # x0,y0 are 0-based
        for row, line in enumerate(sprite.lines):
            yy = y0 + row
            if yy < 0 or yy >= term_h:
                continue

            # quick horizontal reject
            if x0 >= term_w or x0 + len(line) <= 0:
                continue

            start = 0
            end = len(line)
            xx = x0

            if xx < 0:
                start = -xx
                xx = 0
            if xx + (end - start) > term_w:
                end = start + (term_w - xx)
            if start >= end:
                continue

            self.move(yy + 1, xx + 1)
            sys.stdout.write(style.prefix + line[start:end] + style.suffix)