# animations/intro_shuffle.py
from __future__ import annotations
import math
import time
import random
from dataclasses import dataclass
from typing import List, Tuple, Dict

from terminal import TerminalRenderer, Sprite, Style, RESET, BOLD, RED_BOLD
from sprites import card_face, card_back, fold_mix
from cards import Deck, Card

def clamp01(t: float) -> float:
    return max(0.0, min(1.0, t))

def smoothstep(t: float) -> float:
    t = clamp01(t)
    return t * t * (3 - 2 * t)

def ease_in_out_sine(t: float) -> float:
    t = clamp01(t)
    return -(math.cos(math.pi * t) - 1) / 2

def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t

def overlap_area(ax0, ay0, bx0, by0, w, h) -> int:
    ax1, ay1 = ax0 + w, ay0 + h
    bx1, by1 = bx0 + w, by0 + h
    ox = max(0, min(ax1, bx1) - max(ax0, bx0))
    oy = max(0, min(ay1, by1) - max(ay0, by0))
    return ox * oy

@dataclass
class IntroShuffleConfig:
    duration_s: float = 7.4
    fps: int = 55
    visible_cards: int = 26
    passes: int = 3

    # stage timings (normalized)
    A_end: float = 0.64
    B_end: float = 0.82
    C_end: float = 0.82  # you chose "no stage C" by setting equal
    # D is the rest

    # cascade flip
    cascade_gap: float = 0.018
    cascade_flip_dur: float = 0.16

class IntroShuffle:
    def __init__(self, cfg: IntroShuffleConfig):
        self.cfg = cfg

    def _style_for(self, card: Card) -> Style:
        return RED_BOLD if card.is_red else RESET

    def run(self, r: TerminalRenderer) -> None:
        term_w, term_h = r.get_size()

        # size based on terminal
        card_w, card_h = (11, 7)
        if term_w < 70 or term_h < 18:
            card_w, card_h = (9, 7)
        if term_w < 50 or term_h < 14:
            card_w, card_h = (9, 5)

        cx = term_w // 2
        cy = term_h // 2
        base_y = max(0, cy - card_h // 2)

        pile_offset = max(12, term_w // 4)
        left_x0 = cx - pile_offset
        right_x0 = cx + pile_offset

        # unique visible subset
        deck = Deck(seed=time.time_ns())
        visible = deck.take(min(self.cfg.visible_cards, 52))
        n = len(visible)

        # two groups = indices
        idxs = list(range(n))
        random.shuffle(idxs)
        left_group = idxs[: n // 2]
        right_group = idxs[n // 2 :]

        phases = [random.random() * 2 * math.pi for _ in range(n)]
        depths = [random.randint(0, 2) for _ in range(n)]
        cur_x = [0.0] * n
        cur_y = [0.0] * n

        back = card_back(card_w, card_h)

        # overlap-swap gating (swap whenever new strong-overlap pair appears)
        overlap_active = False
        last_pair = None

        # final full 52 deck for cascade flip
        full_deck = Deck(seed=time.time_ns())
        all52 = full_deck.take(52)
        faces52 = [card_face(c.rank, c.suit, card_w, card_h) for c in all52]

        start = time.time()
        dt = 1.0 / max(1, self.cfg.fps)

        while True:
            t = time.time() - start
            if t >= self.cfg.duration_s:
                break
            u = t / self.cfg.duration_s

            if r.clear_each_frame:
                r.clear()

            # title
            title = "SHUFFLING"
            r.move(max(1, base_y - 2) + 1, max(1, cx - len(title)//2) + 1)
            print(BOLD.prefix + title + BOLD.suffix, end="")

            # Stage A: crossing passes
            if u < self.cfg.A_end:
                a = u / self.cfg.A_end
                total = a * (self.cfg.passes - 0.5)
                pass_idx = int(total)
                frac = total - pass_idx

                if pass_idx % 2 == 0:
                    left_from, left_to = left_x0, right_x0
                    right_from, right_to = right_x0, left_x0
                else:
                    left_from, left_to = right_x0, left_x0
                    right_from, right_to = left_x0, right_x0

                p = ease_in_out_sine(frac)
                intensity = max(0.0, math.sin(math.pi * frac))
                fan_scale = (1.1 if card_w == 9 else 1.4) + 2.5 * intensity

                def fan_offset(pos: int, size: int) -> float:
                    if size <= 1:
                        return 0.0
                    center = (size - 1) / 2
                    return (pos - center) * fan_scale

                items = []
                for k, i in enumerate(left_group):  items.append(("L", k, i))
                for k, i in enumerate(right_group): items.append(("R", k, i))
                items.sort(key=lambda it: depths[it[2]])

                rect_pos = {}
                for side, k, i in items:
                    if side == "L":
                        x_base = lerp(left_from, left_to, p)
                        fan = fan_offset(k, len(left_group))
                        dir_sign = 1
                    else:
                        x_base = lerp(right_from, right_to, p)
                        fan = fan_offset(k, len(right_group))
                        dir_sign = -1

                    weave = math.sin(t * 9.5 + phases[i]) * (0.6 + 1.6 * intensity)
                    arc = -abs(math.sin(math.pi * p)) * (0.2 + 1.0 * intensity)

                    x = x_base + fan + weave * dir_sign
                    y = base_y + depths[i] + arc

                    cur_x[i], cur_y[i] = x, y
                    rect_pos[i] = (int(round(x - card_w // 2)), int(round(y)))

                # strong overlap => swap every "new" full-overlap event
                best = None
                best_area = 0
                need = int(card_w * card_h * 0.80)
                for li in left_group:
                    ax0, ay0 = rect_pos[li]
                    for ri in right_group:
                        bx0, by0 = rect_pos[ri]
                        area = overlap_area(ax0, ay0, bx0, by0, card_w, card_h)
                        if area >= need and area > best_area:
                            best_area = area
                            best = (li, ri)

                if best:
                    if (not overlap_active) or (best != last_pair):
                        li, ri = best
                        lpos = left_group.index(li)
                        rpos = right_group.index(ri)
                        left_group[lpos], right_group[rpos] = right_group[rpos], left_group[lpos]
                        overlap_active = True
                        last_pair = best
                else:
                    overlap_active = False
                    last_pair = None

                # draw
                items = []
                for k, i in enumerate(left_group):  items.append(("L", k, i))
                for k, i in enumerate(right_group): items.append(("R", k, i))
                items.sort(key=lambda it: depths[it[2]])

                for _, _, i in items:
                    c = visible[i]
                    spr = card_face(c.rank, c.suit, card_w, card_h)
                    r.draw_sprite(spr, int(round(cur_x[i] - card_w // 2)), int(round(cur_y[i])),
                                  term_w, term_h, style=self._style_for(c))

                r.flush()
                time.sleep(dt)
                continue

            # merged order for stacking
            merged = left_group + right_group
            merged_sorted = sorted(merged, key=lambda i: (depths[i], i))
            draw_order = sorted(merged_sorted, key=lambda i: depths[i])

            slot_offsets = [(0,0), (1,0), (0,1), (1,1), (0,0), (1,0)]
            def slot_for(pos: int) -> Tuple[int, int]:
                ox, oy = slot_offsets[pos % len(slot_offsets)]
                return cx + ox, base_y + oy

            # Stage B: compress faces into deck
            if u < self.cfg.B_end:
                b = (u - self.cfg.A_end) / max(1e-9, (self.cfg.B_end - self.cfg.A_end))
                b_e = smoothstep(b)
                for pos, i in enumerate(draw_order):
                    tx, ty = slot_for(pos)
                    x = lerp(cur_x[i], tx, b_e)
                    y = lerp(cur_y[i], ty, b_e)
                    x += math.sin(t * 7.0 + phases[i]) * (0.18 * (1.0 - b_e))
                    cur_x[i], cur_y[i] = x, y

                    c = visible[i]
                    spr = card_face(c.rank, c.suit, card_w, card_h)
                    r.draw_sprite(spr, int(round(x - card_w // 2)), int(round(y)), term_w, term_h,
                                  style=self._style_for(c))

                r.flush()
                time.sleep(dt)
                continue

            # Stage D: cascade fold-flip all 52 (front->back across width)
            # You set C_end == B_end => flip starts immediately after sorting.
            d = (u - self.cfg.B_end) / max(1e-9, (1.0 - self.cfg.B_end))
            stage_time = d * (self.cfg.duration_s * (1.0 - self.cfg.B_end))

            deck_x = cx - card_w // 2
            deck_y = base_y

            # Draw bottom->top so top card is visible
            offsets = [(0,0), (1,0), (0,1), (1,1), (0,0), (1,0)]

            for layer in range(52 - 1, -1, -1):
                ox, oy = offsets[layer % len(offsets)]
                x = deck_x + ox
                y = deck_y + oy

                local = stage_time - (layer * self.cfg.cascade_gap)
                p = clamp01(local / self.cfg.cascade_flip_dur)

                if p <= 0.0:
                    spr = faces52[layer]
                elif p >= 1.0:
                    spr = back
                else:
                    w = faces52[layer].w
                    mix_col = int(round(w * (1.0 - ease_in_out_sine(p))))
                    spr = fold_mix(faces52[layer], back, mix_col)

                r.draw_sprite(spr, x, y, term_w, term_h, style=RESET)

            if d > 0.92:
                msg = "READY"
                r.move(min(term_h, deck_y + card_h + 2) + 1, max(1, cx - len(msg)//2) + 1)
                print(BOLD.prefix + msg + BOLD.suffix, end="")

            r.flush()
            time.sleep(dt)