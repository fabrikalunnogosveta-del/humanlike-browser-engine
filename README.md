# humanlike-browser-engine

**Human-like browser motion primitives for Python — lognormal latencies, Bezier+Fitts cursor paths, exact-delta inertial scrolling, burst typing, DPI-aware targeting.**

[![CI](https://github.com/fabrikalunnogosveta-del/humanlike-browser-engine/actions/workflows/ci.yml/badge.svg)](https://github.com/fabrikalunnogosveta-del/humanlike-browser-engine/actions)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Tests](https://img.shields.io/badge/tests-22%20passed-brightgreen)

Real people never move like machines: the hand arcs instead of drawing straight lines,
pauses follow a long-tailed distribution instead of uniform delays, and typing runs in
bursts shaped by muscle memory. This library turns raw Playwright-style input calls into
those natural patterns.

---

## The problem we solved

| Problem (before) | Solution (this library) |
|---|---|
| Straight-line mouse = bot signature | Cubic Bezier arcs + tremor |
| Uniform 100ms delays = robotic | Lognormal latencies, 60Hz-quantized |
| Scroll «almost 600px» | **Exact-delta** inertial delivery (sums to requested px) |
| Perfect typing = unnatural | Burst + typos + backspace + muscle memory |
| Wrong click on HiDPI displays | **DPI-aware CSS→OS cursor binding** |
| Unreproducible demos/tests | **Seeded RNG** — same seed, same trajectory |

**Bot-like input is trivially detectable.** This library models real human motor control.

### Bot-like vs human

| Bot-like input | This library |
|---|---|
| Straight-line mouse moves | Cubic Bezier arcs with tremor |
| Uniform 100ms delays | Lognormal, 60Hz-quantized |
| Perfect scroll amounts | Inertial decay, **exact delta delivered** |
| Perfect typing | Burst + typos + backspace + muscle memory |
| Ignores screen scale | DPI-aware CSS→OS cursor binding |

Useful for **UI testing, accessibility automation, RPA, QA**, and any workflow where
input should look and feel human.

---

## Demo

Real screen recording of one uninterrupted run (real OS cursor: Bezier fly-in →
Fitts click → inertial scroll → burst typing).

To re-record: `pip install mss pillow` then `python examples/record_demo.py`
(~30s, hands off the mouse).

---

## Architecture

```
distribution_browser_engine   # orchestration: delays, scroll, type, click, cookies
        │
        ├── bezier_mouse      # cubic Bezier + tremor + Fitts speed model
        ├── cursor_state      # shared cursor state + DPI calibration
        └── humanization_engine # persona: energy, pauses, reading loops

INPUT SURFACE (Playwright-style page object)
  mouse.move → Bezier path → Fitts target offset
  mouse.wheel → inertial decay plan → exact-delta delivery
  keyboard.type → burst engine (typos, flight/dwell, bigram memory)
  click → fresh bbox (no stale coords) + human latency
```

---

## Features

| Module | What it does |
|---|---|
| `distribution_browser_engine` | Lognormal delay engine (60Hz-quantized), Bezier mouse moves + Fitts click offsets, inertial wheel scroll with decay-shaped step plan, burst typing (typos, flight/dwell times, bigram muscle memory, 5 keyboard layouts), 3-tier cookie-banner dismissal (CSS selectors → semantic DOM scan) |
| `bezier_mouse` | Cubic Bezier trajectories with overshoot/undershoot, physiological tremor (8–12Hz octaves), frame-quantized step delays, size-dependent speed (Fitts's law) |
| `cursor_state` | Shared cursor-position state, **DPI-aware CSS→OS scale + window offset** |
| `humanization_engine` | Persona-driven behavior models: energy curve, cognitive pauses, reading loops, human-error primitives |

### Motion models in detail

| Primitive | Model | Guarantee |
|---|---|---|
| **Latency** | lognormal(μ, σ), 60Hz-quantized | long-tailed, not uniform |
| **Mouse path** | cubic Bezier + overshoot + 8–12Hz tremor | seed-deterministic |
| **Click target** | Fitts's law, gaussian σ = W/6 | stays inside element bounds |
| **Scroll** | inertial decay plan | **steps sum to requested delta exactly** |
| **Typing** | burst (3–7 keys) + typos + backspace | text preserved even with 100% typo rate |
| **DPI** | CSS→OS scale detect + calibrate | cursor 1:1 on 100–200% displays |

---

## Install

```bash
git clone https://github.com/fabrikalunnogosveta-del/humanlike-browser-engine.git
cd humanlike-browser-engine
pip install -r requirements.txt
```

## Quickstart

```python
import random
from distribution_browser_engine import (
    _human_inertial_wheel,
    _human_burst_type,
    _human_mouse_to,
    set_fast_mode,
)

rng = random.Random(42)
# set_fast_mode(True)  # fast/test runs

# Scroll exactly 600px with a decay-shaped human flick pattern
_human_inertial_wheel(page, 600, rng)

# Type text in bursts with realistic flight/dwell times
_human_burst_type(page, "hello world", rng, locale="en")
```

```python
from bezier_mouse import bezier_path

pts = bezier_path(
    0, 0, 400, 300,
    rng=random.Random(7),
    profile={"mouse_deviation": 30},
)
# deterministic: same seed → same trajectory, ends exactly at target
```

---

## How this maps to real jobs

| Job title | What this repo proves |
|---|---|
| **Automation / Browser Engineer** | Playwright-level input simulation with human motor models |
| **QA / Test Engineer** | deterministic, seedable input for reproducible UI tests |
| **AI / RPA Engineer** | behavioral motion modeling for agent workflows |
| **Accessibility Tooling** | realistic input patterns for assistive tech |

---

## Testing philosophy

The suite (**22 tests**) proves **behavioral contracts**, not just that code runs:

- inertial scroll steps **sum to the requested delta** (parametrized: 50–2000px),
  per-step cap respected, tiny deltas rejected (<5px)
- burst typing **preserves the text even when the typo engine fires**
  (forced 100%-typo regression test)
- click after auto-scroll uses a **fresh bounding box** (no stale-coordinate clicks)
- focus check returns **within a ~2s budget** and caches success for 3s
- Fitts offsets stay inside the element bounds; Bezier paths are seed-deterministic
- the OS cursor stays **1:1 bound to the virtual one across DPI scales** (calibrated
  CSS→screen scale + window offset, verified for 100–200% displays)

```bash
pip install pytest
python -m pytest tests/ -q
# 22 passed
```

---

## Design notes

- **Seeded everything**: delays sample from the module's `rng`, so demos and tests are
  reproducible.
- **Fail-safe input paths**: focus checks are time-budgeted (no multi-second stalls),
  CDP-hung wheel calls drop their queue post-hoc, clicks abort if the target element
  disappears during auto-scroll.
- **No network, no accounts**: pure computation on top of the Playwright API surface
  you already use.
- **DPI bug fixed**: `calibrate_window_offset` was dead code → live scale detection
  + CSS→OS mapping.

---

## License

MIT

---

## Author

**Maxim Parshshin** — AI/LLM systems, quality gates, browser automation.
Remote contracts. Open-source: [humanlike-browser-engine](https://github.com/fabrikalunnogosveta-del/humanlike-browser-engine) · [guards-and-laws](https://github.com/fabrikalunnogosveta-del/guards-and-laws).
