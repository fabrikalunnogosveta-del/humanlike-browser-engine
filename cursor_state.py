"""
Shared cursor-position state for all humanization primitives.

Single source of truth for the virtual cursor. Invariants:
1. virtual(x,y) * scale + window_offset(screenX, screenY) = OS cursor position.
   `scale` = (OS screen width in OUR process units) / (CSS screen width) —
   it absorbs both DPI scaling (125/150%) and the process DPI-awareness mode,
   so CSS px and SetCursorPos px always land on the same physical point.
2. NEVER start a Bezier path from (0,0).
3. The OS cursor tracks every Bezier step 1:1 — no drift between
   the stored state and the real pointer.
"""
from __future__ import annotations


def _swallow_err(_block, _err):
    """Never-raising guard: error is swallowed by design (state module)."""
    pass


import ctypes
import threading

_cursor_x: float = 0.0
_cursor_y: float = 0.0
_initialized: bool = False
_lock = threading.Lock()
_window_offset_x: int = 0
_window_offset_y: int = 0
_scale: float = 1.0

# Windows API (optional — on other OSes the OS-cursor sync is skipped)
_SetCursorPos = None
_GetSystemMetrics = None
try:
    _user32 = ctypes.windll.user32
    _SetCursorPos = _user32.SetCursorPos
    _SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
    _GetSystemMetrics = _user32.GetSystemMetrics
except (AttributeError, OSError, ValueError):
    pass


def _detect_scale(screen_w_os: float, screen_w_css: float) -> float:
    """CSS px -> our-process screen px factor (1.0 when spaces coincide)."""
    if screen_w_os and screen_w_css and screen_w_os > 0 and screen_w_css > 0:
        return float(screen_w_os) / float(screen_w_css)
    return 1.0


def _css_to_os(x: float, y: float) -> tuple:
    """Viewport CSS px -> OS screen px for SetCursorPos."""
    return (int(round(x * _scale + _window_offset_x)),
            int(round(y * _scale + _window_offset_y)))



def get() -> tuple:
    """Текущая позиция (x, y) в координатах viewport."""
    return (_cursor_x, _cursor_y)


def set(x: float, y: float) -> None:
    """Атомарно обновить позицию + OS-курсор с учётом смещения окна."""
    global _cursor_x, _cursor_y, _initialized
    with _lock:
        _cursor_x = float(x)
        _cursor_y = float(y)
        _initialized = True
    # OS-курсор = viewport координаты, приведённые к экранным единицам
    try:
        if _SetCursorPos is not None:
            _SetCursorPos(*_css_to_os(x, y))
    except Exception as _err:        _swallow_err("cursor_state", _err)
def calibrate_window_offset(page) -> None:
    """Калибровка: scale (CSS→OS, DPI) + смещение окна через screenX/Y."""
    global _window_offset_x, _window_offset_y, _scale
    try:
        off = page.evaluate(
            "() => [window.screenX || 0, window.screenY || 0,"
            " window.screen.width || 0]"
        )
        sm_w = 0
        if _GetSystemMetrics is not None:
            sm_w = int(_GetSystemMetrics(0))  # SM_CXSCREEN в наших единицах
        css_w = float(off[2]) if off and len(off) >= 3 else 0.0
        _scale = _detect_scale(sm_w, css_w)
        _window_offset_x = int(round(float(off[0]) * _scale))
        _window_offset_y = int(round(float(off[1]) * _scale))
    except Exception as _err:        _swallow_err("cursor_state", _err)
def is_init() -> bool:
    """Был ли курсор уже инициализирован."""
    return _initialized


def init_from_viewport(page, rng=None) -> tuple:
    """Инициализировать позицию из центра viewport + jitter. + OS-курсор."""
    global _cursor_x, _cursor_y, _initialized
    calibrate_window_offset(page)
    if _initialized:
        return (_cursor_x, _cursor_y)
    import random as _random
    r = rng or _random.Random()
    try:
        vw = page.evaluate("() => window.innerWidth") or 1200
        vh = page.evaluate("() => window.innerHeight") or 800
        x = vw / 2 + r.uniform(-100, 100)
        y = vh / 2 + r.uniform(-60, 60)
    except Exception:
        x, y = 600.0, 400.0
    with _lock:
        _cursor_x = float(x)
        _cursor_y = float(y)
        _initialized = True
    try:
        if _SetCursorPos is not None:
            _SetCursorPos(*_css_to_os(x, y))
    except Exception as _err:        _swallow_err("cursor_state", _err)
    return (_cursor_x, _cursor_y)
