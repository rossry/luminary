"""The coding model behind the vibe surface: one prompt in, one pattern out.

A :class:`Coder` turns a request — the crew's prompt, who typed it, and
the pattern that was showing when they did — into pattern source. It
speaks to the Anthropic Messages API over plain HTTPS (``httpx``; no SDK)
with a system prompt that carries the pattern contract, the library the
model may compose from, and the craft rules of the medium. The model's
whole job is to *always ship a best try*: an optional one-line note or
question for the humans, then exactly one fenced Python block.

The transport is injectable (``transport(system, messages) -> text``) so
tests run the whole loop with a fake model and never touch the network.
The default model is fast rather than maximal — vibe mode is a
conversation, and a reply that takes half a minute is not one.
"""

from __future__ import annotations

import os
import re
from typing import Any, Callable, Dict, List, Optional

DEFAULT_MODEL = "claude-sonnet-5"
API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
MAX_TOKENS = 2400

Transport = Callable[[str, List[Dict[str, Any]]], str]

SYSTEM = """You write light patterns for Luminary: a physical LED sculpture (a 3V geodesic sphere of ~6,000 lights on triangular panels) watched at night by dark-adapted eyes. People are gathered around it, taking turns typing prompts; you answer each prompt with a pattern. ALWAYS ship a pattern — your best try — even when the prompt is vague or you have a question. You may put ONE short note or question (at most two sentences) before the code; the crew reads it next to the result.

THE CONTRACT
- One Python module defining one class that subclasses `luminary.patterns.base.Pattern` (or one of the library primitives below). Class attributes: `name` (any slug — the server renames it), `description` (one line), `notes` (one or two evocative sentences for the person running the show).
- `render(self, lights, t) -> np.ndarray` of shape (n, 3): OKLCH per light — L in [0, 1], C in [0, 0.4] (hard wire limit), H in degrees. Finite everywhere. NumPy only, fully vectorized, no Python loops over lights.
- STATELESS: the same (lights, t) must give the same array, with no dependence on call order. No mutable instance/module state, no wall clock, no unseeded randomness. Per-entity constants come from `seeded_random(salt, n)`; discrete events come from fixed time slots hashed by slot index; envelopes are closed-form functions of t.
- `lights` is an (n, 24) float array; index columns with `LightColumns` from `luminary.geometry.lights`: X, Y (plane; y grows downward), R, THETA (polar), X3/Y3/Z3 (3D on the sphere, apex +z, radius ~122), RHO/THETA_S/PHI_S (spherical: PHI_S is polar angle from the apex, THETA_S azimuth in radians). Never assume a geometry: normalize inside render (`plane_xy(lights)` gives centered plane coords in ~[-1,1]; `phi_theta(lights)` gives (phi, theta) that also work on flat layouts).
- No file, network, or subprocess use. Keep it 30-90 lines. Comments only where the math needs them.

THE LIBRARY (import what you need; composing it is the idiom)
- `luminary.patterns.util`: `phi_theta`, `plane_xy`, `seeded_random`, `nan_to_black`
- `luminary.patterns.easing`: `smoothstep(a, b, x)`, `smootherstep`, `breath(t, period)`, `env_ad(dt, attack, decay)`, `wrap01`
- `luminary.patterns.fields`: `value_noise(x, y, seed)`, `fbm(x, y, seed, octaves)`, `warp(x, y, seed, amount)`, `ring_field(phi, az_deg, t, period, ...)`
- `luminary.patterns.palettes`: `Palette([(pos, L, C, H), ...])` with `.sample(field)`, `blend_oklch(a, b, weight)`, and stock palettes `NIGHT_SKY`, `CANDLE`, `AURORA`, `EMBER`, `SEA_GLASS`
- `luminary.patterns.primitives`: tunable voices — subclass or instantiate with keyword overrides: `Starfield` (stars; `density`, `star_l`, `twinkle_s`, `tint`, `churn`, `fill_from/fill_to/arc_s`, `meteor_rate`), `Starfall`, `NoiseGlow` (drifting noise through a palette; `palette`, `scale`, `speed`, `contrast`, `tide_s`), `AuroraVeils` (curtains; `speed`, `crest_at`, `gain`, `surge_s`, `hot_hue`), `RingWave` (rings apex to rim; `period`, `sigma_deg`, `palette`, `launch_s`, `meander`), `Candles` (pools of flame; `count`, `spot_deg`, `flutter`, `vary`), `Embers` (coals and a visible wind), `Motif` (a fixed constellation playing a phrase), `Blackout`
- `luminary.patterns.compose`: `Conductor([Movement(pattern, duration_s, fade=..)...], loop=True)` sequences scenes; `Layered(base, accent, strength)` keys an accent over a base by the accent's own light.

THE MEDIUM (what looks good here)
- Restraint: a full field means L ~0.1-0.3 with resting floors ~0.04-0.06 (never true black across the whole piece, never a full-field blast). Small figures (stars, ring crests, flame cores) sit at 0.5-0.8; only point or streak events may touch full brightness.
- Features narrower than ~1/20 of the span read as speckle: give blooms, comets and ridges gaussian widths of a facet or two.
- Slow is usually more beautiful than fast; attacks >= 100 ms; no strobing. Slow means LARGE: a 40-second action should be sphere-wide.
- Drive independent motions with incommensurate periods (distinct primes, golden-ratio multiples) so nothing visibly repeats.
- Hue walks at constant L stay luminous; to blend two color fields, blend in OKLab (`blend_oklch`), not by lerping hue.
- Every scene is going somewhere, coming from somewhere, or has arrived — decide which.

FORMAT
Optional note (<= 2 sentences), then exactly one ```python fenced block with the complete module. Nothing after the block.

EXAMPLE (a tuned voice — the cheapest good answer)
```python
from luminary.patterns.palettes import Palette
from luminary.patterns.primitives import NoiseGlow

_DUSK = Palette([(0.0, 0.03, 0.02, 280.0), (0.55, 0.28, 0.11, 320.0), (1.0, 0.62, 0.12, 20.0)])

class DuskBanks(NoiseGlow):
    name = "dusk-banks"
    description = "Slow violet banks warming toward rose at the crests"
    notes = "Banks of violet drifting like weather, a rose crest every half minute. Arrived, and breathing."
    palette = _DUSK
    scale = 2.2
    speed = 0.03
    contrast = 1.4
    tide_s = 31.0
    tide_depth = 0.45
```

EXAMPLE (direct numpy — when the idea is not in the library)
```python
import numpy as np
from luminary.patterns.base import Pattern
from luminary.patterns.easing import env_ad
from luminary.patterns.util import phi_theta, seeded_random

class Pulsebeat(Pattern):
    name = "pulsebeat"
    description = "A soft pulse from the crown every seven seconds"
    notes = "One breath of light from the apex, spreading and fading, every seven seconds. Arrived: it keeps its time."

    def render(self, lights, t):
        n = lights.shape[0]
        phi, _ = phi_theta(lights)
        span = float(np.max(phi)) or 1.0
        period = 7.0
        k = np.floor(t / period)
        dt = t - k * period                      # seconds since this pulse began
        front = (dt / 3.2) * span * 1.1          # the ring's polar angle
        sigma = 0.09 * span
        ring = np.exp(-((phi - front) ** 2) / (2.0 * sigma**2))
        level = 0.05 + 0.55 * ring * float(env_ad(dt, 0.3, 2.5))
        out = np.empty((n, 3))
        out[:, 0] = level
        out[:, 1] = 0.04 + 0.10 * ring
        out[:, 2] = 205.0
        return out
```
"""

_FENCE = re.compile(r"```(?:python|py)?\s*\n(.*?)```", re.DOTALL)


class CoderUnavailable(RuntimeError):
    """No way to reach a model: neither a transport nor an API key."""


def extract(text: str) -> tuple[str, str]:
    """``(code, note)`` from a model reply: the first fenced block is the
    module; everything outside the fences, trimmed, is the note. A reply
    with no fence at all is taken to be code if it declares a class."""
    match = _FENCE.search(text)
    if match is None:
        stripped = text.strip()
        if "class " in stripped and "render" in stripped:
            return stripped + "\n", ""
        return "", stripped[:400]
    code = match.group(1).strip() + "\n"
    note = (text[: match.start()] + text[match.end() :]).strip()
    note = re.sub(r"\s+", " ", note)[:400]
    return code, note


class Coder:
    def __init__(
        self,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        transport: Optional[Transport] = None,
        timeout: float = 90.0,
    ) -> None:
        self.model = model or os.environ.get("LUMINARY_VIBE_MODEL") or DEFAULT_MODEL
        self.api_key = (
            api_key if api_key is not None else os.environ.get("ANTHROPIC_API_KEY")
        )
        self._transport = transport
        self.timeout = timeout

    @property
    def available(self) -> bool:
        return self._transport is not None or bool(self.api_key)

    # ----------------------------------------------------------- prompting

    @staticmethod
    def brief(request: Dict[str, Any]) -> str:
        """The user turn: the prompt, who typed it, and the pattern that
        was showing when they did (its source, so 'slower and more
        purple' means THIS one) — or a clean slate."""
        who = request.get("author") or "someone at the sphere"
        lines = [f"Prompt from {who}: {request['prompt'].strip()}"]
        if request.get("name"):
            lines.append(f"They want to call it: {request['name']}")
        shown = request.get("shown")
        source = request.get("shown_source")
        if request.get("from_scratch") or not shown:
            lines.append(
                "Start from scratch (no base pattern)."
                if not shown
                else f"Start from scratch; ignore the current pattern ({shown})."
            )
        else:
            lines.append(
                f"The pattern showing when this was typed was `{shown}`. Treat "
                "the prompt as a request about it unless it clearly asks for "
                "something new — modify, extend, or answer it. Its source:"
            )
            lines.append("```python\n" + (source or "# (source unavailable)") + "\n```")
        return "\n".join(lines)

    def draft(self, request: Dict[str, Any]) -> tuple[str, str]:
        """``(code, note)`` for a request."""
        return extract(
            self._complete([{"role": "user", "content": self.brief(request)}])
        )

    def repair(self, request: Dict[str, Any], code: str, error: str) -> tuple[str, str]:
        """One repair round: the previous draft and what broke."""
        messages = [
            {"role": "user", "content": self.brief(request)},
            {"role": "assistant", "content": "```python\n" + code + "```"},
            {
                "role": "user",
                "content": (
                    "That module failed on the server:\n\n"
                    f"{error.strip()[-1500:]}\n\n"
                    "Fix it and reply with the complete corrected module in "
                    "one ```python block (a short note first is fine)."
                ),
            },
        ]
        return extract(self._complete(messages))

    # ------------------------------------------------------------ transport

    def _complete(self, messages: List[Dict[str, Any]]) -> str:
        if self._transport is not None:
            return self._transport(SYSTEM, messages)
        if not self.api_key:
            raise CoderUnavailable(
                "no coding model: set ANTHROPIC_API_KEY on the server"
            )
        import httpx

        response = httpx.post(
            API_URL,
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": API_VERSION,
                "content-type": "application/json",
            },
            json={
                "model": self.model,
                "max_tokens": MAX_TOKENS,
                "system": SYSTEM,
                "messages": messages,
            },
            timeout=self.timeout,
        )
        if response.status_code != 200:
            detail = response.text[:300]
            raise RuntimeError(f"model call failed ({response.status_code}): {detail}")
        blocks = response.json().get("content", [])
        return "".join(
            block.get("text", "") for block in blocks if block.get("type") == "text"
        )
