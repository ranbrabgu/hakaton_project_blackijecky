# main.py
from terminal import TerminalRenderer
from animations import IntroShuffle, IntroShuffleConfig

def main():
    r = TerminalRenderer(clear_each_frame=True)
    anim = IntroShuffle(IntroShuffleConfig(
        duration_s=7.4,
        fps=55,
        visible_cards=26,
        passes=3,
        B_end=0.82,
        C_end=0.82,
        cascade_gap=0.018,
        cascade_flip_dur=0.16,
    ))

    r.begin()
    try:
        anim.run(r)
    finally:
        r.end()

if __name__ == "__main__":
    main()