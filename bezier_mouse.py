"""
Bezier Mouse — human-like mouse trajectories.

A real person never moves the mouse in a straight line: the hand arcs,
overshoots the target, corrects, trembles, accelerates in the middle and
decelerates near the target (ease-in-out). This module generates a cubic
Bezier curve with 2 control points (offset perpendicular to the line + overshoot),
step count proportional to distance/speed, plus physiological tremor
(8-12Hz multi-octave) and frame-quantized step delays.

Injectors (engine-independent): Playwright (page.mouse.move), Selenium
ActionChains, raw CDP (Input.dispatchMouseEvent). Headless fallback → final point only.

Autonomous, $0, no network. Accepts an optional behavioral profile
(dict or object) for per-user handwriting styles.
"""
from __future__ import annotations


def _swallow_err(_block, _err):
    """Never-raising guard: swallowed errors are only logged."""
    try:
        log.debug("suppressed in %s: %r", _block, _err)
    except Exception:
        pass


import logging
import math
import random
import time

log = logging.getLogger("humanlike_engine.bezier_mouse")


def _cubic(p0, p1, p2, p3, t):
    """Точка на кубической Безье при t∈[0,1]."""
    mt = 1.0 - t
    a, b, c, d = mt * mt * mt, 3 * mt * mt * t, 3 * mt * t * t, t * t * t
    return (a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0],
            a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1])


def _ease(t: float) -> float:
    """Ease-in-out: медленный старт, разгон, торможение (smoothstep)."""
    return t * t * (3.0 - 2.0 * t)


def _profile_get(profile, key, default):
    """Читать параметр из profile — dict (behavior_profile) или object (BehavioralProfile)."""
    if profile is None:
        return default
    if isinstance(profile, dict):
        return profile.get(key, default)
    return getattr(profile, key, default)


def calculate_dynamic_mouse_speed(box_width: float, box_height: float) -> float:
    """Коэффициент скорости на основе площади цели (Закон Фиттса).

    Мелкая кнопка → медленнее (аккуратное прицеливание).
    Крупный баннер → быстрее (не надо целиться).
    Базовый размер ~150x40 = 6000px → speed_factor = 1.0.
    Диапазон: 0.6 (микро-кнопки) … 1.8 (огромные блоки).
    """
    area = max(float(box_width) * float(box_height), 100.0)
    speed = math.log10(area) / 3.77
    return max(0.6, min(speed, 1.8))


def bezier_path(x1, y1, x2, y2, rng=None, profile=None, steps: int = None,
               target_size: tuple = None, undershoot_chance: float = None,
               overshoot_chance: float = None) -> list:
    """Сгенерировать список (x,y) точек человеческой траектории мыши.

    Кривизна: 2 контрольные точки смещены перпендикулярно линии (дуга) + случайный overshoot
    у цели (промах и доводка). Дрожание tremor на каждом шаге. Шаги ∝ дистанции/скорости.

    profile: dict (из behavior_profile) или object (BehavioralProfile).
        dict-ключи: mouse_deviation, mouse_speed_modifier, overshoot_chance.
    target_size: (width, height) цели — размерозависимая скорость по Фиттсу.
    undershoot_chance: переопределение шанса недолёта (0.15 для мелких целей).
    overshoot_chance: переопределение шанса перелёта (0.18 для крупных целей).
    """
    r = rng or random.Random()
    dist = math.hypot(x2 - x1, y2 - y1)

    # Параметры почерка из profile (dict или object)
    deviation = _profile_get(profile, "mouse_deviation", r.randint(15, 45))
    speed_mod = _profile_get(profile, "mouse_speed_modifier", r.uniform(0.8, 1.5))
    base_overshoot = _profile_get(profile, "overshoot_chance", r.uniform(0.10, 0.35))
    tremor = _profile_get(profile, "tremor_px", 1.0)

    # Размерозависимая скорость (Фиттс): мелкая цель = медленнее
    if target_size is not None:
        size_speed = calculate_dynamic_mouse_speed(target_size[0], target_size[1])
        speed_mod *= size_speed

    # Размерозависимые шансы недолёта/перелёта
    if undershoot_chance is None:
        undershoot_chance = 0.12 if target_size and target_size[0] * target_size[1] < 3000 else 0.05
    if overshoot_chance is None:
        overshoot_chance = base_overshoot
        if target_size and target_size[0] * target_size[1] > 20000:
            overshoot_chance += 0.08  # крупная цель → чаще перелёт

    if steps is None:
        # Минимум 25 шагов — человек не телепортирует курсор за 8 кадров
        steps = int(max(25, min(200, dist / max(2.0, speed_mod * 12.0))))

    if dist < 1e-6:
        return [(x2, y2)]

    nx, ny = -(y2 - y1) / dist, (x2 - x1) / dist
    # Power-law bow magnitude — human fingerprint vs plain Gaussian
    bow_mag = deviation * 3
    bow = r.uniform(-1, 1) * min(bow_mag, dist * 0.25)

    # 2 контрольные точки на 1/3 и 2/3 с выгибом + джиттер
    c1 = (x1 + (x2 - x1) / 3 + nx * bow + r.uniform(-8, 8),
          y1 + (y2 - y1) / 3 + ny * bow + r.uniform(-8, 8))
    c2 = (x1 + 2 * (x2 - x1) / 3 + nx * bow * 0.6 + r.uniform(-8, 8),
          y1 + 2 * (y2 - y1) / 3 + ny * bow * 0.6 + r.uniform(-8, 8))

    do_overshoot = dist > 40 and r.random() < overshoot_chance
    if do_overshoot:
        overshoot_px = r.randint(4, 10)
        ox = x2 + (x2 - x1) / dist * r.uniform(0.4, 1.0) * overshoot_px
        oy = y2 + (y2 - y1) / dist * r.uniform(0.4, 1.0) * overshoot_px
        aim = (ox, oy)
    else:
        aim = (x2, y2)

    pts = []
    _time = 0.0
    for i in range(steps + 1):
        t = _ease(i / steps)
        px, py = _cubic((x1, y1), c1, c2, aim, t)
        if 0 < i < steps:  # multi-octave физиологический тремор (8-12Hz)
            _time += 1.0 / 60.0   # ~60Hz семплинг (синхронизация с vsync монитора)
            _tremor_x = 0.0
            _tremor_y = 0.0
            for _oct in range(2):  # 2 октавы: 8Hz, 16Hz (32Hz > Nyquist 30Hz при 60Hz семплинге)
                _freq = 8.0 * (2 ** _oct)
                _amp = tremor / (2 ** _oct)
                _tremor_x += _amp * math.sin(2 * math.pi * _freq * _time + r.uniform(0, math.pi))
                _tremor_y += _amp * math.cos(2 * math.pi * _freq * _time + r.uniform(0, math.pi))
            px += _tremor_x
            py += _tremor_y
        pts.append((px, py))

    if do_overshoot:
        # доводка от промаха к точной цели (2-4 коротких шага)
        n = r.randint(2, 4)
        sx, sy = pts[-1]
        for j in range(1, n + 1):
            t = j / n
            pts.append((sx + (x2 - sx) * t + r.uniform(-tremor, tremor) * (t < 1),
                        sy + (y2 - sy) * t + r.uniform(-tremor, tremor) * (t < 1)))

    pts[-1] = (float(x2), float(y2))  # финал ровно в цель
    return pts


_FRAME_60HZ = 1.0 / 60     # ~16.67ms — стандартный офисный монитор 60Hz


def _step_delays(n: int, profile, rng) -> list:
    """Задержки между шагами (сек) с кривой ускорения/замедления.

    Human acceleration curve: start slow → peak speed in middle → decelerate →
    gentle landing at target. Trajectory analyzers look at the histogram of
    mousemove intervals — constant/uniform speed reads as non-human.
    """
    import math
    if isinstance(profile, dict):
        speed = _profile_get(profile, "mouse_speed_modifier", 1.15) or 1.0
    else:
        spd_lo, spd_hi = getattr(profile, "mouse_speed_range", None) or [0.8, 2.0]
        speed = (spd_lo + spd_hi) / 2.0 or 1.0

    single_frame_ratio = 0.05
    two_frame_ratio = 0.45 + 0.3 * speed
    out = []
    total_raw = 0.0
    for i in range(n):
        t = i / max(n - 1, 1)
        # Gentle ease-in-out: 1.3x at ends, 1.0x at middle (smooth, no jerky stops)
        ease = 1.0 + 0.3 * (1.0 - math.sin(t * math.pi))
        ease *= rng.uniform(0.92, 1.08)

        # Frame-quantized delays: 8-16ms for smooth 60-120Hz movement
        roll = rng.random()
        if roll < 0.15:   frames = 1     # 16.7ms — fast frames
        elif roll < 0.75: frames = 1     # most frames at 1-frame speed
        else:             frames = 2     # occasional 2-frame (33ms) — natural variance

        jitter = rng.uniform(0.88, 1.12)
        delay = max(0.008, _FRAME_60HZ * frames * jitter * ease)
        out.append(delay)
        total_raw += _FRAME_60HZ * frames * jitter

    # Clamp total time to human range: 0.15-0.45 seconds
    if total_raw > 0 and len(out) > 0:
        target_total = rng.uniform(0.18, 0.40)
        scale = target_total / total_raw
        for i in range(len(out)):
            out[i] *= scale

    return out


def human_move_mouse(page, x1, y1, x2, y2, *, profile=None, rng=None) -> tuple:
    """Playwright: move the mouse along a human curve via page.mouse.move (CDP).

    Some anti-detect browsers relay page.mouse.move to trusted OS events.
    Returns the final (x,y) in viewport coordinates.
    """
    r = rng or random.Random()
    pts = bezier_path(x1, y1, x2, y2, rng=r, profile=profile)
    delays = _step_delays(len(pts), profile, r)

    for (px, py), d in zip(pts, delays):
        page.mouse.move(px, py)
        time.sleep(d)
    fx, fy = pts[-1]
    try:
        from cursor_state import set as _cs_set
        _cs_set(fx, fy)
    except Exception as _err:        _swallow_err("bezier_mouse", _err)
    return (fx, fy)


def human_move_mouse_cdp(driver, x1, y1, x2, y2, *, profile=None, rng=None) -> tuple:
    """Raw CDP: Input.dispatchMouseEvent along the curve. Returns the final (x,y)."""
    r = rng or random.Random()
    pts = bezier_path(x1, y1, x2, y2, rng=r, profile=profile)
    delays = _step_delays(len(pts), profile, r)
    for (px, py), d in zip(pts, delays):
        try:
            driver.execute_cdp_cmd("Input.dispatchMouseEvent",
                                   {"type": "mouseMoved", "x": float(px), "y": float(py)})
        except Exception:
            log.debug("CDP mouseMoved failed", exc_info=True)
            break
        time.sleep(d)
    return pts[-1]


def human_move_mouse_selenium(driver, element, x1, y1, *, profile=None, rng=None):
    """Selenium ActionChains: подвести к центру element по кривой (относит. смещения)."""
    from selenium.webdriver.common.action_chains import ActionChains
    r = rng or random.Random()
    loc = element.location
    size = element.size
    x2 = loc["x"] + size["width"] / 2
    y2 = loc["y"] + size["height"] / 2
    pts = bezier_path(x1, y1, x2, y2, rng=r, profile=profile)
    ac = ActionChains(driver)
    prev = (x1, y1)
    for (px, py) in pts:
        ac.move_by_offset(px - prev[0], py - prev[1])
        prev = (px, py)
    ac.perform()
    return pts[-1]


def human_move(session, x1, y1, x2, y2, *, profile=None, rng=None) -> tuple:
    """Engine-independent entry: accepts a session-like object (engine + _page/_driver).

    playwright → human_move_mouse; selenium → CDP; no engine → final point only.
    """
    engine = getattr(session, "engine", "")
    try:
        if engine == "playwright" and getattr(session, "_page", None):
            return human_move_mouse(session._page, x1, y1, x2, y2, profile=profile, rng=rng)
        drv = getattr(session, "_driver", None)
        if drv is not None:
            return human_move_mouse_cdp(drv, x1, y1, x2, y2, profile=profile, rng=rng)
    except Exception:
        log.warning("human_move failed — fallback no-op", exc_info=True)
    return (float(x2), float(y2))  # истинный headless / нет движка → просто цель


# ── smoke self-test ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    print("=== bezier_mouse self-test ===")
    prof = {"mouse_deviation": 30, "mouse_speed_modifier": 1.1, "overshoot_chance": 0.2}
    rng = random.Random(42)

    # 1) base trajectory: start/end exact, middle is NOT a straight line
    pts = bezier_path(0, 0, 300, 200, rng=rng, profile=prof)
    assert pts[-1] == (300.0, 200.0), pts[-1]
    assert len(pts) >= 8

    def dev(p):  # distance from the straight line (0,0)-(300,200)
        return abs(200 * p[0] - 300 * p[1]) / math.hypot(300, 200)

    max_dev = max(dev(p) for p in pts)
    assert max_dev > 5.0, f"path too straight: max_dev={max_dev:.1f}"
    print(f"  path: {len(pts)} pts, end==target, curvature {max_dev:.1f}px: OK")

    # 2) determinism: same seed → same path; different seed → different path
    p_a = bezier_path(10, 10, 400, 300, rng=random.Random(7), profile=prof)
    p_b = bezier_path(10, 10, 400, 300, rng=random.Random(7), profile=prof)
    p_c = bezier_path(10, 10, 400, 300, rng=random.Random(99), profile=prof)
    assert p_a == p_b and p_a != p_c
    print("  determinism (same seed = same path): OK")

    # 3) edge cases
    assert bezier_path(5, 5, 12, 8, rng=random.Random(1), profile=prof)[-1] == (12.0, 8.0)
    assert bezier_path(50, 50, 50, 50, rng=rng, profile=prof)[-1] == (50, 50)
    print("  short / zero-distance moves: OK")

    # 4) fake Playwright page: N moves, final at target
    class _FakeMouse:
        def __init__(self):
            self.moves = []

        def move(self, x, y):
            self.moves.append((x, y))

    class _FakePage:
        def __init__(self):
            self.mouse = _FakeMouse()

    fp = _FakePage()
    final = human_move_mouse(fp, 0, 0, 200, 150, profile=prof, rng=random.Random(3))
    assert len(fp.mouse.moves) >= 8
    assert fp.mouse.moves[-1] == (200.0, 150.0)
    assert final == (200.0, 150.0)
    print(f"  playwright injector: {len(fp.mouse.moves)} moves, ends at target: OK")

    # 5) fake CDP driver
    class _FakeDriver:
        def __init__(self):
            self.calls = []

        def execute_cdp_cmd(self, m, p):
            self.calls.append((m, p["x"], p["y"]))

    fd = _FakeDriver()
    human_move_mouse_cdp(fd, 0, 0, 100, 100, profile=prof, rng=random.Random(4))
    assert len(fd.calls) >= 8
    assert fd.calls[0][0] == "Input.dispatchMouseEvent"
    print(f"  CDP injector: {len(fd.calls)} dispatchMouseEvent calls: OK")

    print("=== PASS ===")
    sys.exit(0)
