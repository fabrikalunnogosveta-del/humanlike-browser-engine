"""Human-like browser engine — behavioral motion primitives.

Lognormal latencies, Bezier cursor paths with Fitts's-law targeting,
inertial wheel scrolling with decay, burst typing with keyboard-layout
distance modeling, and a 3-tier cookie-banner resolution pipeline
(CSS selectors -> semantic DOM scan; optional vision hook).

MIT License.
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
import os
import random
import time

log = logging.getLogger("humanlike_engine.distribution")

_FAST_MODE = False
_HZ_60 = 0.01667  # 60Hz frame quantum для квантования задержек
def set_fast_mode(v: bool):
    global _FAST_MODE
    _FAST_MODE = v


def _mod_key(page) -> str:
    """Meta (Cmd) на macOS, Control на всём остальном. По navigator.platform."""
    try:
        plat = (page.evaluate("() => navigator.platform || ''") or "").lower()
        return "Meta" if plat.startswith("mac") else "Control"
    except Exception:
        import sys as _sys
        return "Meta" if _sys.platform == "darwin" else "Control"


# ══════════════════════════════════════════════════════════════════════════════
# Хьюманизация (общие примитивы)
# ══════════════════════════════════════════════════════════════════════════════

def _lognormal_delay(target_mu: float, sigma: float = 0.25) -> None:
    """Логнормальная задержка с квантованием под 60Hz.

    Замена uniform — люди не распределяют паузы равномерно.
    Длинный хвост вправо: при target_mu=1.0 чаще ~1s, но бывают 1.5-2s.
    Квантование под частоту монитора (60Hz = 16.67ms фреймы).
    Минимум 4ms — ниже физиологически невозможно.
    """
    if target_mu <= 0:
        return
    adjusted = math.log(target_mu) - (sigma ** 2) / 2
    delay = random.lognormvariate(adjusted, sigma)
    delay = round(delay / _HZ_60) * _HZ_60
    time.sleep(max(delay, 0.004))


def _sleep(rng, lo: float, hi: float) -> None:
    if _FAST_MODE:
        time.sleep(0.002)
    else:
        target_mu = (lo + hi) / 2.0
        _lognormal_delay(target_mu, 0.25)


def _human_delay(rng, lo: float = 1.5, hi: float = 4.5) -> None:
    """Динамическая пауза между ВСЕМИ шагами (логнормальное распределение)."""
    _sleep(rng, lo, hi)
# ══════════════════════════════════════════════════════════════════════════════
# Cookie consent — универсальный dismiss (Google + GDPR + все баннеры)
# ══════════════════════════════════════════════════════════════════════════════

_COOKIE_SELECTORS = [
    # Google (поиск, аккаунты, YouTube)
    'button[id="L2AGLb"]',                        # Google "Accept all" (самый частый)
    'button[aria-label="Accept all"]',
    'button[aria-label="Accept everything"]',
    'button[aria-label="I agree"]',
    'button[aria-label="OK"]',
    'form[action*="consent"] button',
    'form[action*="consent"] button[type="submit"]',
    'div[role="dialog"] button:has-text("Accept all")',
    'div[role="dialog"] button:has-text("I agree")',
    # Google legacy / alternate
    'button:has-text("Accept all")',
    'button:has-text("Accept everything")',
    'button:has-text("I agree")',
    'button:has-text("Accept cookies")',
    'button:has-text("Allow all")',
    'button:has-text("Allow all cookies")',
    'button:has-text("Agree")',
    'button:has-text("OK")',
    'button:has-text("Got it")',
    'button:has-text("Accept")',
    'button:has-text("Consent")',
    'button:has-text("Yes, I accept")',
    'button:has-text("Continue to site")',
    'a:has-text("Accept all")',
    'a:has-text("I agree")',
    # GDPR generic
    'button[data-cookie*="accept"]',
    '[class*="cookie"] button[id*="accept"]',
    '[class*="cookie"] button[class*="accept"]',
    '[class*="consent"] button[class*="accept"]',
    '[id*="cookie"] button[id*="accept"]',
    '[id*="consent"] button[id*="accept"]',
    '#accept-cookies',
    '#cookie-accept',
    '#accept-all',
    '#consent-accept',
    '.accept-cookies',
    '.cookie-accept',
    '.accept-all',
    # EU-specific
    'button[aria-label*="ccept"]',
    'button[title*="ccept"]',
    # General dialog dismiss
    'div[class*="fc-consent"] button',
    'div[id*="usercentrics"] button[class*="accept"]',
    'div[id*="onetrust"] button[id*="accept"]',
]


# Слова Accept (на 14 языках) — кликаем
_ACCEPT_WORDS = [
    "accept", "accepter", "aceptar", "accetta", "akzeptieren", "accepteren",
    "agree", "accepter", "acepto", "accetto", "stimme zu", "akkoord",
    "allow", "autoriser", "permitir", "consenti", "erlauben", "toestaan",
    "ok", "okay", "got it", "compris", "entendido", "capito", "verstanden",
    "consent", "consentir", "consentir", "acconsento", "zustimmen",
    "continue", "continuer", "continuar", "continua", "fortfahren", "doorgaan",
    "close", "fermer", "cerrar", "chiudi", "schließen",
    "agree to all", "agree and", "accepter tout",
]

# Слова Reject/настроек — НЕ кликаем
_REJECT_WORDS = [
    "reject", "decline", "refuser", "rechazar", "rifiutare", "ablehnen",
    "customize", "customise", "personnaliser", "personalizar", "personalizza",
    "manage", "gérer", "gestionar", "gestisci", "verwalten", "beheren",
    "settings", "paramètres", "configuración", "impostazioni", "einstellungen",
    "only necessary", "only required", "nécessaires", "necesarias", "necessari",
    "more options", "plus", "más", "altro", "mehr", "meer",
    "preferences", "préférences", "preferencias", "preferenze", "präferenzen",
    "edit", "modifier", "editar", "modifica", "bearbeiten",
]


def _el_text(el) -> str:
    """Весь текст элемента (включая дочерние) нижним регистром."""
    try:
        t = (el.inner_text() or "").strip().lower()
        return t
    except Exception:
        return ""


def _is_accept_button(el) -> bool:
    """Элемент — кнопка Accept (не Reject/Customize/Manage)."""
    txt = _el_text(el)
    if not txt or len(txt) > 80:  # слишком длинный текст — не кнопка
        return False
    # Reject имеет приоритет: если в тексте reject-слова → НЕ кликаем
    for rw in _REJECT_WORDS:
        if rw in txt:
            return False
    for aw in _ACCEPT_WORDS:
        if aw in txt:
            return True
    return False


def _parse_page_cookie_buttons(page):
    """Спарсить ВСЕ видимые элементы на странице которые могут быть cookie-кнопкой.

    Возвращает список отсортированный по приоритету:
    - Кнопка Accept (лучшая) → просто кнопка с cookie-текстом → fallback-селектор
    """
    result = []
    try:
        if not hasattr(page, "evaluate"):
            return result
        # Парсим все кликабельные элементы с cookie/consent/gdpr текстом или атрибутами
        candidates = page.evaluate("""() => {
            const out = [];
            const els = document.querySelectorAll(
                'button, a, [role="button"], [onclick], input[type="submit"], input[type="button"]'
            );
            for (const el of els) {
                const rect = el.getBoundingClientRect();
                if (rect.width === 0 || rect.height === 0) continue;
                const style = window.getComputedStyle(el);
                if (style.visibility === 'hidden' || style.display === 'none' || style.opacity === '0') continue;
                const txt = (el.innerText || el.textContent || '').trim().substring(0, 100).toLowerCase();
                const attr = ((el.getAttribute('aria-label') || '') + ' ' +
                    (el.getAttribute('title') || '') + ' ' +
                    (el.getAttribute('id') || '') + ' ' +
                    (el.className || '')).toLowerCase();
                const tag = el.tagName.toLowerCase();
                // Ищем cookie/consent/gdpr/cookie-banner в атрибутах ИЛИ accept/agree/allow в тексте
                const combined = txt + ' ' + attr;
                const isCookieRelated = /cookie|consent|gdpr|privacy.*(?:banner|notice|popup|modal|overlay)/.test(combined);
                const isAcceptText = /accept|agree|allow|ok\b|got it|consent|continue|close/.test(txt);
                if (isCookieRelated || isAcceptText) {
                    out.push({
                        tag: tag,
                        text: txt,
                        x: rect.x, y: rect.y, w: rect.width, h: rect.height
                    });
                }
            }
            return out;
        }""")
        for c in (candidates or []):
            result.append(c)
    except Exception as _err:        _swallow_err("distribution_browser_engine", _err)
    return result


def dismiss_cookies(page, rng=None, timeout_ms: int = 3000) -> bool:
    """Семантический dismiss cookie-баннера: спарсить страницу → найти Accept-кнопку → кликнуть.

    Алгоритм:
    1. Парсим ВСЕ видимые кликабельные элементы с cookie/consent/gdpr признаками
    2. Фильтруем через _is_accept_button (Accept — да, Reject/Customize — нет)
    3. Кликаем лучший (человеческий клик с Bezier-мышью и OS-курсором)
    4. Fallback: старые селекторы если парсинг ничего не дал
    """
    if page is None or not hasattr(page, "query_selector"):
        return False
    rng = rng if rng is not None else random.Random()

    # ── Этап 1: Семантический парсинг страницы ──
    try:
        buttons = _parse_page_cookie_buttons(page)
        accept_btns = [b for b in buttons if _is_accept_button_type(b)]
        # Сортируем: короткий текст (чистая кнопка) → предпочтительнее
        accept_btns.sort(key=lambda b: len(b.get("text", "")))
        if accept_btns:
            best = accept_btns[0]
            bx, by = best.get("x", 0), best.get("y", 0)
            bw, bh = best.get("w", 50), best.get("h", 30)
            tx = bx + _fitts_click_offset(rng, bw, bh)[0]
            ty = by + _fitts_click_offset(rng, bw, bh)[1]
            _human_mouse_to(page, tx, ty, rng)
            _sleep(rng, 0.08, 0.20)
            page.mouse.click(tx, ty)
            _sleep(rng, 0.3, 0.7)
            log.debug("dismiss_cookies: semantic click '%s'", best.get("text", "")[:50])
            return True
    except Exception as e:
        log.debug("dismiss_cookies semantic: %s", e)

    # ── Этап 2: Fallback — CSS-селекторы (с проверкой Accept/Reject) ──
    try:
        for sel in _COOKIE_SELECTORS:
            try:
                el = page.query_selector(sel)
                if el and el.is_visible():
                    if not _is_accept_button(el):
                        continue  # это Reject/Customize → пропускаем
                    _human_delay(rng, 0.15, 0.45)
                    _human_click_element(page, el, rng)
                    _sleep(rng, 0.3, 0.7)
                    log.debug("dismiss_cookies: selector click %s", sel)
                    return True
            except Exception:
                continue
    except Exception as e:
        log.debug("dismiss_cookies: %s", e)
    return False
def _is_accept_button_type(btn: dict) -> bool:
    """Проверка словаря (из _parse_page_cookie_buttons) — Accept или нет."""
    txt = (btn.get("text") or "").lower().strip()
    if not txt or len(txt) > 80:
        return False
    for rw in _REJECT_WORDS:
        if rw in txt:
            return False
    for aw in _ACCEPT_WORDS:
        if aw in txt:
            return True
    return False
class BrowserClosedError(Exception):
    """Браузер закрыт — неустранимая ошибка, требуется перезапуск сессии."""
    pass
from cursor_state import get as _cursor_get, set as _cursor_set, is_init as _cursor_is_init, init_from_viewport as _cursor_init, calibrate_window_offset as _cursor_calibrate
_cursor_x = 600.0
_cursor_y = 400.0


def _ensure_cursor_state(page, rng) -> None:
    """Force cursor to center viewport if unset or stuck at origin (0,0 = tab bar)."""
    try:
        if _cursor_is_init():
            cx, cy = _cursor_get()
            if cx == 0 and cy == 0:
                raise ValueError("Cursor stuck at origin (tab bar)")
            return
    except Exception as _err:        _swallow_err("distribution_browser_engine", _err)
    try:
        vw = page.evaluate("() => window.innerWidth") or 1280
        vh = page.evaluate("() => window.innerHeight") or 720
        _cursor_calibrate(page)  # DPI/offset: первый set() должен знать масштаб
        init_x = vw * (0.5 if rng is None else rng.uniform(0.4, 0.6))
        init_y = vh * (0.5 if rng is None else rng.uniform(0.4, 0.6))
        _cursor_set(init_x, init_y)
        page.mouse.move(init_x, init_y)
    except Exception:
        _cursor_set(600, 400)


def _micro_sleep(page, rng, lo: float, hi: float) -> None:
    """Сон с микро-дыханием курсора: каждые 0.5-1.5s — микро-сдвиг 0.3-1.5px.

    Реальный человек никогда не держит мышь идеально неподвижно — рука микро-дрожит.
    Анти-боты детектят «замороженный» курсор во время пауз чтения.
    """
    if _FAST_MODE:
        _sleep(rng, 0.01, 0.02)
        return
    total = random.lognormvariate(math.log((lo + hi) / 2.0), 0.25)
    total = max(lo, min(hi, total))
    elapsed = 0.0
    while elapsed < total:
        chunk = min(total - elapsed, random.lognormvariate(math.log(0.8), 0.25))
        time.sleep(max(chunk, 0.004))
        elapsed += chunk
        # Микро-дрожание: 0.3-1.5px в случайную сторону
        if rng.random() < 0.7:
            try:
                dx = rng.uniform(-1.5, 1.5)
                dy = rng.uniform(-1.5, 1.5)
                page.mouse.move(
                    (_cursor_x or 600) + dx,
                    (_cursor_y or 400) + dy
                )
            except Exception as _err:                _swallow_err("distribution_browser_engine", _err)
_focus_ok_ts = 0.0  # monotonic ts of last verified focus (3s success cache)


def _ensure_tab_focus(page, rng=None) -> bool:
    """Check document.hasFocus() + visibilityState. NO programmatic focus() — isTrusted:false.

    If focus is lost: physical mouse click on page body generates native events
    (isTrusted: true) that trigger focus via OS-level input, undetectable by anti-fraud.
    No bring_to_front(), no document.body.focus(), no programmatic tab switches.
    Time-budgeted: deadline ~2s (checked every iteration, worst-case walk to
    it ≈2.6s with retry pacing) + 3s success cache — a lost-focus loop must
    never block the input path for ~90s (old: 20 retries x ~4.5s sleep).
    """
    global _focus_ok_ts
    import time as _t
    r = rng or random.Random()
    try:
        if not hasattr(page, "evaluate"):
            return True

        now = _t.monotonic()
        if now - _focus_ok_ts < 3.0:
            return True
        deadline = now + 2.0

        for attempt in range(20):
            if _t.monotonic() >= deadline:
                return False
            try:
                state = page.evaluate("""() => ({
                    visible: document.visibilityState === 'visible',
                    focused: document.hasFocus(),
                })""")
            except Exception:
                return True

            if state.get("visible") and state.get("focused"):
                _focus_ok_ts = _t.monotonic()
                return True

            if attempt == 0:
                # Physical click on page body — native events, isTrusted:true
                # NOT document.body.focus() — that's programmatic, isTrusted:false
                try:
                    vw = page.evaluate("() => window.innerWidth") or 1280
                    vh = page.evaluate("() => window.innerHeight") or 720
                    # Click near center-left (safe zone — no menus, no ads)
                    sx = _cursor_get()[0] if callable(_cursor_get) else vw * 0.35
                    sy = _cursor_get()[1] if callable(_cursor_get) else vh * 0.45
                    # Small movement → click (generates mousedown/mouseup/click chain)
                    page.mouse.move(sx + r.uniform(-30, 30), sy + r.uniform(-20, 20), steps=3)
                    _t.sleep(r.uniform(0.03, 0.08))
                    page.mouse.click(sx, sy)
                    _t.sleep(r.uniform(0.05, 0.10))
                except Exception as _err:                    _swallow_err("distribution_browser_engine", _err)
            if _t.monotonic() >= deadline:
                return False
            _lognormal_delay(0.8, 0.30)  # retry pacing inside the 2s budget

        return False
    except Exception:
        return True


def _fitts_click_offset(rng, width: float = 200, height: float = 40) -> tuple:
    """Двумерное нормальное распределение клика по закону Фиттса: σ = W/6.

    Реальный человек целится в геометрический центр, но из-за моторного шума
    распределение Гауссово: X ~ N(cx, (W/6)²), Y ~ N(cy, (H/6)²).
    Clamp к границам элемента (5% отступ от краёв).
    """
    import math as _m
    cx, cy = width / 2, height / 2
    ox = cx + rng.gauss(0, width / 6.0)
    oy = cy + rng.gauss(0, height / 6.0)
    ox = max(width * 0.05, min(width * 0.95, ox))
    oy = max(height * 0.05, min(height * 0.95, oy))
    return ox, oy


def _human_mouse_to(page, x: float, y: float, rng, tremor_px: float = None) -> None:
    """CURSOR 1:1 BINDING — OS cursor ALWAYS synced with virtual position.
    IRON RULE: _cursor_set(x,y) after EVERY movement. Never decouple.
    Every page.mouse.click() MUST be preceded by _human_mouse_to() to same coords."""
    if not hasattr(page, "mouse"):
        return
    _ensure_tab_focus(page, rng)
    _ensure_cursor_state(page, rng)
    sx, sy = _cursor_get()

    # ── БАРЬЕР №1: target (0,0) или near-zero → ABORT, don't redirect to random ──
    if (abs(x) < 5 and abs(y) < 5):
        log.warning("[mouse] target (%.1f, %.1f) near-zero — element finder failed, aborting move", x, y)
        return  # don't move to random position, caller should handle empty result

    # ── БАРЬЕР №2: target совпадает с текущей позицией → сдвиг ──
    dist_to_target = ((x - sx) ** 2 + (y - sy) ** 2) ** 0.5
    if dist_to_target < 15:
        x += rng.uniform(40, 120) * (1 if rng.random() > 0.5 else -1)
        y += rng.uniform(20, 60) * (1 if rng.random() > 0.5 else -1)

    try:
        from bezier_mouse import bezier_path, _step_delays
        _profile = {"tremor_px": tremor_px} if tremor_px is not None else None
        pts = bezier_path(sx, sy, x, y, rng=rng, profile=_profile)
        delays = _step_delays(len(pts), None, rng)
        # DNA kinematics injection
        try:
            from behavior_engine import apply_kinematics
            delays = apply_kinematics(delays, x - sx, y - sy, dist_to_target, page=page, rng=rng)
        except Exception as _err:            _swallow_err("distribution_browser_engine", _err)
        for (px, py), d in zip(pts, delays):
            page.mouse.move(px, py)
            if not _FAST_MODE:
                time.sleep(d)
        _cursor_set(x, y)
    except Exception:
        try:
            page.mouse.move(x, y)
            _cursor_set(x, y)
        except Exception as _err:            _swallow_err("distribution_browser_engine", _err)
def _human_click_element(page, element, rng, profile=None, fatigue=None) -> bool:
    """Fitts-клик по элементу: Bezier-движение + OS-курсор + физический клик с duration.

    БЛОК 1 (Тотальная хьюманизация мыши):
    - Overshoot 15-20% (из profile.overshoot_chance), когнитивная пауза 100-250ms перед коррекцией
    - Click duration 60-180ms: mousedown → пауза (глубина нажатия) → mouseup
    - Gaussian распределение точки клика (Fitts)
    - Path-error 5%: отклонение в середине траектории
    """
    if element is None:
        return False
    _ensure_tab_focus(page, rng)
    try:
        box = element.bounding_box()
        if not box:
            return False
        ox, oy = _fitts_click_offset(rng, box["width"], box["height"])
        tx, ty = box["x"] + ox, box["y"] + oy

        # ── Viewport calibration: scroll if target is outside visible area ──
        scrolled = False
        try:
            vp = page.viewport_size or {"width": 1024, "height": 768}
            if ty > vp["height"] * 0.85:
                page.mouse.wheel(0, ty - vp["height"] * 0.45)
                _sleep(rng, 0.15, 0.35)
                scrolled = True
            elif ty < vp["height"] * 0.10:
                page.mouse.wheel(0, ty - vp["height"] * 0.45)
                _sleep(rng, 0.15, 0.35)
                scrolled = True
        except Exception as _err:            _swallow_err("distribution_browser_engine", _err)
        if scrolled:
            # The scroll moved the element — the pre-scroll bbox/tx/ty are stale
            # and the click would land off-target. Re-read before moving.
            try:
                box2 = element.bounding_box()
                if box2:
                    box = box2
                    ox, oy = _fitts_click_offset(rng, box["width"], box["height"])
                    tx, ty = box["x"] + ox, box["y"] + oy
                else:
                    # Element detached/hidden during the scroll — clicking the
                    # stale coordinates could hit a different element.
                    return False
            except Exception as _err:
                _swallow_err("distribution_browser_engine", _err)
                return False  # re-read failed → stale coords are not clickable
        # Clamp к bbox ±2px чтобы не уйти за пределы элемента
        path_error = rng.random() < 0.05
        if path_error:
            mid_x = tx + rng.uniform(15, 30) * (1 if rng.random() > 0.5 else -1)
            mid_y = ty + rng.uniform(10, 20) * (1 if rng.random() > 0.5 else -1)
            mid_x = max(box["x"] - 2, min(box["x"] + box["width"] + 2, mid_x))
            mid_y = max(box["y"] - 2, min(box["y"] + box["height"] + 2, mid_y))
            _tr = fatigue.current_tremor_sigma if fatigue else None
            _human_mouse_to(page, mid_x, mid_y, rng, tremor_px=_tr)
            _sleep(rng, 0.08, 0.15)
            _human_mouse_to(page, tx, ty, rng, tremor_px=_tr)
        else:
            _tr = fatigue.current_tremor_sigma if fatigue else None
            _human_mouse_to(page, tx, ty, rng, tremor_px=_tr)
        _sleep(rng, 0.05, 0.20)

        # Overshoot: 15-20% шанс (из profile или дефолт 18%)
        # Fatigue scaling: current_overshoot_px растёт со временем сессии
        overshoot_ch = 0.18
        overshoot_scale = 1.0
        if profile is not None:
            overshoot_ch = getattr(profile, 'overshoot_chance', 0.18) if not isinstance(profile, dict) else profile.get('overshoot_chance', 0.18)
        if fatigue is not None:
            overshoot_ch = min(0.35, overshoot_ch + fatigue.current_overshoot_px * 0.01)
            overshoot_scale = max(1.0, fatigue.current_overshoot_px / max(0.1, getattr(fatigue, 'base_overshoot_px', 2.0)))
        if rng.random() < overshoot_ch:
            _ov_base = rng.uniform(5, 12) * overshoot_scale
            overshoot_x = tx + _ov_base * (1 if rng.random() > 0.5 else -1)
            overshoot_y = ty + rng.uniform(3, 8) * overshoot_scale * (1 if rng.random() > 0.5 else -1)
            page.mouse.move(overshoot_x, overshoot_y)
            # Когнитивная пауза 100-250ms (осознал промах)
            _sleep(rng, 0.10, 0.25)
            # Медленный возврат на цель (2-3 шага)
            for _ in range(rng.randint(2, 3)):
                ix = overshoot_x + (tx - overshoot_x) * rng.uniform(0.3, 0.7)
                iy = overshoot_y + (ty - overshoot_y) * rng.uniform(0.3, 0.7)
                page.mouse.move(ix, iy)
                _sleep(rng, 0.04, 0.10)
            page.mouse.move(tx, ty)
            _sleep(rng, 0.05, 0.12)

        # Click duration: mousedown → пауза 60-180ms (глубина нажатия) → mouseup
        click_lo, click_hi = 60, 180
        if profile is not None:
            if isinstance(profile, dict):
                cd = profile.get('click_duration_ms', [60, 180])
            else:
                cd = getattr(profile, 'click_duration_ms', [60, 180])
            click_lo, click_hi = cd[0], cd[1]
        page.mouse.move(tx, ty)
        page.mouse.down()
        # Ghosting: 4% extra mousedown time
        try:
            from behavior_engine import should_ghost, ghost_extra_ms
            if should_ghost(rng):
                _sleep(rng, ghost_extra_ms(rng)/1000.0, ghost_extra_ms(rng)/1000.0*1.3)
        except Exception as _err:            _swallow_err("distribution_browser_engine", _err)
        _sleep(rng, click_lo / 1000.0, click_hi / 1000.0)
        page.mouse.up()
        # Double-click: 15% for nervous personas
        try:
            from behavior_engine import should_double_click
            if should_double_click(rng):
                _sleep(rng, 0.15, 0.35)
                page.mouse.down()
                _sleep(rng, 0.06, 0.14)
                page.mouse.up()
        except Exception as _err:            _swallow_err("distribution_browser_engine", _err)
        global _cursor_x, _cursor_y
        _cursor_x, _cursor_y = float(tx), float(ty)
        return True
    except Exception:
        return False
# ══════════════════════════════════════════════════════════════════════════════
# Locale-Aware Keyboard Layout Engine (P2 — QWERTY/QWERTZ/AZERTY)
# ══════════════════════════════════════════════════════════════════════════════
# Каждая раскладка: {char: (col, row)} — физические координаты на клавиатуре.
# Flight time = f(euclidean_distance(key1, key2, layout)) + dwell(50-120ms).
# Немец на QWERTZ печатает Z быстрее Y, француз на AZERTY A медленнее Z.
# Разные тайминги на ОДНИХ И ТЕХ ЖЕ буквах — Google Identity триггер.
#
# Схема индексации: _KEYBOARD_GRID[locale_prefix] → coord_map
# locale_prefix из persona.locale (первые 2 символа lowercase): en→QWERTY,
# de→QWERTZ, fr→AZERTY. Fallback = QWERTY.

_QWERTY_GRID = {
    # Row 0 (цифры+спец): ` 1 2 3 4 5 6 7 8 9 0 - =
    '`': (0, 0), '1': (1, 0), '2': (2, 0), '3': (3, 0), '4': (4, 0),
    '5': (5, 0), '6': (6, 0), '7': (7, 0), '8': (8, 0), '9': (9, 0),
    '0': (10, 0), '-': (11, 0), '=': (12, 0),
    # Row 1: Tab q w e r t y u i o p [ ] \
    'q': (0.5, 1), 'w': (1.5, 1), 'e': (2.5, 1), 'r': (3.5, 1), 't': (4.5, 1),
    'y': (5.5, 1), 'u': (6.5, 1), 'i': (7.5, 1), 'o': (8.5, 1), 'p': (9.5, 1),
    '[': (10.5, 1), ']': (11.5, 1), '\\': (12.5, 1),
    # Row 2: CapsLock a s d f g h j k l ; '
    'a': (1.0, 2), 's': (2.0, 2), 'd': (3.0, 2), 'f': (4.0, 2), 'g': (5.0, 2),
    'h': (6.0, 2), 'j': (7.0, 2), 'k': (8.0, 2), 'l': (9.0, 2), ';': (10.0, 2),
    "'": (11.0, 2),
    # Row 3: Shift z x c v b n m , . / Shift
    'z': (1.5, 3), 'x': (2.5, 3), 'c': (3.5, 3), 'v': (4.5, 3), 'b': (5.5, 3),
    'n': (6.5, 3), 'm': (7.5, 3), ',': (8.5, 3), '.': (9.5, 3), '/': (10.5, 3),
    # Row 4: Space
    ' ': (5.0, 4),
}

_QWERTZ_GRID = {
    # QWERTZ (de_DE/de_CH): Y↔Z swap vs QWERTY, umlauts ö/ä/ü, ß
    # Row 0: ^ 1 2 3 4 5 6 7 8 9 0 ß ´
    '^': (0, 0), '1': (1, 0), '2': (2, 0), '3': (3, 0), '4': (4, 0),
    '5': (5, 0), '6': (6, 0), '7': (7, 0), '8': (8, 0), '9': (9, 0),
    '0': (10, 0), 'ß': (11, 0), '´': (12, 0),
    # Row 1: Tab q w e r t z u i o p ü +
    'q': (0.5, 1), 'w': (1.5, 1), 'e': (2.5, 1), 'r': (3.5, 1), 't': (4.5, 1),
    'z': (5.5, 1), 'u': (6.5, 1), 'i': (7.5, 1), 'o': (8.5, 1), 'p': (9.5, 1),
    'ü': (10.5, 1), '+': (11.5, 1),
    # Row 2: CapsLock a s d f g h j k l ö ä #
    'a': (1.0, 2), 's': (2.0, 2), 'd': (3.0, 2), 'f': (4.0, 2), 'g': (5.0, 2),
    'h': (6.0, 2), 'j': (7.0, 2), 'k': (8.0, 2), 'l': (9.0, 2), 'ö': (10.0, 2),
    'ä': (11.0, 2), '#': (12.0, 2),
    # Row 3: Shift < y x c v b n m , . - Shift
    '<': (0.5, 3), 'y': (1.5, 3), 'x': (2.5, 3), 'c': (3.5, 3), 'v': (4.5, 3),
    'b': (5.5, 3), 'n': (6.5, 3), 'm': (7.5, 3), ',': (8.5, 3), '.': (9.5, 3),
    '-': (10.5, 3),
    # Row 4: Space
    ' ': (5.0, 4),
}

# de_CH: same as de_DE but no ß (uses ss), has special chars: è é à
_QWERTZ_CH_GRID = dict(_QWERTZ_GRID)
_QWERTZ_CH_GRID.update({
    'è': (11.0, 0), 'é': (12.0, 0),  # Row 0: è é replace ß ´
    'à': (11.5, 1),                    # Row 1: à replace +
    '$': (12.0, 2),                    # Row 2: $ replace #
})

_AZERTY_GRID = {
    # AZERTY (fr_FR/fr_BE): A↔Q swap, W↔Z swap, M moved to row 2, digits need Shift
    # Row 0: ` 1 2 3 4 5 6 7 8 9 0 - =
    '`': (0, 0), '1': (1, 0), '2': (2, 0), '3': (3, 0), '4': (4, 0),
    '5': (5, 0), '6': (6, 0), '7': (7, 0), '8': (8, 0), '9': (9, 0),
    '0': (10, 0), '-': (11, 0), '=': (12, 0),
    # Row 1: Tab a z e r t y u i o p ^ $
    'a': (0.5, 1), 'z': (1.5, 1), 'e': (2.5, 1), 'r': (3.5, 1), 't': (4.5, 1),
    'y': (5.5, 1), 'u': (6.5, 1), 'i': (7.5, 1), 'o': (8.5, 1), 'p': (9.5, 1),
    '^': (10.5, 1), '$': (11.5, 1),
    # Row 2: CapsLock q s d f g h j k l m ù enter
    'q': (1.0, 2), 's': (2.0, 2), 'd': (3.0, 2), 'f': (4.0, 2), 'g': (5.0, 2),
    'h': (6.0, 2), 'j': (7.0, 2), 'k': (8.0, 2), 'l': (9.0, 2), 'm': (10.0, 2),
    'ù': (11.0, 2),
    # Row 3: Shift w x c v b n , ; : ! Shift
    'w': (1.5, 3), 'x': (2.5, 3), 'c': (3.5, 3), 'v': (4.5, 3), 'b': (5.5, 3),
    'n': (6.5, 3), ',': (7.5, 3), ';': (8.5, 3), ':': (9.5, 3), '!': (10.5, 3),
    # Row 4: Space
    ' ': (5.0, 4),
}

# fr_BE: Belgian AZERTY — minor accent diffs
_AZERTY_BE_GRID = dict(_AZERTY_GRID)
_AZERTY_BE_GRID.update({
    '$': (11.5, 1),  # Row 1: $ at end
    'é': (12.0, 2),  # Row 2: é
    'è': (12.5, 3),  # Row 3: è
})

# Локаль → раскладка
_LAYOUT_INDEX = {
    'en': _QWERTY_GRID,       # en_US, en_GB, en_CA, en_AU
    'de': _QWERTZ_GRID,       # de_DE
    'ch': _QWERTZ_CH_GRID,    # de_CH (Swiss German)
    'fr': _AZERTY_GRID,       # fr_FR
    'be': _AZERTY_BE_GRID,    # fr_BE (Belgian French)
}

# Построить neighbours per-layout (символы на расстоянии < 1.5 единиц)
_NEIGHBORS_BY_LAYOUT = {}
for _layout_name, _grid in _LAYOUT_INDEX.items():
    _nbrs = {}
    for _k, (kx, ky) in _grid.items():
        _nbrs[_k] = ''.join(c for c, (cx, cy) in _grid.items()
                           if c != _k and ((cx - kx)**2 + (cy - ky)**2) < 1.6**2)
        _nbrs[_k.upper()] = _nbrs[_k].upper()
    _NEIGHBORS_BY_LAYOUT[_layout_name] = _nbrs

# Обратная совместимость: QWERTY neighbours (для кода который ещё не мигрировал)
_QWERTY_NEIGHBORS = _NEIGHBORS_BY_LAYOUT['en']


def _resolve_keyboard_layout(locale: str = "") -> str:
    """locale='en_GB' → 'en', 'de_DE' → 'de', 'fr_FR' → 'fr', 'de_CH' → 'ch'.
    Неизвестный locale → 'en' (QWERTY fallback)."""
    if not locale:
        return 'en'
    lo = locale.lower().strip()
    # fr_BE → 'be'
    if lo.startswith('fr_be'):
        return 'be'
    # de_CH → 'ch'
    if lo.startswith('de_ch'):
        return 'ch'
    cc = lo[:2]
    return cc if cc in _LAYOUT_INDEX else 'en'


def _keyboard_distance(c1: str, c2: str, locale: str = "en") -> float:
    """Евклидово расстояние между клавишами в указанной раскладке."""
    grid = _LAYOUT_INDEX.get(_resolve_keyboard_layout(locale), _QWERTY_GRID)
    p1 = grid.get(c1.lower())
    p2 = grid.get(c2.lower())
    if p1 is None or p2 is None:
        return 2.5  # среднее при неизвестном символе
    return math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2)


def _keyboard_neighbors(char: str, locale: str = "en") -> str:
    """Соседние клавиши для burst-mode в указанной раскладке."""
    layout = _resolve_keyboard_layout(locale)
    nbrs = _NEIGHBORS_BY_LAYOUT.get(layout, _NEIGHBORS_BY_LAYOUT['en'])
    return nbrs.get(char, '')


def _human_paste_long_text(page, text: str, rng) -> None:
    """Ctrl+V с реальным буфером ОС + физической последовательностью клавиш (V3).

    Порядок: pyperclip → буфер ОС → когнитивная пауза → Control down → pause →
    v down → v up → Control up. НИКАКОГО navigator.clipboard.writeText (sandbox).
    """
    import pyperclip as _clip
    mod = _mod_key(page)
    try:
        _clip.copy(text)
    except Exception:
        page.keyboard.insert_text(text)
        _sleep(rng, 0.4, 0.9)
        return

    _sleep(rng, 0.10, 0.30)  # когнитивная пауза перед вставкой

    # Физическая последовательность: зажать модификатор → нажать v → отпустить v → отпустить модификатор
    try:
        page.keyboard.down(mod)
        _sleep(rng, 0.03, 0.07)
        page.keyboard.down("v")
        _sleep(rng, 0.02, 0.05)
        page.keyboard.up("v")
        _sleep(rng, 0.02, 0.04)
        page.keyboard.up(mod)
    except Exception:
        try:
            page.keyboard.press(f"{mod}+v")
        except Exception:
            page.keyboard.insert_text(text)

    _sleep(rng, 0.4, 0.9)
    # Микро-форматирование после вставки (15% шанс): поправить 1-2 символа в начале
    if rng.random() < 0.15 and len(text) > 100:
        page.keyboard.press("Home")
        _sleep(rng, 0.08, 0.15)
        for _ in range(rng.randint(0, 2)):
            page.keyboard.press("ArrowRight")
            _sleep(rng, 0.04, 0.08)
        page.keyboard.press("Backspace")
        _sleep(rng, 0.05, 0.10)
        page.keyboard.press(text[min(rng.randint(0, min(5, len(text) - 1)), len(text) - 1)])
        _sleep(rng, 0.1, 0.2)


# Bigram muscle memory — Tier 1 languages (YouTube priority: EN, ES, IT, DE, FR, RU, NL, SV, NO, DA, FI, JA, KO)
_FAST_BIGRAMS_EN = {"th","he","in","er","an","re","nd","at","on","nt","ha","es","st","en","ed","to","it","ou","ea","hi","is","or","ti","as","te","et","ng","of","al","de","se","le","sa","si","ar","ve","ra","ld","ur"}
_FAST_BIGRAMS_ES = {"de","es","en","el","la","os","as","ue","ra","se","er","te","al","ar","or","ci","co","ta","me","un","do","ca","ad","pr","tr","an","ie","io","qu","no","pa","ro","ma","da","re","na","li","to"}
_FAST_BIGRAMS_IT = {"di","la","il","un","pe","no","si","ma","te","al","re","co","ra","se","ti","to","ol","st","pr","tr","zi","io","ia","ca","ci","gi","ni","li","ta","ri","ne","vi","mo","pa"}
_FAST_BIGRAMS_DE = {"en","er","ch","ei","ie","un","be","te","sc","he","it","de","au","se","le","re","nd","ng","in","ge","an","ar","ic","el","me","no","li","ta","si","ve","ha","ma","ne","da","la","na","kt","os"}
_FAST_BIGRAMS_FR = {"de","le","es","en","re","on","er","an","ou","la","nt","ur","ai","it","ne","se","et","ed","em","co","qu","io","ue","el","pe","ce","so","me","te","is","ir","su","ch","po","ve","pa","nd"}
_FAST_BIGRAMS_RU = {"ст","но","ен","то","на","во","ор","ко","ер","по","ро","ал","ра","пр","ос","ни","тр","он","де","ве","ла","ре","ка","че","ли","ть","го","от","не","за","из","ми","ан","до","се","ло","та","ри","бо","ем"}
_ALL_FAST_BIGRAMS = _FAST_BIGRAMS_EN | _FAST_BIGRAMS_ES | _FAST_BIGRAMS_IT | _FAST_BIGRAMS_DE | _FAST_BIGRAMS_FR | _FAST_BIGRAMS_RU

# Trigrams — 3-letter muscle memory chains (brain types as single impulse: 12-28ms)
_FAST_TRIGRAMS = {
    # EN
    "the","ing","and","ion","ent","for","tio","has","edt","men","pro","thi","ght","all","ter",
    "hat","ver","ere","est","his","one","res","she","nce","our","you","rea","ect","ess","oun",
    # ES
    "que","del","las","por","los","con","una","est","ado","nte","res","ara","ien","tra","des",
    "cio","com","sta","era","ste","pre","pres","ser","tan","ten","dad","cio","mbi","nte",
    # IT
    "che","del","per","non","una","deg","com","sta","tra","men","tto","lla","ssi","nti","are",
    "gli","tti","lle","zzi","gga","sco","sse","dov","que","ssa","mbi","nte",
    # DE
    "ich","ein","cht","gen","gru","abe","dur","sse","wie","sie","hat","tze","ube","rbe","nge",
    "che","cht","sch","eit","ste","ten","ung","ach","and","ode","aus","hre","lle","run",
    # FR
    "que","les","des","ent","ant","our","ans","tre","est","lle","ire","ait","ont","eme","une",
    "pas","ait","ont","sse","pre","nde","nce","lle","tio","men","par","tou","rs",
    # RU
    "что","как","это","все","или","про","при","сто","его","был","ска","ние","ает","ест",
    "стр","его","ать","ные","оль","ост","вно","ени","ете","али","ова","ств",
}

def _human_burst_type(page, text: str, rng, wpm: int = 58, el=None,
                      tab_first: bool = None, locale: str = "en",
                      fatigue: "SessionFatigueTracker | None" = None) -> None:
    """Burst-печать с locale-aware QWERTY/QWERTZ/AZERTY раскладкой (P2).
    fatigue: SessionFatigueTracker -> деградированный WPM и typo_rate (P3).
    """
    # DNA-driven WPM
    try:
        from dna_humanizer import _active as _dh
        if _dh: wpm = _dh.random_wpm()
    except Exception as _err:        _swallow_err("distribution_browser_engine", _err)
    if not text or not hasattr(page, "keyboard"):
        return
    _ensure_tab_focus(page, rng)
    # Длинные тексты → Ctrl+V (человек не печатает 150+ символов вручную в форму)
    if len(text) > 150:
        _human_paste_long_text(page, text, rng)
        _sleep(rng, 0.8, 2.0)
        return
    # Фокус: Tab (40%) или клик мыши (60%) с задержкой 1.2-3.5s
    if el is not None:
        if tab_first is None:
            tab_first = rng.random() < 0.4
        try:
            if tab_first:
                page.keyboard.press("Tab")
            else:
                el.click()
                el.focus()
            _sleep(rng, 1.2, 3.5)  # переход между полями
        except Exception as _err:            _swallow_err("distribution_browser_engine", _err)
    _sleep(rng, 0.15, 0.55)  # нашел поле, подвинул руку

    # P3: fatigue-деградированные параметры
    _active_wpm = wpm
    _active_typo_chance = 0.03
    if fatigue is not None:
        _active_wpm = fatigue.current_wpm
        _active_typo_chance = fatigue.current_typo_rate

    chars = list(text)
    i = 0
    base_ms = max(110, min(280, 12000 / (max(15, _active_wpm) * 5)))
    _typo_counter = 0  # счётчик символов для опечаток
    _layout_id = _resolve_keyboard_layout(locale)
    _grid = _LAYOUT_INDEX.get(_layout_id, _QWERTY_GRID)
    # Клавиши на этой раскладке для генерации опечаток
    _all_keys = [k for k in _grid if len(k) == 1 and k.isalpha()]

    while i < len(chars):
        burst = rng.randint(2, 4)
        for _ in range(burst):
            if i >= len(chars):
                break

            # P2+P3: locale-aware typo с fatigue-шансом
            _typo_counter += 1
            if _typo_counter >= 50 and rng.random() < _active_typo_chance:
                _typo_counter = 0
                wrong = rng.choice(_all_keys) if _all_keys else rng.choice("qwertyuiopasdfghjkl")
                page.keyboard.press(wrong)           # неверный символ
                _sleep(rng, 0.04, 0.08)
                if i < len(chars):
                    # Inertia keystroke: it and the wrong key are erased by the
                    # two Backspaces below. i is NOT advanced here — the normal
                    # path retypes chars[i], otherwise every triggered typo
                    # silently drops one correct character from the text.
                    page.keyboard.press(chars[i])
                _sleep(rng, 0.20, 0.30)              # пауза 200-300ms (осознание)
                page.keyboard.press("Backspace")      # Backspace ×2
                _sleep(rng, 0.06, 0.10)
                page.keyboard.press("Backspace")
                _sleep(rng, 0.12, 0.18)              # пауза 120-180ms после стирания

            # P2: locale-aware keyboard distance → flight time
            ch = chars[i]
            prev_ch = chars[i - 1] if i > 0 else ''
            dist = _keyboard_distance(prev_ch, ch, locale)
            # median flight: 35ms при dist=1 (соседи), ~55ms при dist=2.5 (далёкие)
            flight_ms = rng.lognormvariate(-3.35 + dist * 0.12, 0.22 + dist * 0.02)
            flight_ms = max(0.015, min(0.35, flight_ms))

            # Bigram + trigram muscle memory checks
            _pair = prev_ch.lower() + ch.lower()  # 2-char sequence
            _triplet = ""
            if i + 1 < len(chars):
                _triplet = (prev_ch.lower() + ch.lower() + chars[i+1].lower())
            if _triplet and _triplet in _FAST_TRIGRAMS:
                flight_ms = rng.uniform(0.012, 0.028)  # single impulse — fastest
            # Bigram muscle memory: common pairs typed 30-50ms flat
            elif _pair in _ALL_FAST_BIGRAMS:
                flight_ms = rng.uniform(0.018, 0.038)  # muscle memory — fast
            else:
                # Cross-hand latency: different hands = faster, same hand = slower
                _left_hand = set('qwertasdfgzxcvb')
                _right_hand = set('yuiophjklbnm')
                prev_is_left = prev_ch.lower() in _left_hand
                curr_is_left = ch.lower() in _left_hand
                prev_is_right = prev_ch.lower() in _right_hand
                curr_is_right = ch.lower() in _right_hand
                if (prev_is_left and curr_is_right) or (prev_is_right and curr_is_left):
                    flight_ms *= 0.75  # different hands = 25% faster
                elif prev_is_left == curr_is_left:
                    flight_ms *= 1.15  # same hand = 15% slower

            # Dwell Time (6): keydown -> 50-120ms -> keyup
            page.keyboard.down(ch)
            _sleep(rng, 0.05, 0.12)     # dwell: палец держит клавишу
            page.keyboard.up(ch)
            time.sleep(max(0.015, min(0.35, flight_ms)))  # flight: палец летит к следующей
            i += 1

        if i >= len(chars):
            break
        # Когнитивная пауза: конец предложения > пробел > прочее (2.5)
        prev = chars[i - 1]
        if prev in ('.', '!', '?'):
            _sleep(rng, 0.40, 0.80)   # конец предложения
        elif prev in (' ', '\n'):
            _sleep(rng, 0.30, 0.70)   # между словами
        else:
            _sleep(rng, 0.04, 0.15)   # внутри burst

    # Пауза после окончания ввода (человек перечитывает)
    _sleep(rng, 0.8, 2.0)
def _plan_inertial_steps(total: float, num_steps: int, rng, cap: int = 80) -> list:
    """Decay-shaped step plan whose steps sum to `total` (±1-2px rounding).

    Front-loaded weights (strong flick + micro-adjustments) are normalized to
    sum to 1 before slicing the total — computing each step from the shrinking
    remainder (old code) delivered only ~53% of the requested scroll. Per-step
    values are soft-capped at `cap` px with overflow pushed to later steps;
    `num_steps` grows for large deltas (so the cap can hold the whole
    distance) and shrinks for tiny ones (each step is at least 2px).
    """
    num_steps = max(num_steps, int(math.ceil(total / max(1, cap - 10))) + 1)
    num_steps = max(2, min(num_steps, int(total) // 2 or 2))  # ≥2px/step floor
    frs = [0.35 * math.exp(-3.5 * (j / max(1, num_steps - 1))) + 0.02
           for j in range(num_steps)]
    frs = [f * (1.0 + rng.uniform(-0.15, 0.15)) for f in frs]
    scale = total / max(sum(frs), 1e-9)
    px = [f * scale for f in frs]
    for i in range(len(px) - 1):
        if px[i] > cap:
            overflow = px[i] - cap
            px[i] = float(cap)
            for j in range(i + 1, len(px)):
                room = cap - px[j]
                if room <= 0:
                    continue
                take = min(room, overflow)
                px[j] += take
                overflow -= take
                if overflow <= 1e-9:
                    break
            if overflow > 1e-9:  # cap cannot hold total — tail takes the rest
                px[-1] += overflow
                break
    out = [max(2, int(round(v))) for v in px]
    # Spread rounding drift across steps (a single last-step correction cannot
    # absorb it: every step has a 2px floor, so the tail may have no room).
    drift = int(round(total)) - sum(out)
    k = len(out) - 1
    while drift > 0 and k >= 0:
        out[k] += 1
        drift -= 1
        k -= 1
    k = len(out) - 1
    while drift < 0 and k >= 0:
        if out[k] > 2:
            out[k] -= 1
            drift += 1  # stay on this step — it may have more headroom
        else:
            k -= 1
    return out


def _human_inertial_wheel(page, total_delta_y: float, rng, num_steps: int = None) -> None:
    """Scroll Decay Engine with post-hoc CDP hang detection.

    The step plan is normalized so the steps sum to EXACTLY the requested
    delta (see _plan_inertial_steps). If a wheel() call takes >2s the
    remaining queue is dropped (post-hoc detection — sync API cannot
    interrupt a hung CDP call). burst_guard skips steps issued <15ms after
    the previous one (burst after a CDP hang-up).
    """
    if not hasattr(page, "mouse") or not hasattr(page.mouse, "wheel"):
        return
    if abs(total_delta_y) < 5:
        return

    if num_steps is None:
        num_steps = rng.randint(8, 15)

    total = float(total_delta_y)
    sign = 1.0 if total > 0 else -1.0
    _t = __import__("time")
    prev_wheel_ts = 0.0
    aborted = False
    steps_plan = _plan_inertial_steps(abs(total), num_steps, rng)

    for i, step_px in enumerate(steps_plan):
        if aborted:
            break  # drop the queue — no burst of leftover wheel events

        dy = sign * step_px

        # burst guard — skip if the previous wheel was <15ms ago (queue
        # recovery after a CDP hang). Disabled in FAST_MODE: inter-step pause
        # there is 2ms, so the guard would skip every step after the first.
        now = _t.time()
        if not _FAST_MODE and prev_wheel_ts > 0 and (now - prev_wheel_ts) < 0.015:
            log.warning("_human_inertial_wheel: burst detected (%.0fms gap) — skipping step %d/%d",
                        (now - prev_wheel_ts) * 1000, i + 1, len(steps_plan))
            continue

        wheel_start = _t.time()
        try:
            page.mouse.wheel(0, dy)
        except Exception:
            return

        wheel_elapsed = _t.time() - wheel_start
        prev_wheel_ts = _t.time()

        if wheel_elapsed > 2.0:
            log.warning("_human_inertial_wheel: CDP timeout %.1fs step %d/%d — aborting queue",
                        wheel_elapsed, i + 1, len(steps_plan))
            aborted = True
            break

        if i < len(steps_plan) - 1 and not aborted:
            # Human-like inter-wheel delay: 50-150ms (real finger on the wheel).
            _sleep(rng, 0.050, 0.150)
def _human_scroll(page, rng, count: int = None, px_range: tuple = (200, 600)) -> None:
    """Человеческий скролл: СНАЧАЛА курсор к скроллбару/контенту, ПОТОМ wheel.
    Правило «Сначала рука — потом движение» — никаких wheel из пустоты."""
    if not hasattr(page, "mouse") or not hasattr(page.mouse, "wheel"):
        return
    # ── Позиционирование курсора ПЕРЕД скроллом ──
    try:
        vw = page.evaluate("() => window.innerWidth") or 1200
        vh = page.evaluate("() => window.innerHeight") or 800
        if rng.random() < 0.55:
            tx = vw - rng.uniform(10, 40)           # скроллбар
        else:
            tx = rng.uniform(vw * 0.15, vw * 0.75)   # контент
        ty = rng.uniform(vh * 0.25, vh * 0.65)
        _human_mouse_to(page, tx, ty, rng)
        _sleep(rng, 0.05, 0.15)
    except Exception as _err:        _swallow_err("distribution_browser_engine", _err)

    n = count or rng.randint(2, 5)
    for _ in range(n):
        delta = rng.randint(*px_range)
        _human_inertial_wheel(page, delta, rng)
        _sleep(rng, 0.5, 1.5)
def human_click_box(page, bbox: list, rng, profile=None, undershoot_ratio: float = 0.0) -> bool:
    """Принять bounding box от Qwen2.5VL:3b [x1, y1, x2, y2] → Fitts-клик.

    Prescription item #3: двумерное Гауссово распределение σ=W/6 (Закон Фиттса),
    Bezier-траектория с фазой торможения (easing), физический mousedown→dwell→mouseup.

    bbox: [x1, y1, x2, y2] — координаты от vision-модели (Qwen2.5VL:3b).
    profile: BehavioralProfile или dict с overshoot_chance, click_duration_ms, tremor_px.
    undershoot_ratio: 0.0 = без недолёта, 0.15 = Bezier до 85% пути → коррекция → цель.
    """
    if not bbox or len(bbox) < 4:
        return False
    x1, y1, x2, y2 = float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])
    w, h = x2 - x1, y2 - y1
    if w <= 0 or h <= 0:
        return False
    _ensure_tab_focus(page, rng)
    try:
        ox, oy = _fitts_click_offset(rng, w, h)
        tx, ty = x1 + ox, y1 + oy

        # V1: Детерминированный undershoot — Bezier до 85-95% пути, коррекция, цель
        if undershoot_ratio > 0.01:
            _ensure_cursor_state(page, rng)
            sx, sy = _cursor_get()
            ux = sx + (tx - sx) * (1.0 - undershoot_ratio)
            uy = sy + (ty - sy) * (1.0 - undershoot_ratio)
            _human_mouse_to(page, ux, uy, rng)
            _sleep(rng, 0.06, 0.12)  # зрительная коррекция недолёта
            _human_mouse_to(page, tx, ty, rng)
            _sleep(rng, 0.05, 0.20)

        # Path-error: 5% шанс отклонения в середине траектории (только без undershoot)
        elif rng.random() < 0.05:
            mid_x = tx + rng.uniform(15, 30) * (1 if rng.random() > 0.5 else -1)
            mid_y = ty + rng.uniform(10, 20) * (1 if rng.random() > 0.5 else -1)
            mid_x = max(x1 - 2, min(x2 + 2, mid_x))
            mid_y = max(y1 - 2, min(y2 + 2, mid_y))
            _human_mouse_to(page, mid_x, mid_y, rng)
            _sleep(rng, 0.08, 0.15)
            _human_mouse_to(page, tx, ty, rng)
            _sleep(rng, 0.05, 0.20)
        else:
            _human_mouse_to(page, tx, ty, rng)
            _sleep(rng, 0.05, 0.20)

        # Undershoot: 15% — уставшая рука недотягивает 5-10px (Патч U1)
        # Биомеханика: undershoot короче и быстрее корректируется чем overshoot.
        if rng.random() < 0.15:
            undershoot_x = tx + rng.uniform(5, 10) * (-1 if rng.random() > 0.3 else 1)
            undershoot_y = ty + rng.uniform(3, 7) * (-1 if rng.random() > 0.3 else 1)
            page.mouse.move(undershoot_x, undershoot_y)
            _sleep(rng, 0.04, 0.08)  # быстрая зрительная коррекция
            page.mouse.move(tx, ty)  # дотянуть до цели
            _sleep(rng, 0.03, 0.07)

        # Overshoot с когнитивной паузой
        overshoot_ch = 0.18
        if profile is not None:
            overshoot_ch = getattr(profile, 'overshoot_chance', 0.18) if not isinstance(profile, dict) else profile.get('overshoot_chance', 0.18)
        if rng.random() < overshoot_ch:
            overshoot_x = tx + rng.uniform(5, 12) * (1 if rng.random() > 0.5 else -1)
            overshoot_y = ty + rng.uniform(3, 8) * (1 if rng.random() > 0.5 else -1)
            page.mouse.move(overshoot_x, overshoot_y)
            _sleep(rng, 0.10, 0.25)  # когнитивная пауза
            for _ in range(rng.randint(2, 3)):
                ix = overshoot_x + (tx - overshoot_x) * rng.uniform(0.3, 0.7)
                iy = overshoot_y + (ty - overshoot_y) * rng.uniform(0.3, 0.7)
                page.mouse.move(ix, iy)
                _sleep(rng, 0.04, 0.10)
            page.mouse.move(tx, ty)
            _sleep(rng, 0.05, 0.12)

        # Физический клик: mousedown → dwell(60-180ms) → mouseup
        click_lo, click_hi = 60, 180
        if profile is not None:
            if isinstance(profile, dict):
                cd = profile.get('click_duration_ms', [60, 180])
            else:
                cd = getattr(profile, 'click_duration_ms', [60, 180])
            click_lo, click_hi = cd[0], cd[1]
        page.mouse.move(tx, ty)
        page.mouse.down()
        _sleep(rng, click_lo / 1000.0, click_hi / 1000.0)
        page.mouse.up()

        _cursor_set(float(tx), float(ty))
        return True
    except Exception:
        return False


def human_input_manager(page, element, text: str, rng, wpm: int = 58,
                        profile=None, locale: str = "en",
                        fatigue: "SessionFatigueTracker | None" = None) -> None:
    """Единый вход текста с locale-aware раскладкой (P2) + fatigue-деградацией (P3).

    locale: 'en_GB', 'de_DE', 'fr_FR' и т.д. → выбор QWERTY/QWERTZ/AZERTY.
    fatigue: SessionFatigueTracker → деградированный WPM и typo_rate.
    profile: BehavioralProfile или dict с typing_wpm, typo_rate (статический бейзлайн).
    """
    if not text or not hasattr(page, "keyboard"):
        return
    _ensure_tab_focus(page, rng)

    # P2: resolve keyboard layout from locale
    keyboard_locale = locale if locale else "en"

    # Порог 150: короче — печать, длиннее — физическая Ctrl+V
    if len(text) > 150:
        import pyperclip as _clip
        mod = _mod_key(page)
        try:
            _clip.copy(text)
        except Exception:
            page.keyboard.insert_text(text)
            _sleep(rng, 0.4, 0.9)
            return
        _sleep(rng, 0.10, 0.30)
        try:
            page.keyboard.down(mod)
            _sleep(rng, 0.03, 0.07)
            page.keyboard.down("v")
            _sleep(rng, 0.02, 0.05)
            page.keyboard.up("v")
            _sleep(rng, 0.02, 0.04)
            page.keyboard.up(mod)
        except Exception:
            page.keyboard.press(f"{mod}+v")
        _sleep(rng, 0.3, 0.7)
        if rng.random() < 0.15 and len(text) > 100:
            page.keyboard.press("Home")
            _sleep(rng, 0.08, 0.15)
            for _ in range(rng.randint(0, 2)):
                page.keyboard.press("ArrowRight")
                _sleep(rng, 0.04, 0.08)
            page.keyboard.press("Backspace")
            _sleep(rng, 0.05, 0.10)
            page.keyboard.press(text[min(rng.randint(0, min(5, len(text) - 1)), len(text) - 1)])
        return

    # ── Короткий текст: locale-aware burst-ввод с fatigue ──
    # Делегируем в _human_burst_type (единый движок печати)
    _human_burst_type(page, text, rng, wpm=wpm, el=element,
                      locale=keyboard_locale, fatigue=fatigue)
