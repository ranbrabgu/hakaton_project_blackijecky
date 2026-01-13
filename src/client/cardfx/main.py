# main.py
import time

from .terminal import TerminalRenderer
from .animations import (
    IntroShuffle,
    IntroShuffleConfig,
    BlackjackTable,
    BlackjackTableConfig,
)


def main():
    r = TerminalRenderer(clear_each_frame=True)

    # --- 1) Intro shuffle ---
    intro = IntroShuffle(
        IntroShuffleConfig(
            duration_s=7.4,
            fps=55,
            visible_cards=26,
            passes=3,
            B_end=0.82,
            C_end=0.82,
            cascade_gap=0.018,
            cascade_flip_dur=0.16,
        )
    )

    r.begin()
    try:
        table = BlackjackTable(BlackjackTableConfig())
        intro.run(r)

        # small pause between scenes
        time.sleep(0.4)

        # --- 2) Blackjack table ---
        table.render(r)
        time.sleep(1)
        table.set_permanent_prompt(r, "Initial Draw")

        # 2. draw player card
        table.deal_card(r, "player", "A", "♠")

        # 3. draw player card
        table.deal_card(r, "player", "7", "♥")

        # 4. draw dealer card (auto hole card is added)
        table.deal_card(r, "dealer", "K", "♦")

        table.set_permanent_prompt(r, None)
        table.set_temporary_prompt(r, "Hit or Stand")
        time.sleep(1)
        table.set_temporary_prompt(r, None)
        # 5. draw player card
        table.deal_card(r, "player", "5", "♣")

        table.set_temporary_prompt(r, "Hit or Stand")
        time.sleep(1)
        table.set_temporary_prompt(r, None)

        table.set_permanent_prompt(r, "Dealer's turn")
        time.sleep(1)
        # 6. draw dealer card (this flips the hole card)
        table.deal_card(r, "dealer", "9", "♠")

        # 7. draw dealer card (normal dealer hit)
        table.deal_card(r, "dealer", "3", "♥")

        table.set_permanent_prompt(r, None)

        # keep final state visible
        time.sleep(1.0)
        table.win(r)
        table.lose(r)
        table.busted(r)

    finally:
        r.end()


if __name__ == "__main__":
    main()