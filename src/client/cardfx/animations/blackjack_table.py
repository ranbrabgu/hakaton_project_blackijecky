# cardfx/animations/blackjack_table.py
from __future__ import annotations

import time
import math
from dataclasses import dataclass
from typing import List, Tuple, Literal

from ..terminal import TerminalRenderer, RESET, BOLD, RED_BOLD
from ..sprites import card_back, card_face, shoe


# ---------- small math helpers ----------
def clamp01(t: float) -> float:
    return max(0.0, min(1.0, t))


def smoothstep(t: float) -> float:
    t = clamp01(t)
    return t * t * (3.0 - 2.0 * t)


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def ease_in_out_sine(t: float) -> float:
    t = clamp01(t)
    return -(math.cos(math.pi * t) - 1) / 2


def suit_style(suit: str):
    # Hearts/diamonds red; spades/clubs default
    return RED_BOLD if suit in ("♥", "♦") else RESET


# ---------- scene config ----------
@dataclass
class BlackjackTableConfig:
    fps: int = 60

    # Deal animation duration (seconds)
    deal_dur: float = 0.55

    # spacing between cards in a hand
    gap_x: int = 2

    # shoe sprite size
    shoe_w: int = 24
    shoe_h: int = 9

    # layout paddings
    left_margin: int = 2
    right_margin: int = 2
    top_margin: int = 1
    bottom_margin: int = 1


# ---------- persistent table ----------
class BlackjackTable:
    """
    Persistent blackjack table scene.

    - dealer hand is drawn near the top
    - player hand is drawn near the bottom
    - shoe sits on the right side

    Public API:
      - reset()
      - render(prompt="Hit or Stand?")
      - deal_card(who, rank, suit, prompt="Hit or Stand?")

    Notes:
      - Hands persist until reset().
      - deal_card animates the card from the shoe mouth to the next available slot.
      - All normal draws are face-up.
      - First dealer draw auto-creates a facedown hole card.
      - Second dealer draw reveals (flips) the hole card.
    """

    def __init__(self, cfg: BlackjackTableConfig = BlackjackTableConfig()):
        self.cfg = cfg
        self.dealer_hand: List[Tuple[str, str, bool]] = []  # (rank, suit, is_face_down)
        self.player_hand: List[Tuple[str, str, bool]] = []  # always face_up (False)
        self._permanent_prompt: str | None = None
        self._temporary_prompt: str | None = None

    # ---------- state ----------
    def reset(self) -> None:
        self.dealer_hand.clear()
        self.player_hand.clear()

    # ---------- layout ----------
    def _choose_card_size(self, term_w: int, term_h: int) -> Tuple[int, int]:
        card_w, card_h = (11, 7)
        if term_w < 70 or term_h < 18:
            card_w, card_h = (9, 7)
        if term_w < 50 or term_h < 14:
            card_w, card_h = (9, 5)
        return card_w, card_h

    def _layout(self, r: TerminalRenderer, card_w: int, card_h: int):
        term_w, term_h = r.get_size()

        shoe_spr = shoe(w=self.cfg.shoe_w, h=self.cfg.shoe_h)

        # Place shoe on the right side, centered vertically
        shoe_x = max(0, term_w - shoe_spr.w - self.cfg.right_margin)
        shoe_y = max(0, (term_h // 2) - (shoe_spr.h // 2))

        # Hands left side region ends before shoe
        hand_right_limit = max(0, shoe_x - 2)
        slot_w = card_w + self.cfg.gap_x

        # Dealer near top, player near bottom
        dealer_y = max(self.cfg.top_margin + 1, shoe_y - card_h - 2)
        # Player near bottom (below the shoe)
        player_y = min(term_h - card_h - self.cfg.bottom_margin, shoe_y + shoe_spr.h + 1)

        dealer_x0 = self.cfg.left_margin
        player_x0 = self.cfg.left_margin

        # Shoe "ready card" source for dealing: protruding ~half a card out of the shoe.
        # We draw the card first and then the shoe on top, so the overlapping part is hidden.
        src_x = shoe_x - (card_w // 2)          # half outside to the left of the shoe
        src_y = shoe_y + (shoe_spr.h // 2) - (card_h // 2)

        return {
            "term_w": term_w,
            "term_h": term_h,
            "shoe_spr": shoe_spr,
            "shoe_x": shoe_x,
            "shoe_y": shoe_y,
            "hand_right_limit": hand_right_limit,
            "slot_w": slot_w,
            "dealer_x0": dealer_x0,
            "dealer_y": dealer_y,
            "player_x0": player_x0,
            "player_y": player_y,
            "src_x": int(src_x),
            "src_y": int(src_y),
        }

    def _slot_pos(self, layout, who: Literal["dealer", "player"], index: int) -> Tuple[int, int]:
        x0 = layout["dealer_x0"] if who == "dealer" else layout["player_x0"]
        y = layout["dealer_y"] if who == "dealer" else layout["player_y"]
        x = x0 + index * layout["slot_w"]

        # keep within left-side region (avoid overlapping shoe)
        if x + 1 >= layout["hand_right_limit"]:
            x = max(0, layout["hand_right_limit"] - 12)  # fallback near the limit
        return int(x), int(y)

    def _active_prompt(self) -> str | None:
        return self._temporary_prompt if self._temporary_prompt is not None else self._permanent_prompt

    # ---------- rendering ----------
    def render(self, r: TerminalRenderer, *, show_shoe_card: bool = True) -> None:
        term_w, term_h = r.get_size()
        card_w, card_h = self._choose_card_size(term_w, term_h)

        back = card_back(card_w, card_h)
        layout = self._layout(r, card_w, card_h)

        if r.clear_each_frame:
            r.clear()

        # Labels
        r.move(max(1, layout["dealer_y"] - 1) + 1, self.cfg.left_margin + 1)
        print(BOLD.prefix + "Dealer" + BOLD.suffix, end="")

        r.move(max(1, layout["player_y"] - 1) + 1, self.cfg.left_margin + 1)
        print(BOLD.prefix + "You" + BOLD.suffix, end="")

        # Dealer hand (persisted)
        for i, (rank, suit, is_face_down) in enumerate(self.dealer_hand):
            x, y = self._slot_pos(layout, "dealer", i)
            if is_face_down:
                r.draw_sprite(back, x, y, layout["term_w"], layout["term_h"], style=RESET)
            else:
                spr = card_face(rank, suit, card_w, card_h)
                r.draw_sprite(spr, x, y, layout["term_w"], layout["term_h"], style=suit_style(suit))

        # Player hand (persisted)
        for i, (rank, suit, is_face_down) in enumerate(self.player_hand):
            x, y = self._slot_pos(layout, "player", i)
            if is_face_down:
                r.draw_sprite(back, x, y, layout["term_w"], layout["term_h"], style=RESET)
            else:
                spr = card_face(rank, suit, card_w, card_h)
                r.draw_sprite(spr, x, y, layout["term_w"], layout["term_h"], style=suit_style(suit))

        # Ready card (drawn BEHIND the shoe so it looks like it's coming from inside)
        if show_shoe_card:
            r.draw_sprite(back, layout["src_x"], layout["src_y"], layout["term_w"], layout["term_h"], style=RESET)

        # Shoe drawn on TOP to occlude/hide part of the ready card
        r.draw_sprite(layout["shoe_spr"], layout["shoe_x"], layout["shoe_y"], layout["term_w"], layout["term_h"], style=RESET)

        # Prompt (temporary overrides permanent)
        prompt_text = self._active_prompt()
        if prompt_text:
            px = max(1, (term_w // 2) - (len(prompt_text) // 2)) + 1
            r.move(term_h, px)
            print(BOLD.prefix + prompt_text + BOLD.suffix, end="")

        r.flush()

    # ---------- animation ----------
    def deal_card(
        self,
        r: TerminalRenderer,
        who: Literal["dealer", "player"],
        rank: str,
        suit: str,
    ) -> None:
        """
        Deal logic:

        - Player: always draws a NEW face-up card from the shoe to the next slot.
        - Dealer:
            * If dealer has 0 cards: draw face-up card to slot 0, then auto-draw a facedown hole card to slot 1.
            * If dealer hole card exists and is still facedown: this call REVEALS it by flipping in-place (no new draw).
            * Otherwise: draw a NEW face-up card from the shoe to the next slot.

        The hands persist until reset().
        """
        # Temporary prompts last only until the next animation starts
        self._temporary_prompt = None

        term_w, term_h = r.get_size()
        card_w, card_h = self._choose_card_size(term_w, term_h)

        back = card_back(card_w, card_h)
        layout = self._layout(r, card_w, card_h)

        src_x, src_y = layout["src_x"], layout["src_y"]

        def _animate_move_to_slot(dst_index_to_use: int, sprite_to_draw, style_to_use) -> None:
            dst_x_to_use, dst_y_to_use = self._slot_pos(layout, who, dst_index_to_use)

            start = time.time()
            dt = 1.0 / max(1, self.cfg.fps)

            while True:
                t = time.time() - start
                p = smoothstep(clamp01(t / max(1e-6, self.cfg.deal_dur)))

                x = int(round(lerp(src_x, dst_x_to_use, p)))
                y = int(round(lerp(src_y, dst_y_to_use, p)))

                # draw persistent scene
                self.render(r, show_shoe_card=False)

                # draw moving card on top
                r.draw_sprite(sprite_to_draw, x, y, layout["term_w"], layout["term_h"], style=style_to_use)
                r.flush()

                if p >= 1.0:
                    break
                time.sleep(dt)

        def _animate_flip_in_place(x: int, y: int, from_sprite, to_sprite, to_style) -> None:
            """
            Fold-style flip across width:
            left part shows the 'to' side gradually as the fold progresses.
            """
            start = time.time()
            dt = 1.0 / max(1, self.cfg.fps)
            w = to_sprite.w

            while True:
                t = time.time() - start
                p = clamp01(t / max(1e-6, self.cfg.deal_dur))
                p = ease_in_out_sine(p)

                # mix_col goes 0..w (more of the 'to' side as p increases)
                mix_col = int(round(w * p))
                mixed_lines = []
                for f_line, t_line in zip(from_sprite.lines, to_sprite.lines):
                    ww = min(len(f_line), len(t_line))
                    m = max(0, min(mix_col, ww))
                    mixed_lines.append(t_line[:m] + f_line[m:ww])
                mixed = type(to_sprite)(mixed_lines)  # Sprite

                self.render(r, show_shoe_card=True)
                # draw mixed card on top
                r.draw_sprite(mixed, x, y, layout["term_w"], layout["term_h"], style=to_style)
                r.flush()

                if p >= 1.0:
                    break
                time.sleep(dt)

        # -------------------------
        # PLAYER: always draw new face-up
        # -------------------------
        if who == "player":
            dst_index = len(self.player_hand)
            face = card_face(rank, suit, card_w, card_h)
            _animate_move_to_slot(dst_index, face, suit_style(suit))
            self.player_hand.append((rank, suit, False))
            self.render(r)
            return

        # -------------------------
        # DEALER logic
        # -------------------------
        # First dealer draw: draw face-up + auto hole facedown
        if len(self.dealer_hand) == 0:
            # slot 0 face-up
            face0 = card_face(rank, suit, card_w, card_h)
            _animate_move_to_slot(0, face0, suit_style(suit))
            self.dealer_hand.append((rank, suit, False))

            # slot 1 hole facedown (unknown identity for now)
            _animate_move_to_slot(1, back, RESET)
            self.dealer_hand.append(("?", "?", True))

            self.render(r)
            return

        # If hole exists and is still facedown -> reveal it by flipping in-place (this is the "second dealer draw")
        if len(self.dealer_hand) >= 2 and self.dealer_hand[1][2] is True:
            # flip the hole at slot 1: back -> face(rank,suit)
            x1, y1 = self._slot_pos(layout, "dealer", 1)
            to_face = card_face(rank, suit, card_w, card_h)
            _animate_flip_in_place(x1, y1, back, to_face, suit_style(suit))
            # update stored hole
            self.dealer_hand[1] = (rank, suit, False)
            self.render(r)
            return

        # Otherwise: normal dealer hit - draw new face-up card to next slot
        dst_index = len(self.dealer_hand)
        faceN = card_face(rank, suit, card_w, card_h)
        _animate_move_to_slot(dst_index, faceN, suit_style(suit))
        self.dealer_hand.append((rank, suit, False))
        self.render(r)

    def set_permanent_prompt(self, r: TerminalRenderer, text: str | None) -> None:
        """
        Set a permanent prompt (persists across animations). If text is None or empty, clears it.
        Setting a permanent prompt clears any temporary prompt.
        """
        if not text:
            self._permanent_prompt = None
        else:
            self._permanent_prompt = text
        self._temporary_prompt = None
        self.render(r, show_shoe_card=True)

    def set_temporary_prompt(self, r: TerminalRenderer, text: str | None) -> None:
        """
        Set a temporary prompt (shown immediately and during the *current* animation),
        and cleared automatically when the next animation starts.
        If text is None or empty, clears the temporary prompt.
        """
        if not text:
            self._temporary_prompt = None
        else:
            self._temporary_prompt = text
        # temporary replaces any previous temporary; permanent remains underneath
        self.render(r, show_shoe_card=True)

    def display_prompt(self, r: TerminalRenderer, text: str) -> None:
        """
        Convenience wrapper: set a TEMPORARY prompt and redraw.
        """
        self.set_temporary_prompt(r, text)
