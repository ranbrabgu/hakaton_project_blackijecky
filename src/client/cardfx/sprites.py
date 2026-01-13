# sprites.py
from __future__ import annotations
from .terminal import Sprite

def card_face(rank: str, suit: str, w: int = 11, h: int = 7) -> Sprite:
    w = max(w, 9)
    h = max(h, 7)
    inner_w = w - 2

    top = "┌" + "─" * inner_w + "┐"
    bot = "└" + "─" * inner_w + "┘"

    r = rank[:2]
    tl = (r + suit).ljust(inner_w)
    br = (r + suit).rjust(inner_w)

    lines = [top, "│" + tl + "│"]
    middle_rows = h - 4
    mid_symbol = suit.center(inner_w)
    for i in range(middle_rows):
        lines.append("│" + (mid_symbol if i == middle_rows // 2 else " " * inner_w) + "│")
    lines.append("│" + br + "│")
    lines.append(bot)
    return Sprite(lines)

def card_back(w: int = 11, h: int = 7) -> Sprite:
    w = max(w, 9)
    h = max(h, 7)
    inner_w = w - 2

    top = "┌" + "─" * inner_w + "┐"
    bot = "└" + "─" * inner_w + "┘"

    lines = [top]
    for r in range(h - 2):
        pattern = (("░▒" if r % 2 == 0 else "▒░") * (inner_w // 2 + 3))[:inner_w]
        lines.append("│" + pattern + "│")
    lines.append(bot)
    return Sprite(lines)

def fold_mix(front: Sprite, back: Sprite, mix_col: int) -> Sprite:
    """
    Left part front, right part back.
    mix_col = number of columns kept from front (0..w).
    """
    out = []
    for f, b in zip(front.lines, back.lines):
        w = min(len(f), len(b))
        m = max(0, min(mix_col, w))
        out.append(f[:m] + b[m:w])
    return Sprite(out)

def shoe(w: int = 24, h: int = 9) -> Sprite:
    """
    Simple card shoe (box) you can place on the table.
    """
    w = max(w, 18)
    h = max(h, 7)
    inner_w = w - 2

    top = "╔" + "═" * inner_w + "╗"
    bot = "╚" + "═" * inner_w + "╝"

    lines = [top]
    # a little "mouth" opening on the left side
    for r in range(h - 2):
        if r == 2:
            mouth = " " * (inner_w // 3) + "┌─────┐" + " " * (inner_w - (inner_w // 3) - 7)
            lines.append("║" + mouth[:inner_w] + "║")
        elif r == 3:
            mouth = " " * (inner_w // 3) + "│     │" + " " * (inner_w - (inner_w // 3) - 7)
            lines.append("║" + mouth[:inner_w] + "║")
        elif r == 4:
            mouth = " " * (inner_w // 3) + "└─────┘" + " " * (inner_w - (inner_w // 3) - 7)
            lines.append("║" + mouth[:inner_w] + "║")
        else:
            lines.append("║" + (" " * inner_w) + "║")
    lines.append(bot)
    return Sprite(lines)