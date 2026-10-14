"""Core test suite for humanlike-browser-engine (Этап 0: evidence before push).

Covers: inertial scroll math (H2 regression), typo text integrity (H1
regression), focus budget (H6), Fitts bounds, Bezier determinism, and
negative cases (tiny deltas rejected, unfocused budget respected).
"""
import random
import time

import pytest

import distribution_browser_engine as dbe
import bezier_mouse


@pytest.fixture(autouse=True)
def fast_mode_and_fresh_focus():
    dbe.set_fast_mode(True)
    dbe._focus_ok_ts = 0.0
    yield
    dbe.set_fast_mode(False)
    dbe._focus_ok_ts = 0.0


# ── H2: inertial scroll plan ───────────────────────────────────────────────

@pytest.mark.parametrize("total,steps", [(600, 8), (2000, 15), (50, 8), (1200, 12), (300, 10)])
def test_plan_steps_sum_to_requested_total(total, steps):
    plan = dbe._plan_inertial_steps(float(total), steps, random.Random(42))
    assert abs(sum(plan) - total) <= 2
    assert all(s >= 2 for s in plan)


def test_plan_respects_per_step_cap_for_large_totals():
    plan = dbe._plan_inertial_steps(2000.0, 15, random.Random(7))
    assert max(plan) <= 80


def test_plan_tiny_total_does_not_overdeliver():
    # Each step has a 2px floor — without a step-count clamp a 5px scroll
    # would plan 8 steps = 16px. Regression for the pass-1 finding.
    for total in (5, 8, 12, 16):
        plan = dbe._plan_inertial_steps(float(total), 8, random.Random(1))
        assert abs(sum(plan) - total) <= 2, f"total={total} plan={plan}"


class _WheelRecorder:
    def __init__(self):
        self.deltas = []

    def wheel(self, _x, dy):
        self.deltas.append(dy)


class _WheelPage:
    def __init__(self):
        self.mouse = _WheelRecorder()


def test_wheel_delivers_full_delta_in_fast_mode():
    page = _WheelPage()
    dbe._human_inertial_wheel(page, 600, random.Random(42))
    assert page.mouse.deltas, "wheel never called"
    assert abs(sum(page.mouse.deltas) - 600) <= 3


def test_wheel_negative_tiny_delta_is_rejected():
    page = _WheelPage()
    dbe._human_inertial_wheel(page, 4, random.Random(42))
    assert page.mouse.deltas == []


def test_wheel_negative_direction_preserved():
    page = _WheelPage()
    dbe._human_inertial_wheel(page, -400, random.Random(3))
    assert page.mouse.deltas
    assert all(dy < 0 for dy in page.mouse.deltas)
    assert abs(sum(page.mouse.deltas) + 400) <= 3


# ── H1: burst typing preserves the text even when typos trigger ────────────

class _KeyRecorder:
    def __init__(self):
        self.buffer = []
        self._pending = None

    def press(self, key):
        if key == "Backspace":
            if self.buffer:
                self.buffer.pop()
        else:
            self.buffer.append(key)

    def down(self, key):
        self._pending = key

    def up(self, _key):
        if self._pending is not None:
            self.buffer.append(self._pending)
            self._pending = None


class _TypingPage:
    def __init__(self):
        self.keyboard = _KeyRecorder()


class _FatigueStub:
    current_wpm = 60
    current_typo_rate = 1.0  # forces a typo every 50th char
    current_tremor_sigma = None


def test_burst_typing_text_survives_triggered_typos():
    text = ("the quick brown fox jumps over the lazy dog and keeps running "
            "past the old river bank while the quiet village wakes up slowly "
            "in the pale morning light")[:140]
    page = _TypingPage()
    dbe._human_burst_type(page, text, random.Random(42), fatigue=_FatigueStub())
    typed = "".join(page.keyboard.buffer)
    assert typed == text, f"typed={typed!r} expected={text!r}"


def test_burst_typing_short_text_is_exact():
    text = "hello world, this is a plain short line"
    page = _TypingPage()
    dbe._human_burst_type(page, text, random.Random(7))
    assert "".join(page.keyboard.buffer) == text


# ── H6: focus budget ───────────────────────────────────────────────────────

class _AlwaysUnfocusedPage:
    class _M:
        def move(self, *a, **k):
            pass

        def click(self, *a, **k):
            pass

    mouse = _M()

    def evaluate(self, _js, *a):
        if "visibilityState" in _js:
            return {"visible": True, "focused": False}
        return [0, 0]


def test_focus_check_returns_within_budget_when_unfocused():
    page = _AlwaysUnfocusedPage()
    started = time.monotonic()
    result = dbe._ensure_tab_focus(page, random.Random(1))
    elapsed = time.monotonic() - started
    assert result is False
    assert elapsed < 4.0, f"budget blown: {elapsed:.1f}s"


def test_focus_success_is_cached():
    class _FocusedPage(_AlwaysUnfocusedPage):
        def evaluate(self, _js, *a):
            if "visibilityState" in _js:
                return {"visible": True, "focused": True}
            return [0, 0]

    assert dbe._ensure_tab_focus(_FocusedPage(), random.Random(1)) is True
    started = time.monotonic()
    # Second call inside the 3s cache must not evaluate the page at all.
    class _ExplodingPage:
        def evaluate(self, _js, *a):
            raise AssertionError("cache miss: page evaluated")

    assert dbe._ensure_tab_focus(_ExplodingPage(), random.Random(1)) is True
    assert time.monotonic() - started < 0.2


# ── H3: click after auto-scroll must use a fresh bounding box ──────────────

class _ClickMouse:
    def __init__(self):
        self.moves = []
        self.wheels = []
        self.downs = 0

    def move(self, x, y, steps=None):
        self.moves.append((x, y))

    def wheel(self, _x, dy):
        self.wheels.append(dy)

    def down(self):
        self.downs += 1

    def up(self):
        pass

    def click(self, *a, **k):
        self.downs += 1


class _ClickPage:
    viewport_size = {"width": 1024, "height": 768}

    def __init__(self):
        self.mouse = _ClickMouse()

    def evaluate(self, js, *a):
        if "visibilityState" in js:
            return {"visible": True, "focused": True}
        if "innerWidth" in js:
            return [1024, 768]
        if "screenX" in js:
            return [0, 0]
        return None


class _MovingElement:
    """bbox at y=700 (outside 85% viewport → triggers scroll); y=300 after."""

    def __init__(self, page):
        self.page = page

    def bounding_box(self):
        if self.page.mouse.wheels:
            return {"x": 400, "y": 300, "width": 80, "height": 30}
        return {"x": 400, "y": 700, "width": 80, "height": 30}


def test_click_after_autoscroll_targets_fresh_bbox():
    page = _ClickPage()
    dbe._human_click_element(page, _MovingElement(page), random.Random(42))
    assert page.mouse.wheels, "precondition: scroll must trigger"
    assert page.mouse.downs >= 1, "click never happened"
    final_x, final_y = page.mouse.moves[-1]
    # Fresh bbox is at y≈300; the stale one was at y≈700 (past the 85%
    # viewport line). Landing near 700 would mean the pre-scroll box was used.
    assert 290 <= final_y <= 350, f"clicked at stale y={final_y}"


class _DetachingElement:
    """bbox disappears once the scroll happens (element detached)."""

    def __init__(self, page):
        self.page = page

    def bounding_box(self):
        if self.page.mouse.wheels:
            return None
        return {"x": 400, "y": 700, "width": 80, "height": 30}


def test_click_aborts_when_bbox_lost_after_scroll():
    page = _ClickPage()
    result = dbe._human_click_element(page, _DetachingElement(page), random.Random(42))
    assert page.mouse.wheels, "precondition: scroll must trigger"
    assert result is False
    assert page.mouse.downs == 0, "stale-coordinates click must not fire"


# ── Fitts / Bezier primitives ──────────────────────────────────────────────

def test_fitts_offset_stays_inside_element():
    rng = random.Random(42)
    for _ in range(500):
        ox, oy = dbe._fitts_click_offset(rng, 200, 40)
        assert 10 <= ox <= 190  # 5%..95% clamp
        assert 2 <= oy <= 38


def test_bezier_path_ends_at_target():
    pts = bezier_mouse.bezier_path(0, 0, 300, 200, rng=random.Random(42),
                                   profile={"mouse_deviation": 30})
    assert pts[-1] == (300.0, 200.0)
    assert len(pts) >= 8


def test_bezier_same_seed_same_path():
    kw = dict(profile={"mouse_deviation": 30})
    a = bezier_mouse.bezier_path(10, 10, 400, 300, rng=random.Random(7), **kw)
    b = bezier_mouse.bezier_path(10, 10, 400, 300, rng=random.Random(7), **kw)
    c = bezier_mouse.bezier_path(10, 10, 400, 300, rng=random.Random(99), **kw)
    assert a == b
    assert a != c


# ── cursor_state: CSS -> OS mapping (DPI) ──────────────────────────────────

def test_detect_scale_identity_and_dpi():
    import cursor_state
    assert cursor_state._detect_scale(1920, 1920) == 1.0   # 100% / unaware
    assert cursor_state._detect_scale(2880, 1920) == 1.5   # 150% aware
    assert cursor_state._detect_scale(0, 1920) == 1.0      # no OS info
    assert cursor_state._detect_scale(1920, 0) == 1.0      # no CSS info


def test_css_to_os_applies_scale_offset_and_rounding():
    import cursor_state
    old = (cursor_state._scale,
           cursor_state._window_offset_x, cursor_state._window_offset_y)
    try:
        cursor_state._scale = 1.0
        cursor_state._window_offset_x = 0
        cursor_state._window_offset_y = 0
        assert cursor_state._css_to_os(100.4, 200.6) == (100, 201)

        cursor_state._scale = 1.25
        cursor_state._window_offset_x = 32
        cursor_state._window_offset_y = 40
        assert cursor_state._css_to_os(100, 200) == (157, 290)

        cursor_state._scale = 1.0
        cursor_state._window_offset_x = -10
        cursor_state._window_offset_y = 0
        assert cursor_state._css_to_os(5, 5) == (-5, 5)
    finally:
        (cursor_state._scale,
         cursor_state._window_offset_x,
         cursor_state._window_offset_y) = old


def test_calibrate_uses_screen_width_ratio():
    import cursor_state

    class _FakePage:
        def evaluate(self, _js):
            return [32, 64, 1920]  # screenX, screenY, CSS screen width

    old = (cursor_state._scale,
           cursor_state._window_offset_x, cursor_state._window_offset_y,
           cursor_state._GetSystemMetrics)
    try:
        cursor_state._GetSystemMetrics = lambda _idx: 2880  # aware @150%
        cursor_state.calibrate_window_offset(_FakePage())
        assert cursor_state._scale == 1.5
        assert cursor_state._window_offset_x == 48   # 32 * 1.5
        assert cursor_state._window_offset_y == 96   # 64 * 1.5
    finally:
        (cursor_state._scale,
         cursor_state._window_offset_x,
         cursor_state._window_offset_y,
         cursor_state._GetSystemMetrics) = old
