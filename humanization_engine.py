"""Humanization parameters: behavior models for the browser engine.

Persona-driven behavior dispatch (scroll style, reading depth, WPM),
energy curve over the day, cognitive pauses, and human-error primitives
(misclick, scroll-past-and-back, retype). Thin facade over the motion
primitives in distribution_browser_engine.
"""

import logging
import random
import sys as _sys
import time
import time as _t
from dataclasses import dataclass, field

log = logging.getLogger("humanlike_engine.humanization")

_FAST_MODE = False


def _swallow_err(_block, _err):
    """Never-raising guard: swallowed errors are only logged."""
    try:
        log.debug("suppressed in %s: %r", _block, _err)
    except Exception:
        pass


def safe_evaluate(page, fn, *args):
    """Local shim for the shared safe_browser helper: run JS in the page."""
    try:
        return page.evaluate(fn, *args)
    except Exception as _err:
        _swallow_err("safe_evaluate", _err)
        return None


@dataclass
class EngineActionResult:
    """Результат действия Engine — структурированный (не голый bool)."""
    success: bool = False
    fallback_used: bool = False
    error: str = ""
    retries: int = 0
    action: str = ""
    meta: dict = field(default_factory=dict)

    def __bool__(self) -> bool:
        return self.success
def _mod_key(page) -> str:
    """Meta (Cmd) на macOS, Control на всём остальном. По navigator.platform."""
    try:
        plat = (safe_evaluate(page, "() => navigator.platform || ''") or "").lower()
        return "Meta" if plat.startswith("mac") else "Control"
    except Exception:
        import sys as _sys
        return "Meta" if _sys.platform == "darwin" else "Control"
def _physical_scroll(page, delta_y: float, *, rng=None, num_ticks: int = None) -> bool:
    """Эмуляция физического колеса мыши с экспоненциальным затуханием (Scroll Decay).

    Правило «Сначала рука — потом движение»: курсор ОБЯЗАН быть у скроллбара
    или над контентом ПЕРЕД вызовом wheel. Никаких wheel из пустоты.
    """
    try:
        if not hasattr(page, "mouse") or not hasattr(page.mouse, "wheel"):
            return False
        r = rng or random.Random()

        # ── Сначала рука: Bezier к скроллбару или контенту ──
        try:
            from distribution_browser_engine import _human_mouse_to
            vw = safe_evaluate(page, "() => window.innerWidth") or 1200
            vh = safe_evaluate(page, "() => window.innerHeight") or 800
            if r.random() < 0.55:
                tx = vw - r.uniform(10, 40)          # скроллбар
            else:
                tx = r.uniform(vw * 0.15, vw * 0.75)  # контент
            ty = r.uniform(vh * 0.25, vh * 0.65)
            _human_mouse_to(page, tx, ty, r)
            time.sleep(r.uniform(0.05, 0.15))
        except Exception:
            log.debug("suppressed")

            pass  # best-effort: позиционирование мыши, не блокировать скролл

        from distribution_browser_engine import _human_inertial_wheel
        _human_inertial_wheel(page, delta_y, r, num_steps=num_ticks)
        return True
    except Exception:
        return False
class HumanizationEngine:
    """Фасад очеловеченных действий. Делегирует всё специализированным движкам."""
    def __init__(
        self,
        page,
        channel_id: str = "",
        persona: dict = None,
        bprof=None,
        sema: dict = None,
        rng: random.Random = None,
        context=None,       # BrowserContext (для new_tab)
        country_code: str = "us",
        event_hook=None,        # optional event hook (unused)
        fatigue_tracker=None,    # optional fatigue tracker
    ):
        self.page = page
        self.channel_id = channel_id
        self.persona = persona or {}
        self.bprof = bprof          # BehavioralProfile dataclass
        self.sema = sema or {}      # SemanticPersona dict
        self.rng = rng or random.Random()
        self.context = context
        self.cc = (country_code or "us").lower().strip()
        self._hook = event_hook
        self._last_intent = ""
        self._last_bbox = None
        self._fatigue = fatigue_tracker  # fatigue tracker | None

        # Состояние сессии
        self.actions_taken: int = 0
        self.errors: int = 0
        # Behavior dispatcher — персонализация из digital_dna
        self._behavior = self._get_behavior_params()

    def _get_behavior_params(self) -> dict:
        """Диспетчер повадок: извлекает персональные модификаторы из digital_dna.

        Все тайминги/вероятности умножаются на energy — график активности меняется
        в течение дня, убивая «роботизированный паттерн» детектор.
        """
        dna = self.persona.get("digital_dna", {}) if isinstance(self.persona, dict) else {}
        if hasattr(self.persona, "digital_dna") and not dna:
            dna = self.persona.digital_dna or {}

        typing_p = dna.get("typing_profile", {})
        browsing = dna.get("browsing_habits", {})
        content = dna.get("content_preferences", {})
        sentiment = dna.get("interest_sentiment", {})
        mood_curve = dna.get("daily_mood_curve", [])
        quirks = dna.get("persona_quirks", [])

        energy = self._calculate_current_energy(mood_curve)

        # scroll_style → jerky_chunked (прыжки 300-800px) vs smooth (мелкие шаги)
        scroll_style = browsing.get("scroll_style", "smooth_continuous")
        scroll_jerky = scroll_style in ("jerky_chunked", "arrow_keys")

        # reading_depth → skimmer (быстрый, заголовки) vs deep_reader (медленный, абзацы)
        reading_depth = browsing.get("reading_depth", "moderate")
        is_skimmer = reading_depth in ("skimmer", "headline_only")
        is_deep = reading_depth == "deep_reader"

        # reading_wpm из typing_profile (reading ≈ typing_wpm * 4)
        reading_wpm = (typing_p.get("wpm_base", 40) or 40) * 4

        # interest_sentiment → агрегированный click_bias
        sentiments = [v.get("sentiment", "neutral") for v in sentiment.values()] if sentiment else []
        skeptic_ratio = sentiments.count("skeptic") + sentiments.count("critical")
        enthusiast_ratio = sentiments.count("enthusiast")
        total = max(1, len(sentiments))
        # close_tab_probability: скептик чаще закрывает неинтересные вкладки
        close_tab_prob = 0.1 + 0.7 * (skeptic_ratio / total)
        # click_boost: энтузиаст чаще кликает на внутренние ссылки
        click_boost = 1.0 + 0.5 * (enthusiast_ratio / total)

        # quirks
        quirk_categories = [q.get("category", "") for q in quirks]
        quirk_descs = [q.get("quirk", "") for q in quirks]
        always_new_tab = any("new tab" in q.lower() for q in quirk_descs)
        never_close_tabs = any("never closes" in q.lower() or "50+" in q for q in quirk_descs)

        # content prefs
        skip_intro_chance = content.get("skip_intro_chance", 0.3)
        pref_duration = content.get("preferred_video_duration_sec", 600)
        pref_tone = content.get("preferred_tone", "educational")

        return {
            "energy": energy,
            "scroll_style": scroll_style,
            "scroll_jerky": scroll_jerky,
            "reading_depth": reading_depth,
            "is_skimmer": is_skimmer,
            "is_deep": is_deep,
            "reading_wpm": reading_wpm,
            "close_tab_prob": round(close_tab_prob, 2),
            "click_boost": round(click_boost, 2),
            "always_new_tab": always_new_tab,
            "never_close_tabs": never_close_tabs,
            "skip_intro_chance": skip_intro_chance,
            "pref_duration": pref_duration,
            "pref_tone": pref_tone,
            "quirk_categories": quirk_categories,
        }

    @staticmethod
    def _calculate_current_energy(mood_curve: list) -> float:
        """Текущий уровень энергии из daily_mood_curve по времени суток."""
        if not mood_curve:
            return 0.7  # default: бодрый
        try:
            from datetime import datetime
            now = datetime.now()
            current_minutes = now.hour * 60 + now.minute
            for segment in mood_curve:
                hour_range = segment.get("hour", "12:00-14:00")
                parts = hour_range.split("-")
                if len(parts) == 2:
                    h1, m1 = parts[0].split(":")
                    h2, m2 = parts[1].split(":")
                    start = int(h1) * 60 + int(m1)
                    end = int(h2) * 60 + int(m2)
                    # handle overnight ranges (00:00-06:00)
                    if start > end:
                        if current_minutes >= start or current_minutes < end:
                            return float(segment.get("energy", 0.7))
                    elif start <= current_minutes < end:
                        return float(segment.get("energy", 0.7))
        except Exception:
            log.debug("suppressed")

            pass
        return 0.7
    def pause(self, lo: float = 1.0, hi: float = 4.0) -> None:
        """Когнитивная пауза: микро-дыхание курсора + бездействие (думает/читает). Без скролла.
        Fatigue-aware: паузы растягиваются с усталостью (speed_factor ≥ 1.0)."""
        if self._fatigue is not None:
            sf = self._fatigue.speed_factor
            lo, hi = lo * sf, hi * sf
        try:
            from distribution_browser_engine import _micro_sleep
        except ImportError:
            from distribution_browser_engine import _micro_sleep
        _micro_sleep(self.page, self.rng, lo, hi)

    def cognitive_pause(self) -> None:
        """Stochastic cognitive pause: 18% chance micro-idle 5-40s.

        Natural behavior during idle:
        80% -- still with micro-tremor (reading/thinking)
        15% -- one gentle scroll pulse (browsing)
        5%  -- single cursor reposition (e.g. to next paragraph)
        Anti-fraud: chaotic 8-point darting replaced with physiology-correct patterns.
        """
        if self.rng.random() > 0.18:
            return
        duration_s = self.rng.uniform(5.0, 40.0)
        import time as _t
        try:
            vp = self.page.viewport_size or {"width": 1024, "height": 768}
            idle_action = self.rng.random()
            if idle_action < 0.80:
                # 80%: Still with micro-tremor -- human reads/thinks
                # Emit subtle 1-2px jitter mimicking hand resting on mouse
                try:
                    cx, cy = vp["width"]*self.rng.uniform(0.25, 0.65), vp["height"]*self.rng.uniform(0.30, 0.70)
                    self.move(cx, cy)
                except Exception as _err:
                    _swallow_err("humanization_engine", _err)
                remaining = duration_s - 1.0
                while remaining > 0.5:
                    chunk = min(remaining, self.rng.uniform(2.0, 5.0))
                    _t.sleep(chunk)
                    remaining -= chunk
                    # micro-tremor every 2-5s
                    if remaining > 1 and self.rng.random() < 0.4:
                        try:
                            self.page.mouse.move(
                                cx + self.rng.uniform(-2, 2),
                                cy + self.rng.uniform(-1, 1),
                                steps=2)
                        except Exception as _err:
                            _swallow_err("humanization_engine", _err)
            elif idle_action < 0.95:
                # 15%: One gentle scroll pulse -- human browses
                for _ in range(self.rng.randint(1, 3)):
                    dy = self.rng.randint(-120, 120)
                    try:
                        self.page.mouse.wheel(0, dy)
                    except Exception as _err:
                        _swallow_err("humanization_engine", _err)
                    _t.sleep(self.rng.uniform(2.0, 6.0))
                if duration_s > 10:
                    _t.sleep(duration_s - 5)
            else:
                # 5%: Single cursor movement to content position, then still
                try:
                    cx = vp["width"] * self.rng.uniform(0.25, 0.65)
                    cy = vp["height"] * self.rng.uniform(0.30, 0.70)
                    self.move(cx, cy)
                except Exception as _err:
                    _swallow_err("humanization_engine", _err)
                _t.sleep(duration_s - 1.5)
            log.debug("[cognitive_pause] micro-idle %.1fs (pattern=%.2f)", duration_s, idle_action)
        except Exception:
            _t.sleep(duration_s)
    def scroll(self, direction: str = "down", amount_px: int = None) -> bool:
        """DOM-aware семантический скролл — персонализирован под scroll_style.

        jerky_chunked: случайные прыжки 300-800px (имитация нетерпеливого скролла).
        smooth_continuous: мелкие шаги с паузами.
        arrow_keys: пострелочный скролл (page_down).
        """
        if not hasattr(self.page, "evaluate"):
            return False
        try:
            energy = self._behavior.get("energy", 0.7)
            jerky = self._behavior.get("scroll_jerky", False)
            target = self._next_block_below(direction)
            if target:
                _physical_scroll(self.page, target['top'], rng=self.rng)
                pause_ms = target.get("pause_ms", self.rng.randint(300, 700))
                # energy: drained → дольше паузы
                pause_ms = int(pause_ms / max(0.3, energy))
                time.sleep(pause_ms / 1000.0)
                if target.get("type") in ("image", "header") and self.rng.random() < 0.6 * energy:
                    self._micro_mouse_move_near(target.get("cx", 500), target.get("cy", 300))
            else:
                sign = -1 if direction == "up" else 1
                if jerky:
                    # jerky_chunked: прыжки 300-800px с нерегулярными паузами
                    px = amount_px or self.rng.choice([300, 350, 500, 650, 800])
                    _physical_scroll(self.page, sign * px, rng=self.rng)
                    # случайная микро-пауза после прыжка (анти-робот)
                    if self.rng.random() < 0.4:
                        time.sleep(self.rng.uniform(0.1, 0.5) / max(0.3, energy))
                else:
                    # smooth: мелкие шаги
                    px = amount_px or self.rng.randint(120, 350)
                    _physical_scroll(self.page, sign * px, rng=self.rng)
            self.actions_taken += 1
            return True
        except Exception:
            self.errors += 1
            log.error("scroll failed", exc_info=True)
            return False
    def read(self, duration_s: float) -> bool:
        """Personalized DOM reading loop: wpm, depth, energy, scroll blocks."""
        if not hasattr(self.page, 'evaluate'):
            return False
        if _FAST_MODE:
            _sleep(self.rng, 0.01, 0.02)
            self.actions_taken += 1
            return True
        # DOM-based _next_block_below loop (personalized)
        try:
            sp = self.sema.get("scroll_pattern", {})
            p_headers = sp.get("pause_on_headers_ms", (600, 1800))
            p_images = sp.get("pause_on_images_ms", (800, 2800))
            p_paragraphs = sp.get("pause_on_paragraphs_ms", (300, 1200))
            reading_wpm = self._behavior.get("reading_wpm", 200)
            energy = self._behavior.get("energy", 0.7)
            is_skimmer = self._behavior.get("is_skimmer", False)
            is_deep = self._behavior.get("is_deep", False)
            avg_words_per_line = 10
            elapsed = 0.0
            blocks_read = 0
            _short_phase = True

            while elapsed < duration_s:
                block = self._next_block_below("down")
                if not block:
                    _sleep(self.rng, 0.5, 1.5)
                    elapsed += 1.0
                    continue

                btype = block.get("type", "text")
                if btype == "header":
                    pause_s = self.rng.uniform(*p_headers) / 1000.0
                elif btype == "image":
                    pause_s = self.rng.uniform(*p_images) / 1000.0
                else:
                    # skimmer: пропускает абзацы, фокус на заголовках
                    if is_skimmer and self.rng.random() < 0.7:
                        pause_s = self.rng.uniform(0.1, 0.3)  # быстрый пролист
                    else:
                        block_h = block.get("h", 200)
                        est_words = max(3, block_h / 25 * avg_words_per_line)
                        wpm_pause = est_words / reading_wpm * 60.0
                        if is_deep:
                            # deep_reader: longer pauses, re-reads
                            wpm_pause *= self.rng.uniform(1.3, 2.2)
                        if _short_phase:
                            pause_s = wpm_pause * self.rng.uniform(1.2, 2.0)
                        else:
                            pause_s = wpm_pause * self.rng.uniform(0.15, 0.35)
                    _short_phase = not _short_phase

                # energy multiplier: drained → дольше паузы на всём
                pause_s = pause_s / max(0.3, energy)

                # Скролл: короткий (200-400px) или длинный (600-1000px)
                scroll_px = (block["top"] if _short_phase
                            else block.get("top", 400) * self.rng.uniform(1.5, 2.5))
                _physical_scroll(self.page, scroll_px, rng=self.rng)
                from distribution_browser_engine import _micro_sleep
                _micro_sleep(self.page, self.rng, max(0.2, pause_s), max(0.3, pause_s + 0.1))
                elapsed += pause_s + 0.3
                blocks_read += 1

                # Движение взгляда по строкам (4.3)
                if self.rng.random() < 0.5:
                    self._gaze_along_line(block.get("cx", 500), block.get("cy", 300),
                                         block.get("width", 600))

                # Возврат наверх (перечитывает)
                if self.rng.random() < sp.get("bottom_scrollback_chance", 0.12):
                    vh_up = safe_evaluate(self.page,"() => window.innerHeight") or 800
                    _physical_scroll(self.page, -vh_up * 0.4, rng=self.rng)
                    _sleep(self.rng, 0.5, 1.5)

                if blocks_read > 30:
                    break

            self.actions_taken += 1
            return True
        except Exception:
            self.errors += 1
            return False

    def _gaze_along_line(self, cx: float, cy: float, width: float) -> None:
        """Горизонтальное движение мыши вдоль строки (ведение при чтении). (4.3)

        Spec: "Во время пауз чтения курсор мыши должен совершать микродвижения
        по горизонтали вдоль строчек текста"
        """
        try:
            line_y = cy
            start_x = max(10, cx - width * 0.4)
            end_x = cx + width * 0.35
            # 2-3 горизонтальных прохода с микро-Y дрожанием
            for _ in range(self.rng.randint(2, 3)):
                sx = self.rng.uniform(start_x, cx)
                ex = self.rng.uniform(cx, end_x)
                for px in (sx, ex):
                    py = line_y + self.rng.uniform(-3, 3)
                    self.move(px, py)
                    time.sleep(self.rng.uniform(0.05, 0.15))
                line_y += self.rng.uniform(18, 28)  # следующая строка
        except Exception:
            log.debug("suppressed")

            pass
    def _next_block_below(self, direction: str = "down") -> dict:
        """Найти следующий семантический блок ниже (или выше) текущей позиции скролла.

        Возвращает {top, cx, cy, type, pause_ms} или None.
        """
        try:
            result = safe_evaluate(self.page,"""(dir) => {
                const blocks = [];
                const tags = ['h1', 'h2', 'h3', 'p', 'img', 'article', 'section', 'figure'];
                const vh = window.innerHeight;
                const scrollY = window.pageYOffset;
                for (const tag of tags) {
                    const els = document.querySelectorAll(tag);
                    for (const el of els) {
                        const r = el.getBoundingClientRect();
                        if (!r || r.height < 10) continue;
                        const absTop = r.top + scrollY;
                        const below = dir === 'down' ? absTop > (scrollY + vh * 0.1) : absTop < (scrollY - vh * 0.1);
                        if (!below) continue;
                        let type = 'text';
                        if (/^h[123]$/i.test(tag)) type = 'header';
                        else if (tag === 'img') type = 'image';
                        else if (/article|section/i.test(tag)) type = 'section';
                        blocks.push({
                            top: r.top - vh * 0.1,
                            absTop: absTop,
                            cx: r.x + r.width / 2,
                            cy: r.y + r.height / 2,
                            type: type,
                            h: r.height,
                        });
                    }
                }
                if (!blocks.length) return null;
                blocks.sort((a, b) => a.absTop - b.absTop);
                const best = dir === 'down' ? blocks[0] : blocks[blocks.length - 1];
                // Pause duration by type
                if (best.type === 'header') best.pause_ms = 500 + Math.random() * 1000;
                else if (best.type === 'image') best.pause_ms = 600 + best.h * 0.5;
                else best.pause_ms = 200 + Math.random() * 600;
                return best;
            }""", direction)
            return result
        except Exception:
            return None

    def _micro_mouse_move_near(self, cx: float, cy: float) -> None:
        """Микро-движения мыши рядом с точкой (человек водит мышкой пока читает)."""
        try:
            for _ in range(self.rng.randint(1, 3)):
                ox = cx + self.rng.uniform(-30, 30)
                oy = cy + self.rng.uniform(-15, 15)
                self.move(ox, oy)
                time.sleep(self.rng.uniform(0.05, 0.25))
        except Exception:
            log.debug("suppressed")

            pass
    def _maybe_mistake(self, context: str = "") -> bool:
        """Вызывается перед действием. С вероятностью 3-5% совершает ошибку.

        context: 'click', 'scroll', 'type', 'navigate' — тип действия.
        Возвращает True если ошибка случилась (вызывающий код может адаптироваться).
        """
        roll = self.rng.random()
        dr = self.sema.get("distraction_rate", 0.25) if self.sema else 0.25

        if roll < dr * 0.08:
            # Think-pause: человек задумался на 5-15s
            _sleep(self.rng, 5, 15)
            return True

        if context == "click" and roll < dr * 0.30:
            return self._misclick_and_correct()

        if context == "scroll" and roll < dr * 0.25:
            return self._scroll_past_and_back()

        if context == "type" and roll < dr * 0.12:
            return self._retype_partial()

        return False

    def _misclick_and_correct(self) -> bool:
        """Кликнуть мимо цели, осознать ошибку, кликнуть правильно."""
        if not hasattr(self.page, "mouse"):
            return False
        try:
            vp = self.page.viewport_size or {"width": 1024, "height": 768}
            mx = self.rng.randint(100, vp["width"] - 100)
            my = self.rng.randint(100, vp["height"] - 100)
            off_x = mx + self.rng.uniform(25, 50) * (1 if self.rng.random() > 0.5 else -1)
            off_y = my + self.rng.uniform(15, 35) * (1 if self.rng.random() > 0.5 else -1)
            self.move(off_x, off_y)
            self.page.mouse.click(off_x, off_y)
            _sleep(self.rng, 0.3, 0.8)  # осознал ошибку
            self.move(mx, my)
            self.page.mouse.click(mx, my)
            return True
        except Exception:
            return False

    def _scroll_past_and_back(self) -> bool:
        """Проскроллить на 30-50% дальше цели, понять что проскочил, скролл обратно."""
        if not hasattr(self.page, "evaluate"):
            return False
        try:
            vh = safe_evaluate(self.page,"() => window.innerHeight") or 800
            over = int(vh * self.rng.uniform(0.3, 0.5))
            _physical_scroll(self.page, over, rng=self.rng)
            _sleep(self.rng, 0.5, 1.0)  # понял что проскочил
            back = int(over * self.rng.uniform(0.4, 0.7))
            _physical_scroll(self.page, -back, rng=self.rng)
            return True
        except Exception:
            return False

    def _retype_partial(self) -> bool:
        """Начать печатать, стереть часть (Ctrl+Backspace), перепечатать."""
        if not hasattr(self.page, "keyboard"):
            return False
        try:
            # нескольких Backspace-ов
            for _ in range(self.rng.randint(3, 7)):
                self.page.keyboard.press("Backspace")
                time.sleep(self.rng.uniform(0.08, 0.18))
            _sleep(self.rng, 0.2, 0.5)
            return True
        except Exception:
            return False
_FAST_MODE = False


def set_fast_mode(v: bool):
    global _FAST_MODE
    _FAST_MODE = v


def _sleep(rng: random.Random, lo: float, hi: float) -> None:
    if _FAST_MODE:
        time.sleep(0.002)
    else:
        time.sleep(rng.uniform(lo, hi))
