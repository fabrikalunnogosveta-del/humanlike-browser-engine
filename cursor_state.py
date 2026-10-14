"""
Shared cursor-position state for all humanization primitives.

Single source of truth for the virtual cursor. Invariants:
1. virtual(x,y) + window_offset(screenX, screenY) = OS cursor position.
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

# Windows API (optional — on other OSes the OS-cursor sync is skipped)
_SetCursorPos = None
try:
    _user32 = ctypes.windll.user32
    _SetCursorPos = _user32.SetCursorPos
    _SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
except (AttributeError, OSError, ValueError):
    pass


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
    # OS-курсор = viewport координаты + смещение окна браузера
    try:
        if _SetCursorPos is not None:
            _SetCursorPos(int(x) + _window_offset_x, int(y) + _window_offset_y)
    except Exception as _err:        _swallow_err("cursor_state", _err)
def calibrate_window_offset(page) -> None:
    """Вычислить смещение окна браузера от экрана через window.screenX/Y."""
    global _window_offset_x, _window_offset_y
    try:
        off = page.evaluate("() => [window.screenX || 0, window.screenY || 0]")
        if off and len(off) >= 2:
            _window_offset_x = int(off[0])
            _window_offset_y = int(off[1])
    except Exception as _err:        _swallow_err("cursor_state", _err)
def is_init() -> bool:
    """Был ли курсор уже инициализирован."""
    return _initialized


def init_from_viewport(page, rng=None) -> tuple:
    """Инициализировать позицию из центра viewport + jitter. + OS-курсор."""
    global _cursor_x, _cursor_y, _initialized
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
            _SetCursorPos(int(x), int(y))
    except Exception as _err:        _swallow_err("cursor_state", _err)
    return (_cursor_x, _cursor_y)
