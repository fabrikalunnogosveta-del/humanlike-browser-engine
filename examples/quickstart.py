"""Runnable demo — no browser or network required.

    python examples/quickstart.py
"""
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bezier_mouse import bezier_path, human_move_mouse
from distribution_browser_engine import (
    _human_inertial_wheel,
    set_fast_mode,
)


class FakeMouse:
    def __init__(self):
        self.moves = []
        self.wheels = []

    def move(self, x, y, steps=None):
        self.moves.append((round(x, 1), round(y, 1)))

    def wheel(self, _x, dy):
        self.wheels.append(dy)


class FakePage:
    def __init__(self):
        self.mouse = FakeMouse()


def main():
    set_fast_mode(True)  # real runs: drop this line

    # 1) Bezier trajectory: same seed → same path, ends at the target
    pts = bezier_path(0, 0, 400, 300, rng=random.Random(7),
                      profile={"mouse_deviation": 30})
    print(f"bezier: {len(pts)} points, end={pts[-1]}")

    # 2) Inertial scroll: steps sum to exactly the requested 600px
    page = FakePage()
    _human_inertial_wheel(page, 600, random.Random(42))
    total = sum(page.mouse.wheels)
    print(f"scroll: {len(page.mouse.wheels)} wheel events, sum={total:.0f}px (requested 600)")

    # 3) Playwright-style injector on a fake page
    page2 = FakePage()
    final = human_move_mouse(page2, 10, 10, 300, 200, rng=random.Random(3),
                             profile={"mouse_deviation": 25})
    print(f"injector: {len(page2.mouse.moves)} moves, final={final}")

    print("OK")


if __name__ == "__main__":
    main()
