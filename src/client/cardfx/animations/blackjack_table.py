# cardfx/animations/blackjack_table.py
from __future__ import annotations

import time
import math
import random
import os
import subprocess
import sys
import shutil
from dataclasses import dataclass
from typing import List, Tuple, Literal, Optional

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


# ---------- overlay colors (ANSI) ----------
ANSI_RESET = "\x1b[0m"
ANSI_BOLD_GREEN = "\x1b[1;32m"
ANSI_BOLD_RED = "\x1b[1;31m"
ANSI_BLOOD_RED = "\x1b[38;5;88m"   # deep blood red (256-color)
ANSI_BOLD_YELLOW = "\x1b[1;33m"
ANSI_BOLD_CYAN = "\x1b[1;36m"
ANSI_DIM_BLUE = "\x1b[2;34m"
ANSI_DIM_CYAN = "\x1b[2;36m"
ANSI_DIM_WHITE = "\x1b[2;37m"

# A few bright/confetti colors (foreground)
CONFETTI_COLORS = [
    "\x1b[1;31m",  # red
    "\x1b[1;32m",  # green
    "\x1b[1;33m",  # yellow
    "\x1b[1;34m",  # blue
    "\x1b[1;35m",  # magenta
    "\x1b[1;36m",  # cyan
    "\x1b[1;37m",  # white
]
CONFETTI_CHARS = ["*", "+", "•", "·", "x", "o", "░", "▒", "▓"]

# "Sad" particles (rain/tears)
SAD_CHARS = ["'", "’", ".", "·", ":", ";", "|", "╷", "╵"]
SAD_COLORS = [ANSI_DIM_BLUE, ANSI_DIM_CYAN, ANSI_DIM_WHITE]

# "Blood" particles (thick drips)
BLOOD_CHARS = ["█", "▓", "▒", "░", "▄", "▌"]
BLOOD_COLORS = [ANSI_BLOOD_RED, "\x1b[38;5;124m", "\x1b[38;5;160m"]  # deep->bright reds


# ---------- scene config ----------
@dataclass
class BlackjackTableConfig:
    fps: int = 60

    # sound effects
    enable_sfx: bool = True
    sfx_volume: float = 0.9  # used for afplay on macOS

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
        self._bg_audio_proc: subprocess.Popen | None = None
    def _sounds_dir(self) -> str:
        # cardfx/sounds directory (sibling of animations/)
        return os.path.join(os.path.dirname(os.path.dirname(__file__)), "sounds")

    def _stop_bg_audio(self) -> None:
        proc = self._bg_audio_proc
        self._bg_audio_proc = None
        if proc is None:
            return
        try:
            proc.terminate()
        except Exception:
            pass

    def _play_bg_mp3(self, filename: str) -> None:
        """
        Play an MP3 in the background during an overlay.
        macOS only (afplay). Safe no-op on other platforms or if file missing.
        """
        # stop any previous background audio
        self._stop_bg_audio()

        if sys.platform != "darwin":
            return

        sounds_dir = self._sounds_dir()
        path = os.path.join(sounds_dir, filename)

        # Be robust to case differences + minor filename variations
        if not os.path.exists(path):
            try:
                wanted = filename.lower()
                base_wanted = os.path.splitext(wanted)[0]
                candidates = []
                for fn in os.listdir(sounds_dir):
                    if not fn.lower().endswith(".mp3"):
                        continue
                    low = fn.lower()
                    if low == wanted:
                        candidates = [fn]
                        break
                    # allow e.g. "Loser (1).mp3" / "loser_copy.mp3" etc.
                    if os.path.splitext(low)[0].startswith(base_wanted):
                        candidates.append(fn)
                if candidates:
                    # pick the shortest (most likely the canonical one)
                    best = sorted(candidates, key=len)[0]
                    path = os.path.join(sounds_dir, best)
            except Exception:
                pass

        if not os.path.exists(path):
            return

        try:
            # First attempt: respect configured volume.
            proc = subprocess.Popen(
                ["afplay", "-v", str(self.cfg.sfx_volume), path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            # If afplay exits immediately (unsupported file/codec, device issue, etc.), try fallbacks.
            time.sleep(0.08)
            if proc.poll() is not None:
                proc2 = subprocess.Popen(
                    ["afplay", path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                time.sleep(0.08)
                if proc2.poll() is not None:
                    # Try ffplay (ffmpeg) if available
                    if shutil.which("ffplay"):
                        proc3 = subprocess.Popen(
                            ["ffplay", "-nodisp", "-autoexit", "-loglevel", "error", path],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                        )
                        self._bg_audio_proc = proc3
                        return

                    # Try mpg123 if available
                    if shutil.which("mpg123"):
                        proc4 = subprocess.Popen(
                            ["mpg123", "-q", path],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                        )
                        self._bg_audio_proc = proc4
                        return

                    self._bg_audio_proc = None
                    return

                proc = proc2

            self._bg_audio_proc = proc
        except Exception:
            self._bg_audio_proc = None

    # ---------- state ----------
    def reset(self) -> None:
        self.dealer_hand.clear()
        self.player_hand.clear()
        self._stop_bg_audio()

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

    def _sfx_bell(self) -> None:
        # Terminal bell (works in many terminals; harmless if disabled)
        try:
            sys.stdout.write("\a")
            sys.stdout.flush()
        except Exception:
            pass

    def _sfx_afplay(self, sound_name: str) -> None:
        """
        macOS: play /System/Library/Sounds/<sound_name>.aiff asynchronously.
        """
        try:
            path = f"/System/Library/Sounds/{sound_name}.aiff"
            if not os.path.exists(path):
                return
            # Non-blocking; ignore errors
            subprocess.Popen(
                ["afplay", "-v", str(self.cfg.sfx_volume), path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass

    def _sfx_say(self, text: str) -> None:
        """
        macOS: speak asynchronously using `say`.
        """
        try:
            if sys.platform != "darwin":
                return
            subprocess.Popen(
                ["say", text],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass

    def _sfx_say_blocking(self, text: str) -> None:
        """
        macOS: speak and BLOCK until finished (used when sequencing audio).
        """
        if sys.platform != "darwin":
            return
        try:
            subprocess.run(
                ["say", text],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        except Exception:
            pass

    def _sfx_afplay_first_available(self, names: list[str]) -> None:
        """
        macOS: try a list of /System/Library/Sounds/<name>.aiff and play the first that exists.
        """
        if sys.platform != "darwin":
            return
        for n in names:
            path = f"/System/Library/Sounds/{n}.aiff"
            if os.path.exists(path):
                self._sfx_afplay(n)
                return

    def _sfx_eeee_buzzer(self, duration: float = 1.1) -> None:
        """
        Long, annoying "EEEEEE" style buzzer (NOT TTS).
        We approximate a sustained tone by rapidly triggering short system beeps.

        - macOS: use AppleScript `beep` in a short loop (more "tone"-like than discrete sounds),
          and optionally layer a low system sound underneath.
        - Others: fall back to rapid terminal bell bursts.
        """
        end_t = time.time() + max(0.1, duration)

        if sys.platform == "darwin":
            # Optional low layer (doesn't block)
            if os.path.exists("/System/Library/Sounds/Basso.aiff"):
                self._sfx_afplay("Basso")

            # Rapid beeps to emulate a sustained buzzer
            while time.time() < end_t:
                try:
                    subprocess.Popen(
                        ["osascript", "-e", "beep 1"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                except Exception:
                    # fallback to terminal bell
                    self._sfx_bell()
                time.sleep(0.07)
            return

        # universal fallback: rapid terminal bell burst
        while time.time() < end_t:
            self._sfx_bell()
            time.sleep(0.04)

    def _celebrate_sfx(self, phase: str = "tick") -> None:
        """
        WIN SFX: TTS only (no beeps/afplay).
        Uses the existing text: "Woohoo! You win!"
        """
        if not getattr(self.cfg, "enable_sfx", True):
            return
        if sys.platform != "darwin":
            return
        if phase == "start":
            self._sfx_say("Woohoo! You win!")

    def _mock_sfx(self, phase: str = "tick") -> None:
        """
        LOSE SFX: TTS only (no beeps/afplay).
        Uses the existing text: "Ha ha ha ha! You lose."
        """
        if not getattr(self.cfg, "enable_sfx", True):
            return
        if sys.platform != "darwin":
            return
        if phase == "start":
            self._sfx_say("Ha ha ha ha! You lose.")

    def _busted_sfx(self, phase: str = "tick") -> None:
        """
        BUSTED SFX: TTS only.
        """
        if not getattr(self.cfg, "enable_sfx", True):
            return
        if sys.platform != "darwin":
            return
        if phase == "start":
            self._sfx_say("Busted.")

    def _tie_sfx(self, phase: str = "tick") -> None:
        """
        TIE SFX: TTS only.
        """
        if not getattr(self.cfg, "enable_sfx", True):
            return
        if sys.platform != "darwin":
            return
        if phase == "start":
            self._sfx_say("Tie.")

    def _big_win_patterns(self):
        # 7x7 bitmap patterns (1 = filled)
        W = [
            "1000001",
            "1000001",
            "1000001",
            "1001001",
            "1010101",
            "1100011",
            "1000001",
        ]
        I = [
            "1111111",
            "0011100",
            "0011100",
            "0011100",
            "0011100",
            "0011100",
            "1111111",
        ]
        N = [
            "1000001",
            "1100001",
            "1110001",
            "1011001",
            "1001101",
            "1000111",
            "1000001",
        ]
        return {"W": W, "I": I, "N": N}

    def _big_loser_patterns(self):
        # 7x7 bitmap patterns (1 = filled)
        L = [
            "1000000",
            "1000000",
            "1000000",
            "1000000",
            "1000000",
            "1000000",
            "1111111",
        ]
        O = [
            "0111110",
            "1100011",
            "1100011",
            "1100011",
            "1100011",
            "1100011",
            "0111110",
        ]
        S = [
            "0111110",
            "1100001",
            "1100000",
            "0111110",
            "0000011",
            "1000011",
            "0111110",
        ]
        E = [
            "1111111",
            "1000000",
            "1000000",
            "1111110",
            "1000000",
            "1000000",
            "1111111",
        ]
        R = [
            "1111110",
            "1000011",
            "1000011",
            "1111110",
            "1001100",
            "1000110",
            "1000011",
        ]
        return {"L": L, "O": O, "S": S, "E": E, "R": R}

    def _big_busted_patterns(self):
        # 7x7 bitmap patterns (1 = filled)
        B = [
            "1111110",
            "1000011",
            "1000011",
            "1111110",
            "1000011",
            "1000011",
            "1111110",
        ]
        U = [
            "1000001",
            "1000001",
            "1000001",
            "1000001",
            "1000001",
            "1000001",
            "0111110",
        ]
        S = [
            "0111110",
            "1100001",
            "1100000",
            "0111110",
            "0000011",
            "1000011",
            "0111110",
        ]
        T = [
            "1111111",
            "0011100",
            "0011100",
            "0011100",
            "0011100",
            "0011100",
            "0011100",
        ]
        E = [
            "1111111",
            "1000000",
            "1000000",
            "1111110",
            "1000000",
            "1000000",
            "1111111",
        ]
        D = [
            "1111110",
            "1000011",
            "1000001",
            "1000001",
            "1000001",
            "1000011",
            "1111110",
        ]
        return {"B": B, "U": U, "S": S, "T": T, "E": E, "D": D}

    def _big_tie_patterns(self):
        # 7x7 bitmap patterns (1 = filled)
        T = [
            "1111111",
            "0011100",
            "0011100",
            "0011100",
            "0011100",
            "0011100",
            "0011100",
        ]
        I = [
            "1111111",
            "0011100",
            "0011100",
            "0011100",
            "0011100",
            "0011100",
            "1111111",
        ]
        E = [
            "1111111",
            "1000000",
            "1000000",
            "1111110",
            "1000000",
            "1000000",
            "1111111",
        ]
        return {"T": T, "I": I, "E": E}

    def _big_fight_patterns(self):
        # 7x7 bitmap patterns (1 = filled)
        F = [
            "1111111",
            "1100000",
            "1100000",
            "1111110",
            "1100000",
            "1100000",
            "1100000",
        ]
        I = [
            "1111111",
            "0011100",
            "0011100",
            "0011100",
            "0011100",
            "0011100",
            "1111111",
        ]
        G = [
            "0111110",
            "1100011",
            "1100000",
            "1101111",
            "1100011",
            "1100011",
            "0111110",
        ]
        H = [
            "1100011",
            "1100011",
            "1100011",
            "1111111",
            "1100011",
            "1100011",
            "1100011",
        ]
        T = [
            "1111111",
            "0011100",
            "0011100",
            "0011100",
            "0011100",
            "0011100",
            "0011100",
        ]
        return {"F": F, "I": I, "G": G, "H": H, "T": T}

    def _compose_big_fight(self, term_w: int, term_h: int) -> Tuple[List[str], int, int]:
        return self._compose_big_word(term_w, term_h, "FIGHT", self._big_fight_patterns())

    def _compose_big_word(self, term_w: int, term_h: int, word: str, patterns: dict) -> Tuple[List[str], int, int]:
        """
        Compose a big word from 7x7 bitmaps; returns (lines, x, y).
        """
        # target height: big but leave bottom row for prompt
        max_h = max(7, term_h - 2)
        scale = max(1, min(4, (max_h // 9)))  # 1..4

        letter_lines = []
        for ch in word:
            # Keep spaces as actual gaps between words
            if ch == " ":
                bm_space = ["0" * 7] * 7  # 7x7 blank bitmap
                letter_lines.append(self._scale_bitmap(bm_space, scale))
                continue

            bm = patterns.get(ch)
            if bm is None:
                continue
            letter_lines.append(self._scale_bitmap(bm, scale))

        if not letter_lines:
            return [], 0, 0

        gap = " " * max(2, scale)
        lines: List[str] = []
        for row_i in range(len(letter_lines[0])):
            row = gap.join(letter_lines[j][row_i] for j in range(len(letter_lines)))
            lines.append(row)

        art_h = len(lines)
        art_w = max(len(line) for line in lines) if lines else 0
        x = max(0, (term_w // 2) - (art_w // 2))
        y = max(0, (term_h // 2) - (art_h // 2) - 1)
        return lines, x, y

    def _scale_bitmap(self, rows: List[str], scale: int) -> List[str]:
        # scale both axes by `scale`
        out: List[str] = []
        for r in rows:
            scaled_row = "".join(("█" * scale) if c == "1" else (" " * scale) for c in r)
            for _ in range(scale):
                out.append(scaled_row)
        return out

    def _compose_big_win(self, term_w: int, term_h: int) -> Tuple[List[str], int, int]:
        return self._compose_big_word(term_w, term_h, "WIN", self._big_win_patterns())

    def _compose_big_loser(self, term_w: int, term_h: int) -> Tuple[List[str], int, int]:
        return self._compose_big_word(term_w, term_h, "LOSER", self._big_loser_patterns())

    def _compose_big_busted(self, term_w: int, term_h: int) -> Tuple[List[str], int, int]:
        return self._compose_big_word(term_w, term_h, "BUSTED", self._big_busted_patterns())

    def _compose_big_tie(self, term_w: int, term_h: int) -> Tuple[List[str], int, int]:
        return self._compose_big_word(term_w, term_h, "TIE", self._big_tie_patterns())

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

    def win(self, r: TerminalRenderer, *, duration: float = 4, intensity: int = 140) -> None:
        """
        Full-screen WIN overlay:
        - Huge green 'WIN' made from block pixels (█)
        - Colorful confetti sprinkled around the board
        The overlay temporarily ignores the table; it's meant as an end-of-round splash.
        """
        term_w, term_h = r.get_size()
        art_lines, art_x, art_y = self._compose_big_win(term_w, term_h)

        # celebration start sound
        self._celebrate_sfx("start")

        self._play_bg_mp3("Win.mp3")

        # Compute a bounding box for the WIN text so we can keep confetti mostly around it.
        art_h = len(art_lines)
        art_w = max((len(s) for s in art_lines), default=0)
        box_left = art_x
        box_right = art_x + art_w
        box_top = art_y
        box_bottom = art_y + art_h

        start = time.time()
        dt = 1.0 / max(1, self.cfg.fps)

        while True:
            t = time.time() - start
            if t >= duration:
                break

            # clear full board for the overlay
            if r.clear_each_frame:
                r.clear()

            # confetti
            # sprinkle more at the borders of the WIN box to keep it readable
            for _ in range(intensity):
                # 70% chance: outside box, 30% inside (still okay)
                outside = (random.random() < 0.7)
                if outside:
                    # pick a position, retry a couple times to avoid the box
                    for __ in range(3):
                        x = random.randint(0, max(0, term_w - 1))
                        y = random.randint(0, max(0, term_h - 2))  # keep bottom row available
                        if not (box_left <= x < box_right and box_top <= y < box_bottom):
                            break
                else:
                    x = random.randint(0, max(0, term_w - 1))
                    y = random.randint(0, max(0, term_h - 2))

                ch = random.choice(CONFETTI_CHARS)
                col = random.choice(CONFETTI_COLORS)
                r.move(y + 1, x + 1)
                print(col + ch + ANSI_RESET, end="")

            # draw big WIN
            for i, line in enumerate(art_lines):
                yy = art_y + i
                if 0 <= yy < term_h:
                    r.move(yy + 1, art_x + 1)
                    print(ANSI_BOLD_GREEN + line + ANSI_RESET, end="")

            r.flush()
            time.sleep(dt)

        self._stop_bg_audio()


    def lose(self, r: TerminalRenderer, *, duration: float = 6, intensity: int = 120) -> None:
        """
        Full-screen LOSE overlay:
        - Huge red 'LOSER' made from block pixels (█)
        - Sad surrounding animation: falling "rain/tears" particles
        - Mocking SFX on macOS (say + darker system sounds) + AAA bells
        """
        term_w, term_h = r.get_size()
        art_lines, art_x, art_y = self._compose_big_loser(term_w, term_h)

        # start mocking sound
        self._mock_sfx("start")

        self._play_bg_mp3("Loser.m4a")

        art_h = len(art_lines)
        art_w = max((len(s) for s in art_lines), default=0)
        box_left = art_x
        box_right = art_x + art_w
        box_top = art_y
        box_bottom = art_y + art_h

        # initialize "sad rain" particles
        particles: List[Tuple[int, int, int, str, str]] = []
        # tuple: (x, y, vy, ch, color)

        def spawn_particle() -> None:
            # Prefer around the box edges for readability: left/right bands and top band
            region = random.random()
            if region < 0.45:
                x = random.randint(max(0, box_left - 8), max(0, box_left - 1))
            elif region < 0.9:
                x = random.randint(min(term_w - 1, box_right + 1), min(term_w - 1, box_right + 8))
            else:
                x = random.randint(max(0, box_left - 6), min(term_w - 1, box_right + 6))

            y = random.randint(0, max(0, term_h - 3))
            vy = random.choice([1, 1, 1, 2])
            ch = random.choice(SAD_CHARS)
            col = random.choice(SAD_COLORS)
            particles.append((x, y, vy, ch, col))

        start = time.time()
        dt = 1.0 / max(1, self.cfg.fps)

        # prefill
        for _ in range(max(20, intensity // 3)):
            spawn_particle()

        while True:
            t = time.time() - start
            if t >= duration:
                break

            if r.clear_each_frame:
                r.clear()

            # update particles
            new_particles: List[Tuple[int, int, int, str, str]] = []
            # spawn a few each frame
            for _ in range(max(3, intensity // 30)):
                spawn_particle()

            for (x, y, vy, ch, col) in particles:
                ny = y + vy
                # keep mostly outside the text box so the word stays readable
                inside = (box_left <= x < box_right and box_top <= ny < box_bottom)
                if inside and random.random() < 0.85:
                    # nudge to edge
                    if x < (box_left + box_right) // 2:
                        x = max(0, box_left - 1)
                    else:
                        x = min(term_w - 1, box_right + 1)

                if 0 <= x < term_w and 0 <= ny < (term_h - 1):
                    # draw a thicker tear (2 columns wide) for better visibility
                    r.move(ny + 1, x + 1)
                    print(col + ch + ANSI_RESET, end="")

                    if x + 1 < term_w:
                        r.move(ny + 1, x + 2)
                        print(col + ch + ANSI_RESET, end="")

                # keep if still on screen
                if ny < term_h - 2:
                    new_particles.append((x, ny, vy, ch, col))

            particles = new_particles

            # draw big LOSER
            for i, line in enumerate(art_lines):
                yy = art_y + i
                if 0 <= yy < term_h:
                    r.move(yy + 1, art_x + 1)
                    print(ANSI_BOLD_RED + line + ANSI_RESET, end="")

            r.flush()
            time.sleep(dt)

        self._stop_bg_audio()


    def busted(self, r: TerminalRenderer, *, duration: float = 3.0, intensity: int = 150) -> None:
        """
        Full-screen BUSTED overlay:
        - Huge blood-red 'BUSTED'
        - Thick dripping blood particles falling downward
        - TTS + background mp3 (Busted.mp3)
        """
        term_w, term_h = r.get_size()
        art_lines, art_x, art_y = self._compose_big_busted(term_w, term_h)

        # start audio
        self._busted_sfx("start")
        self._play_bg_mp3("Busted.mp3")

        art_h = len(art_lines)
        art_w = max((len(s) for s in art_lines), default=0)
        box_left = art_x
        box_right = art_x + art_w
        box_top = art_y
        box_bottom = art_y + art_h

        # dripping blood particles: (x, y, vy, ch, col)
        particles: List[Tuple[int, int, int, str, str]] = []

        def spawn_drip() -> None:
            # Spawn mostly above/around the word (top band + edges)
            region = random.random()
            if region < 0.6:
                x = random.randint(max(0, box_left - 8), min(term_w - 1, box_right + 8))
                y = random.randint(0, max(0, box_top))
            else:
                # side columns
                if random.random() < 0.5:
                    x = random.randint(max(0, box_left - 10), max(0, box_left - 1))
                else:
                    x = random.randint(min(term_w - 1, box_right + 1), min(term_w - 1, box_right + 10))
                y = random.randint(0, max(0, term_h - 3))

            vy = random.choice([1, 1, 2, 2, 3])
            ch = random.choice(BLOOD_CHARS)
            col = random.choice(BLOOD_COLORS)
            particles.append((x, y, vy, ch, col))

        # prefill a few drips
        for _ in range(max(25, intensity // 4)):
            spawn_drip()

        start = time.time()
        dt = 1.0 / max(1, self.cfg.fps)

        while True:
            t = time.time() - start
            if t >= duration:
                break

            if r.clear_each_frame:
                r.clear()

            # spawn some new drips each frame
            for _ in range(max(4, intensity // 25)):
                spawn_drip()

            new_particles: List[Tuple[int, int, int, str, str]] = []
            for (x, y, vy, ch, col) in particles:
                ny = y + vy

                # keep the word readable: if inside the text box, push outward a bit
                inside = (box_left <= x < box_right and box_top <= ny < box_bottom)
                if inside and random.random() < 0.80:
                    if x < (box_left + box_right) // 2:
                        x = max(0, box_left - 2)
                    else:
                        x = min(term_w - 1, box_right + 2)

                if 0 <= x < term_w and 0 <= ny < (term_h - 1):
                    # thick drip (2 columns) + occasional tail
                    r.move(ny + 1, x + 1)
                    print(col + ch + ANSI_RESET, end="")
                    if x + 1 < term_w:
                        r.move(ny + 1, x + 2)
                        print(col + ch + ANSI_RESET, end="")
                    if random.random() < 0.12 and ny + 1 < term_h - 1:
                        r.move(ny + 2, x + 1)
                        print(col + "▄" + ANSI_RESET, end="")

                if ny < term_h - 2:
                    new_particles.append((x, ny, vy, ch, col))

            particles = new_particles

            # draw big BUSTED
            for i, line in enumerate(art_lines):
                yy = art_y + i
                if 0 <= yy < term_h:
                    r.move(yy + 1, art_x + 1)
                    print(ANSI_BLOOD_RED + line + ANSI_RESET, end="")

            r.flush()
            time.sleep(dt)

        self._stop_bg_audio()
    def tie(self, r: TerminalRenderer, *, duration: float = 3.0, intensity: int = 90) -> None:
        """
        Full-screen TIE overlay:
        - Huge cyan 'TIE'
        - Simple neutral sparkle particles
        - TTS: 'Tie.'
        """
        term_w, term_h = r.get_size()
        art_lines, art_x, art_y = self._compose_big_tie(term_w, term_h)

        self._tie_sfx("start")

        start = time.time()
        dt = 1.0 / max(1, self.cfg.fps)

        while True:
            t = time.time() - start
            if t >= duration:
                break

            if r.clear_each_frame:
                r.clear()

            # neutral sparkles
            for _ in range(intensity):
                x = random.randint(0, max(0, term_w - 1))
                y = random.randint(0, max(0, term_h - 2))
                r.move(y + 1, x + 1)
                print(ANSI_DIM_WHITE + random.choice(["·", ".", ":", "•"]) + ANSI_RESET, end="")

            # draw big TIE
            for i, line in enumerate(art_lines):
                yy = art_y + i
                if 0 <= yy < term_h:
                    r.move(yy + 1, art_x + 1)
                    print(ANSI_BOLD_CYAN + line + ANSI_RESET, end="")

            r.flush()
            time.sleep(dt)

    def stats(self, r: TerminalRenderer, wins: int, losses: int, ties: int, *, duration: float = 3.5) -> None:
        """
        Stats splash:
        Displays wins, losses, and win rate.
        """
        term_w, term_h = r.get_size()
        w = max(0, int(wins))
        l = max(0, int(losses))
        t_ = max(0, int(ties))
        total = w + l + t_
        if total <= 0:
            winrate = 0.0
        else:
            winrate = (w / total) * 100.0
        # play special audio if winrate is 0% and extend duration to 3:03
        if winrate <= 0.0:
            self._play_bg_mp3("Big Loser.mp3")
            duration = 183.0  # 3 minutes and 3 seconds

        lines = [
            "STATS",
            "",
            f"Wins:   {w}",
            f"Losses: {l}",
            f"Ties:   {t_}",
            "",
            f"Win rate: {winrate:.1f}%",
        ]

        # Center the block
        block_w = max(len(s) for s in lines)
        block_h = len(lines)
        x0 = max(0, (term_w // 2) - (block_w // 2))
        y0 = max(0, (term_h // 2) - (block_h // 2) - 1)

        start = time.time()
        dt = 1.0 / max(1, self.cfg.fps)

        while True:
            if time.time() - start >= duration:
                break

            if r.clear_each_frame:
                r.clear()

            # light neutral sparkle background
            for _ in range(80):
                x = random.randint(0, max(0, term_w - 1))
                y = random.randint(0, max(0, term_h - 2))
                r.move(y + 1, x + 1)
                print(ANSI_DIM_WHITE + random.choice(["·", ".", ":"]) + ANSI_RESET, end="")

            for i, s in enumerate(lines):
                yy = y0 + i
                if 0 <= yy < term_h:
                    r.move(yy + 1, x0 + 1)
                    if s == "STATS":
                        print(ANSI_BOLD_CYAN + BOLD.prefix + s + BOLD.suffix + ANSI_RESET, end="")
                    elif s.startswith("Wins:"):
                        print(ANSI_BOLD_GREEN + s + ANSI_RESET, end="")
                    elif s.startswith("Losses:"):
                        print(ANSI_BOLD_RED + s + ANSI_RESET, end="")
                    elif s.startswith("Ties:"):
                        print(ANSI_BOLD_CYAN + s + ANSI_RESET, end="")
                    elif s.startswith("Win rate:"):
                        # yellow if positive, red if zero
                        col = ANSI_BOLD_YELLOW if winrate > 0 else ANSI_BOLD_RED
                        print(col + s + ANSI_RESET, end="")
                    else:
                        print(BOLD.prefix + s + BOLD.suffix, end="")

            r.flush()
            time.sleep(dt)

        self._stop_bg_audio()

    def round(self, r: TerminalRenderer, x: int, *, screen_hold: float = 1.2) -> None:
        """
        Round splash:
        - Shows big 'ROUND X'
        - Speaks 'Round {x}' (blocking)
        - ONLY after TTS completes, plays fight.mp3
        """
        term_w, term_h = r.get_size()
        art_lines, art_x, art_y = self._compose_big_round(term_w, term_h, x)

        # Clear and draw the round splash
        if r.clear_each_frame:
            r.clear()

        # subtle corner sparks (static)
        for _ in range(120):
            xx = random.randint(0, max(0, term_w - 1))
            yy = random.randint(0, max(0, term_h - 2))
            if random.random() < 0.15:
                r.move(yy + 1, xx + 1)
                print("\x1b[2;33m" + random.choice([".", "·", "*"]) + ANSI_RESET, end="")

        for i, line in enumerate(art_lines):
            yy = art_y + i
            if 0 <= yy < term_h:
                r.move(yy + 1, art_x + 1)
                print(ANSI_BOLD_YELLOW + line + ANSI_RESET, end="")

        r.flush()

        # Speak (blocking), then play fight.mp3
        self._sfx_say_blocking(f"Round {x}")
        self._play_bg_mp3("fight.mp3")

        # As soon as the fight audio starts, switch the splash to FIGHT
        fight_lines, fight_x, fight_y = self._compose_big_fight(term_w, term_h)

        if r.clear_each_frame:
            r.clear()

        # reuse the same subtle sparks
        for _ in range(120):
            xx = random.randint(0, max(0, term_w - 1))
            yy = random.randint(0, max(0, term_h - 2))
            if random.random() < 0.15:
                r.move(yy + 1, xx + 1)
                print("\x1b[2;33m" + random.choice([".", "·", "*"]) + ANSI_RESET, end="")

        for i, line in enumerate(fight_lines):
            yy = fight_y + i
            if 0 <= yy < term_h:
                r.move(yy + 1, fight_x + 1)
                print(ANSI_BOLD_YELLOW + line + ANSI_RESET, end="")

        r.flush()

        # Hold screen briefly while music starts, then stop (keeps flow snappy)
        time.sleep(max(0.0, screen_hold))
        self._stop_bg_audio()
    def _big_round_patterns(self):
        # Reuse 7x7 style for ROUND + digits
        R = [
            "1111110",
            "1000011",
            "1000011",
            "1111110",
            "1001100",
            "1000110",
            "1000011",
        ]
        O = [
            "0111110",
            "1100011",
            "1100011",
            "1100011",
            "1100011",
            "1100011",
            "0111110",
        ]
        U = [
            "1000001",
            "1000001",
            "1000001",
            "1000001",
            "1000001",
            "1000001",
            "0111110",
        ]
        N = [
            "1000001",
            "1100001",
            "1110001",
            "1011001",
            "1001101",
            "1000111",
            "1000001",
        ]
        D = [
            "1111110",
            "1000011",
            "1000001",
            "1000001",
            "1000001",
            "1000011",
            "1111110",
        ]

        digits = {
            "0": [
                "0111110",
                "1100011",
                "1100111",
                "1101011",
                "1110011",
                "1100011",
                "0111110",
            ],
            "1": [
                "0011000",
                "0111000",
                "0011000",
                "0011000",
                "0011000",
                "0011000",
                "0111110",
            ],
            "2": [
                "0111110",
                "1100011",
                "0000011",
                "0001110",
                "0110000",
                "1100000",
                "1111111",
            ],
            "3": [
                "0111110",
                "1100011",
                "0000011",
                "0011110",
                "0000011",
                "1100011",
                "0111110",
            ],
            "4": [
                "0001110",
                "0011110",
                "0110110",
                "1100110",
                "1111111",
                "0000110",
                "0000110",
            ],
            "5": [
                "1111111",
                "1100000",
                "1111110",
                "0000011",
                "0000011",
                "1100011",
                "0111110",
            ],
            "6": [
                "0011110",
                "0110000",
                "1100000",
                "1111110",
                "1100011",
                "1100011",
                "0111110",
            ],
            "7": [
                "1111111",
                "0000011",
                "0000110",
                "0001100",
                "0011000",
                "0011000",
                "0011000",
            ],
            "8": [
                "0111110",
                "1100011",
                "1100011",
                "0111110",
                "1100011",
                "1100011",
                "0111110",
            ],
            "9": [
                "0111110",
                "1100011",
                "1100011",
                "0111111",
                "0000011",
                "0000110",
                "0111100",
            ],
        }

        pat = {"R": R, "O": O, "U": U, "N": N, "D": D}
        pat.update(digits)
        return pat

    def _compose_big_round(self, term_w: int, term_h: int, x: int) -> Tuple[List[str], int, int]:
        # Allow multi-digit x
        word = f"ROUND {x}"
        return self._compose_big_word(term_w, term_h, word, self._big_round_patterns())