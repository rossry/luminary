"""Serpents roam the lattice: rainbow bodies, giant blips to eat, and every
swallowed color chases back through the body that ate it as it travels.

The corridor graph is recovered from the lights array exactly as in
`pacman.py` and `border_chase.py` (runs split at turns/gaps, endpoints
clustered into vertices, parallel beams either side of a seam merged into
one corridor) but kept much simpler: no thinning and no portals, just a
connected graph with per-corridor row/arc tables sorted by arclength.

Several snakes share that one graph (roughly one per 100 corridors, capped at
three -- the star gets 3, the small hex demo gets 1). They are co-simulated on
a single global timeline: an "event" is one snake arriving at a vertex and
choosing its next corridor, and the co-sim always advances whichever snake's
arrival is earliest, so at every decision every OTHER snake's committed trip
already covers that instant and its body there is fully determined. Because
all snakes start at s=0 at t=0 and move at one speed, each snake's head
arclength is exactly speed*t, so any snake's body window at any time is
[speed*t - L(t), speed*t] in its own path coordinate -- cheap to query as a
tron wall. Blips are SHARED (any snake can eat any blip); simulating them once
on this global timeline gives the physically-correct "first head to arrive
eats it" for free. Tron rules: entering a corridor another snake's body
occupies, or a vertex it covers, collapses ONLY the crasher (gulp flash +
retract to baby) -- the others continue. The safety planner treats other
snakes' bodies as walls and, dominantly, keeps snakes repelled from each
other's heads so encounters stay the occasional drama the brief wants rather
than routine (survival is the priority: "pretty > normal game").

Each snake's round is still simulated corridor-hop by corridor-hop rather than
at a fixed tick rate -- it moves at constant speed between the turns it
actually has to decide (a junction, an eaten blip), so its whole trip is a
sequence of closed-form segments. Concatenating each segment's per-corridor
row/arc table (offset by the trip's running arclength) and sorting once by
that arclength gives a single `(row, s)` table per snake for the entire round
-- the same idiom `border_chase.py` uses for its closed cycle, just for a
round-length, blip-aware, self-avoiding, tron-aware walk instead of a fixed
loop. Render loops over the snakes (each with its own palette) and paints the
shared blips once.

The signature mechanic falls out of that table almost for free. The body at
time tau is simply the window `[S_head(tau) - L(tau), S_head(tau)]` in that
arclength coordinate. A swallowed color is painted as a fixed-arclength band
`[A_i, A_i + w]` starting at the arclength where the eat happened -- ahead of
the head at that instant. Nothing further has to *reveal* the color: the
band only enters the visible window as the head's own forward motion grows
`S_head` past it, so it appears at the head first, purely as a side effect of
being a fixed point in a coordinate the window slides across. It recedes
toward the tail the same way, and vanishes once the tail edge overtakes
`A_i + w`. This is also why the body is never recolored in place -- a band
is written once, at a place the head hasn't drawn yet, never mutated after.

`L(tau)` (growth on eating, retraction on self-collision) is a short list of
eased breakpoints recorded during simulation and looked up by
`searchsorted`, the same closed-form-envelope idiom `plasma_storm.py` uses
for its bolts. Self-collision is detected during simulation too: entering a
corridor already inside the trailing `L` window triggers a retraction
breakpoint instead of a hard cut.

Blips sit on graph vertices (a uniform hashed choice over every vertex not
already holding a live blip and not within a couple of hops of the head),
rendered as breathing gaussian orbs at hero brightness, their reach down each
incident corridor capped by the junction's shortest arm so the glow stays
radially even instead of favoring the long bars. The head prefers corridors
that close the hop-distance to the nearest live blip, mixed with hashed noise
so the pull reads as a preference, not a leash, and a one-hop lookahead
softly steers it off pockets whose only other exits are already body.
Eating is unconditional on arrival -- whatever live blip sits on the vertex
the head lands on gets eaten, regardless of which blip the pull was chasing,
so passing through one always counts.
"""

import zlib
from typing import Dict, List, NamedTuple, Optional, Tuple

import numpy as np

from luminary.geometry.lights import LightColumns
from luminary.patterns.base import Pattern
from luminary.patterns.util import nan_to_black, seeded_random

# --- graph extraction (idiom shared with border_chase.py / pacman.py) ----
_TURN_DEG = 28.0  # split a strip where it bends more than this
_GAP_FACTOR = 4.0  # ... or jumps more than this multiple of its spacing
_MIN_RUN = 4  # runs shorter than this merge into a neighbor or drop

# --- round / motion --------------------------------------------------
_SPEED_MULT = 2.0  # corridor "unit" lengths per second
_ROUND_K = 4.0  # round length ~= K * total corridor length / speed. Raised ~2.5x
# from 1.6 (the Lady: "keep it going longer before resetting") -- on the star
# this lifts the round from ~186 s to ~465 s; the cap below is raised to match.
_ROUND_MIN = 30.0
_ROUND_MAX = 750.0  # was 300; raised 2.5x with _ROUND_K so nothing re-clips shorter
_FADE_OUT = 2.5  # round-boundary crossfade, seconds
_PULL_WEIGHT = 0.6  # mild pull toward a live blip; noise can still overturn it

# --- multiple snakes (tron) ------------------------------------------
_SNAKE_PER_CORRIDORS = 100  # num_snakes = clip(nc // this + 1, 1, _MAX_SNAKES):
# the 12-corridor hex gets 1, the 266-corridor star gets the 3-snake cap.
_MAX_SNAKES = 3
_OWN_VERTEX_PENALTY = 3.0  # planner nudge away from crossing your OWN body's
# vertex -- legal (no crash) but should read rarely, per the tron brief.
_CRASH_PENALTY = 50.0  # last-ditch penalty for an option that would enter a
# corridor/vertex held by ANOTHER snake (a crash). Only ever chosen when the
# safety planner has no non-crashing option left, so crashes stay occasional.
_AVOID_RADIUS = 5  # hops: keep clear of other snakes' heads. Treating only
# their CURRENT body as a wall let snakes converge on shared blips and collide
# constantly (~40 crashes/round with 3 snakes); a soft repulsion from each
# other's head vertex spreads them across the piece so encounters -- and thus
# crashes -- become the occasional drama the brief asks for (~4/round), not
# routine. This is the dominant lever on crash rate; body size barely moves it.
_AVOID_WEIGHT = 6.0  # penalty per hop inside _AVOID_RADIUS of another head
_SAFE_MARGIN = 1.5  # x current body length: the soft early-avoidance zone.
# An option is fully SAFE once its flood-filled reachable free arclength
# clears body length x this margin; below body length outright it's unsafe
# (survival can't be guaranteed); in between, a scaled penalty nudges the
# choice away early rather than waiting for a last-moment dodge.
_SOFT_TRAP_PENALTY = 2.0  # peak penalty at the unsafe edge of the soft zone
_TRAP_PENALTY = 4.0  # scales the "least bad" ranking in the rare fallback
# where every option is unsafe -- survival can't be guaranteed there, so
# gulp/retraction stays in as the graceful catch, it should just ~never fire

# --- body ---------------------------------------------------------------
_BABY_L_MULT = 1.4  # starting body length, x unit
_GROW_UNIT_MULT = 1.0  # body growth per eat, x unit
_GROW_RAMP = 2.0  # seconds to ramp a growth in -- never a jump
_MAX_BODY_FRAC = 0.12  # cap each snake's body at this fraction of total corridor
# length / num_snakes. NOT in the original single-agent design -- forced by the
# 2.5x-longer round x multiple snakes: unbounded growth let one body reach ~40%
# of the whole graph, so 3 of them saturated the board and crashes became
# routine (44/round) instead of occasional. Capping keeps survival the norm;
# eating past the cap still consumes the blip and paints its band, just adds no
# length. Floored so a small graph (the hex) still gets a few units of growth.
_RETRACT_TIME = 0.65  # MINIMUM seconds to retract after a crash (>= 0.5)
_CRASH_TAIL_RATE = 2.5  # max tail-sweep speed during a crash collapse, in
# corridor units (g.unit) per second. A fixed retract time lets a long body's
# tail sweep arbitrarily fast -- a 158-unit collapse at 0.65s measured 0.67
# L/frame single-light steps, ~3x the wire's 0.24 cap, which the codec would
# smear blue across the whole dying body. Scaling duration with collapse
# distance keeps each light's fade-out inside the slew envelope; the gulp
# flash still marks the crash instant, the body then drains tron-style.
_TAIL_FADE_FRAC = 0.30  # fraction of body length that fades in at the tail
_HUE_RATE = 46.0  # degrees per corridor unit of arclength (s/g.unit): the base
# rainbow cycle -- normalized by the corridor unit, not raw world arclength,
# so the hue step per light stays geometry-independent (a world-unit step
# scales with the strip's light spacing, which varies wildly by geometry).
_HUE_DRIFT = 42.0  # degrees/second: stripes flow tailward (against travel) at
# drift * unit / _HUE_RATE world-units/s -- ~19 world-units/s on the star
# with these constants (raised from 25 for a clearer counter-flow, the Lady:
# "change the colors so the colors move better"). Per-light per-frame hue slew
# from this term alone is drift/30fps =~ 1.4 deg/frame, far under the wire's
# 89 deg/frame cap.
_BODY_ENERGY = 1.05
_CHROMA_GATE = 1.4  # add_c = clip(chroma)*(1 - exp(-_CHROMA_GATE * lum)): gates
# the base/band chroma onset behind luminance. LOWERED from 2.6 -- with the
# higher-saturation palettes below, a steep gate makes a fresh head-lit light
# jump chroma over the 0.09/frame wire cap; a gentler gate spreads the same
# chroma rise across more frames. Measured max dC/frame stays within cap (report).

# --- traveling saturation wave on the base coat (bands are unaffected) ---
_CHROMA_WAVE_AMP = 0.45  # relative to base coat C; deepened from 0.25 for a
# more visible chroma pulse (trough ~0.55x base, crest ~1.45x) -- "colors move
# better". Still strictly > 0 so the base coat never fully desaturates.
_CHROMA_WAVE_LAMBDA_MULT = 4.0  # x unit
_CHROMA_WAVE_PERIOD = 6.7  # seconds; incommensurate with the blip breath (1.1s)

# --- the signature mechanic: swallowed-color bands -----------------------
_BAND_WIDTH_MULT = 4.0  # x unit; widened from 3.0 for harder-edged color
# identity per band (the Lady: "wider bands"). At _SPEED_MULT=2.0 ~2.0s to reveal.
_EDGE_BLEND_MULT = 0.5  # x unit, OKLab edge blend (~0.5 facet, per craft) -- kept
# at 0.5 facet: this is the hue-transition zone, and hardening it further would
# push the base->band hue slew toward the cap. Width, not edge, carries "harder".
_BAND_BULGE = 0.35  # brightness bulge riding the band -- the meal digesting

# --- per-snake palettes: (base-coat C, band C). Snake i on a geometry uses
# _PALETTES[i]. The star (3 snakes) therefore gets one vivid, one mid, one
# pastel body; the hex (1 snake) gets the vivid one. The Lady noticed nothing
# exceeded C~0.24 and wants "some snakes near max saturation": the vivid snake
# runs base C 0.25, band C 0.30, and the composite clips near 0.38 at overlaps
# -- comfortably "near max" (wire caps at 0.40), well past the 0.24 she flagged.
# Held back from the brief's floated 0.33/0.37: the dominant chroma-slew event
# is OKLab-vector cancellation where a blip and a differently-hued body facet
# overlap (composite chroma dives toward the null, then recovers), and its
# single-frame size scales with body chroma. At 0.33/0.37 the worst dived
# ~0.33/frame; 0.25/0.30 keeps 99.9% of ALL chroma motion under the 0.09/frame
# wire cap (matching the shipped single-snake baseline's distribution), with
# only the rarest overlap transients spiking to ~0.28. A measured slew
# tradeoff -- the requested saturation vs. codec smear on those transients.
_PALETTES: List[Tuple[float, float]] = [
    (0.25, 0.30),  # vivid   -- composite clips near 0.38 at overlaps
    (0.17, 0.22),  # mid
    (0.10, 0.14),  # pastel
]

# --- head -----------------------------------------------------------------
_HEAD_SIGMA_MULT = 0.22  # >= 0.19 x unit, the wire-sized floor
_HEAD_BOOST = 1.5

# --- gulp flash: a self-swallow's bright beat before the retraction ------
_GULP_DUR = 0.6  # matches _RETRACT_TIME so the flash and the retraction close together
_GULP_SIGMA_MULT = 0.5
_GULP_L = 3.2
_GULP_HC = (35.0, 0.05)  # near-white, a warm tint

# --- blips ------------------------------------------------------------
_BLIP_SIGMA_MULT = 0.40  # peak orb sigma, x unit
_BLIP_BREATH_PERIOD = 1.1
_BLIP_C = 0.20
_BLIP_L = 2.6  # hero energy: driven hard toward the wire's luminance ceiling
_BLIP_ATTACK = 0.35  # seconds
_BLIP_DEATH_FLARE = 0.10  # seconds: the "gulp!" swell right at the eat instant
_BLIP_DEATH_DUR = 0.45  # seconds: whole death envelope, closes to TRUE zero here
_BLIP_DEATH_PEAK = 1.3  # relative scale at the flare's peak
_BLIP_DEATH_TAU = 0.10  # decay time-constant, seconds -- see _blip_death_scale
_SPAWN_DELAY = (2.0, 4.0)  # seconds after an eat before the next spawn
_SPAWN_MIN_HOPS = 2  # a new blip never lands within this many hops of the head
_MAX_BLIPS_PER_CORRIDORS = 12  # max_blips = clip(nc // this, 1, 5); the 12-corridor
# hex demo gets 1, the 266-corridor star gets the 5-blip cap
_MAX_BLIPS_CAP = 5
_BLIP_REACH_K = 0.75  # radial symmetry: an orb's reach down any arm is capped at
# this fraction of the SHORTEST incident corridor at that junction, applied to
# every arm equally, so a short bar doesn't get swallowed while a long one only
# gets a partial stripe

# --- background -----------------------------------------------------------
_BG_L, _BG_C = 0.045, 0.020
_BG_H_PERIOD = 53.0
_GLITTER_FRAC = 0.030  # raised 3x from 0.010 -- the Lady: "a lot more background
# glitter". Still subordinate to the serpents; the field just visibly sparkles.
# Round 5: matched to constellations' twinkle-tier peak-L distribution
# (p50 0.159 / p90 0.369 / max 0.476, wide per-star variety) rather than one
# uniform amplitude. Each star's peak L is a piecewise-linear quantile
# function of a per-light hashed uniform: 80% of stars ("common") span
# [_GLITTER_PEAK_LO, _GLITTER_PEAK_MID], the brighter fifth span
# [_GLITTER_PEAK_MID, _GLITTER_PEAK_HI] -- continuous at the split, no gap.
_GLITTER_PEAK_LO = 0.09  # dimmest stars' peak L
_GLITTER_PEAK_MID = 0.20  # split point between common/bright tiers
_GLITTER_PEAK_HI = 0.46  # brightest stars' peak L -- well above the old
# uniform 0.245, giving "brighter sparkles" at the top of the distribution
# while the median comes down to match constellations' twinkle tier
_GLITTER_BRIGHT_SPLIT = 0.8  # fraction of stars in the common (dimmer) tier
_GLITTER_BG_FRAC = 0.10  # second, fainter tier: matching per-star peaks
# still left the sky reading emptier than constellations, whose density
# comes from its 10% faint background-star tier on top of the twinkle
# tier. Same remedy here: one light in ten glows faintly, disjoint from
# the twinkle stars (adjacent slice of the same hashed pick).
_GLITTER_BG_LO = 0.065  # faint tier per-light steady L floor...
_GLITTER_BG_HI = 0.12  # ...to ceiling (hashed per light)
_GLITTER_BG_TW = 0.02  # plus this much slow twinkle on top


def _smoothstep(v: np.ndarray, lo: float, hi: float) -> np.ndarray:
    u = np.clip((v - lo) / max(1e-9, hi - lo), 0.0, 1.0)
    out: np.ndarray = u * u * (3.0 - 2.0 * u)
    return out


def _blip_death_scale(age: float) -> float:
    """A relative brightness/size scale for an eaten blip, keyed on ``age``
    (seconds since it was eaten). 1.0 at age<=0 (still "alive" scale, so
    this multiplies cleanly onto the live formula with no seam); a "gulp!"
    flare rising to _BLIP_DEATH_PEAK over _BLIP_DEATH_FLARE; then an
    EXPONENTIAL decay (not linear) times a closing factor that forces TRUE
    zero at _BLIP_DEATH_DUR -- same idiom as pacman.py's death-flash
    `blow * close`. Exponential, not linear, matters here: the render's own
    L <- 1 - exp(-k*Lraw) compositing is steepest exactly where Lraw is
    small, so a *linear* raw-energy decay produces an accelerating drop in
    rendered brightness right at the end of the fade -- a bigger single-
    frame step than the fade was supposed to prevent. An exponential decay
    front-loads the drop while still in the compositing's saturated (flat)
    region and eases off exactly where the compositing gets steep."""
    if age <= 0.0:
        return 1.0
    if age < _BLIP_DEATH_FLARE:
        u = age / _BLIP_DEATH_FLARE
        ease = u * u * (3.0 - 2.0 * u)
        return 1.0 + (_BLIP_DEATH_PEAK - 1.0) * ease
    if age < _BLIP_DEATH_DUR:
        k = age - _BLIP_DEATH_FLARE
        span = _BLIP_DEATH_DUR - _BLIP_DEATH_FLARE
        decay = np.exp(-k / _BLIP_DEATH_TAU)
        close = max(0.0, 1.0 - k / span)
        return _BLIP_DEATH_PEAK * decay * close
    return 0.0


def _fnv(*vals: int) -> int:
    """Deterministic integer hash -- pure arithmetic, identical in any
    process (unlike Python's salted hash())."""
    h = 2166136261
    for v in vals:
        h = ((h ^ (int(v) & 0xFFFFFFFF)) * 16777619) & 0xFFFFFFFF
    return h


def _frac(*vals: int) -> float:
    """Deterministic pseudo-uniform value in [0, 1) from integer arithmetic."""
    return _fnv(*vals) / 4294967296.0


def _build_runs(a: np.ndarray) -> Tuple[List[np.ndarray], float]:
    """Split each strip into straight runs of light rows; return runs
    and the median light spacing."""
    keys = a[:, LightColumns.CONTROLLER].astype(np.int64) * 8 + a[
        :, LightColumns.CHANNEL
    ].astype(np.int64)
    runs: List[np.ndarray] = []
    spacings = []
    for k in np.unique(keys):
        rows = np.flatnonzero(keys == k)
        xy = a[np.ix_(rows, np.array([LightColumns.X, LightColumns.Y], np.intp))]
        finite = ~np.isnan(xy).any(axis=1)
        rows, xy = rows[finite], xy[finite]
        if len(rows) < 2:
            continue
        d = np.diff(xy, axis=0)
        seg = np.hypot(d[:, 0], d[:, 1])
        spacings.append(seg)
        med = float(np.median(seg))
        ang = np.abs(np.diff(np.arctan2(d[:, 1], d[:, 0])))
        ang = np.degrees(np.minimum(ang, 2.0 * np.pi - ang))
        cut = seg > _GAP_FACTOR * med
        cut[1:] |= ang > _TURN_DEG
        starts = np.concatenate([[0], np.flatnonzero(cut) + 1, [len(rows)]])
        pieces = [rows[s:e] for s, e in zip(starts[:-1], starts[1:])]
        merged: List[np.ndarray] = []
        for p in pieces:
            if merged and len(p) < _MIN_RUN:
                prev = merged[-1]
                gap = float(
                    np.hypot(
                        a[p[0], LightColumns.X] - a[prev[-1], LightColumns.X],
                        a[p[0], LightColumns.Y] - a[prev[-1], LightColumns.Y],
                    )
                )
                if gap < _GAP_FACTOR * med:
                    merged[-1] = np.concatenate([prev, p])
                    continue
            merged.append(p)
        # Forward pass: a short piece with no mergeable predecessor -- on
        # this build every strip's FIRST light sits at a hub center and
        # bends away from its strut, so the backward-only merge dropped it
        # and the hub center stayed permanently dark. Attach such pieces to
        # the following piece when spatially contiguous.
        fwd: List[np.ndarray] = []
        pend: Optional[np.ndarray] = None
        for p in merged:
            if pend is not None:
                gap = float(
                    np.hypot(
                        a[p[0], LightColumns.X] - a[pend[-1], LightColumns.X],
                        a[p[0], LightColumns.Y] - a[pend[-1], LightColumns.Y],
                    )
                )
                if gap < _GAP_FACTOR * med:
                    p = np.concatenate([pend, p])
                pend = None
            if len(p) < _MIN_RUN:
                pend = p
                continue
            fwd.append(p)
        runs.extend(fwd)
    med_all = float(np.median(np.concatenate(spacings))) if spacings else 1.0
    return runs, med_all


_SPLIT_EPS = 0.25  # x unit: a run interior passing this close to a hub is a
# through-run. Measured on the star: the 22 genuine straight-through passes
# sit at 0.03-0.08 units from their hub centroid, the nearest false
# candidate (an inset inner-beam corner alongside a strut) at 0.635 -- 0.25
# has ~3x margin to both. Raw endpoint distance is NOT a usable criterion
# (inner-beam corners sit within cluster-tol of strut interiors everywhere;
# a first attempt with it shredded 422 runs into 1098 pieces).


def _split_runs_at_junctions(
    a: np.ndarray, runs: List[np.ndarray], tol: float, unit: float
) -> List[np.ndarray]:
    """Split any run whose interior passes within ``_SPLIT_EPS * unit`` of a
    clustered hub (vertex centroid of a provisional endpoint clustering).
    The bend test alone reads two near-collinear struts as ONE run, so the
    hub between them gets a vertex (other struts terminate there) but no
    incidence for the straight-through run -- a blip sitting on that hub
    then lights every arm except the straight-through pair (the one-sided
    spokes the Lady saw). Splitting at the closest interior light makes
    both halves incident: their new endpoints sit essentially on the hub,
    so the caller's re-clustering folds them into the hub's vertex."""
    labels = _cluster_endpoints(a, runs, tol)
    nv = int(labels.max()) + 1
    pts = np.array(
        [
            [a[r[i], LightColumns.X], a[r[i], LightColumns.Y]]
            for r in runs
            for i in (0, -1)
        ]
    )
    cent = np.zeros((nv, 2))
    cnt = np.zeros(nv)
    for j, lab in enumerate(labels):
        cent[lab] += pts[j]
        cnt[lab] += 1
    cent /= np.maximum(cnt, 1)[:, None]

    eps = _SPLIT_EPS * unit
    xcols = np.array([LightColumns.X, LightColumns.Y], np.intp)
    out: List[np.ndarray] = []
    for e, r in enumerate(runs):
        own = {int(labels[2 * e]), int(labels[2 * e + 1])}
        foreign = np.array([v for v in range(nv) if v not in own], np.intp)
        stack = [r]
        while stack:
            rr = stack.pop()
            if len(foreign) and len(rr) >= 2 * _MIN_RUN:
                xy = a[np.ix_(rr, xcols)]
                d = np.hypot(
                    xy[:, None, 0] - cent[None, foreign, 0],
                    xy[:, None, 1] - cent[None, foreign, 1],
                ).min(axis=1)
                inner = d[_MIN_RUN : len(rr) - _MIN_RUN]
                if len(inner) and inner.min() < eps:
                    k = _MIN_RUN + int(inner.argmin())
                    stack.append(rr[: k + 1])
                    stack.append(rr[k + 1 :])
                    continue
            out.append(rr)
    return out


def _cluster_endpoints(a: np.ndarray, runs: List[np.ndarray], tol: float) -> np.ndarray:
    """Union-find run endpoints into vertex labels; run i's ends are
    out[2i] (first light) and out[2i+1] (last)."""
    pts = np.array(
        [
            [a[r[i], LightColumns.X], a[r[i], LightColumns.Y]]
            for r in runs
            for i in (0, -1)
        ]
    )
    n = len(pts)
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    d2 = ((pts[:, None, :] - pts[None, :, :]) ** 2).sum(-1)
    for i, j in zip(*np.nonzero(d2 < tol * tol)):
        if i < j:
            ri, rj = find(int(i)), find(int(j))
            if ri != rj:
                parent[max(ri, rj)] = min(ri, rj)
    roots = np.array([find(i) for i in range(n)])
    labels: np.ndarray = np.unique(roots, return_inverse=True)[1]
    return labels


def _corridor_adj(
    cu: np.ndarray, cv: np.ndarray, nv: int
) -> List[List[Tuple[int, int]]]:
    """adj[v] = [(other vertex, corridor), ...], ordered by corridor index
    so every traversal of it is deterministic."""
    adj: List[List[Tuple[int, int]]] = [[] for _ in range(nv)]
    for ci in range(len(cu)):
        adj[int(cu[ci])].append((int(cv[ci]), ci))
        adj[int(cv[ci])].append((int(cu[ci]), ci))
    for lst in adj:
        lst.sort(key=lambda oc: oc[1])
    return adj


def _hop_distances(adj: List[List[Tuple[int, int]]], nv: int) -> np.ndarray:
    """All-pairs hop distance by BFS."""
    from collections import deque

    far = nv + 1
    dist = np.full((nv, nv), far, np.int32)
    for s in range(nv):
        dist[s, s] = 0
        q = deque([s])
        while q:
            u = q.popleft()
            for w, _ in adj[u]:
                if dist[s, w] == far:
                    dist[s, w] = dist[s, u] + 1
                    q.append(w)
    return dist


class _Graph(NamedTuple):
    cu: np.ndarray  # (nc,) corridor endpoints
    cv: np.ndarray
    clen: np.ndarray  # (nc,) corridor length, world units
    rows: np.ndarray  # (m,) light row per corridor visit
    arc: np.ndarray  # (m,) arclength from cu, ascending within a corridor
    ptr: np.ndarray  # (nc+1,) slice bounds into rows/arc
    adj: List[List[Tuple[int, int]]]  # adj[v] = [(other vertex, corridor), ...]
    dist: np.ndarray  # (nv, nv) hop distance
    vxy: np.ndarray  # (nv, 2)
    unit: float  # median corridor length
    nv: int
    nc: int
    start: int  # a far-out vertex the round begins from (== starts[0])
    starts: Tuple[int, ...]  # one far-apart start vertex per snake
    num_snakes: int
    round_len: float
    max_blips: int
    max_body: float  # per-snake body-length cap, world units


def _largest_component(
    cu: np.ndarray, cv: np.ndarray, nv: int
) -> Optional[Tuple[np.ndarray, np.ndarray]]:
    parent = list(range(nv))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for u, v in zip(cu.tolist(), cv.tolist()):
        ru, rv = find(u), find(v)
        if ru != rv:
            parent[max(ru, rv)] = min(ru, rv)
    roots = np.array([find(i) for i in range(nv)])
    vals, counts = np.unique(roots, return_counts=True)
    best = vals[int(np.argmax(counts))]
    keep_v = roots == best
    if int(keep_v.sum()) < 6:
        return None
    keep_c = keep_v[cu] & keep_v[cv]
    if int(keep_c.sum()) < 4:
        return None
    return keep_v, keep_c


def _build_graph(a: np.ndarray) -> Optional[_Graph]:
    runs, spacing = _build_runs(a)
    if len(runs) < 6:
        return None
    chords = [
        float(
            np.hypot(
                a[r[-1], LightColumns.X] - a[r[0], LightColumns.X],
                a[r[-1], LightColumns.Y] - a[r[0], LightColumns.Y],
            )
        )
        for r in runs
    ]
    unit = float(np.median(chords))
    tol = max(3.0 * spacing, 0.3 * unit)
    runs = _split_runs_at_junctions(a, runs, tol, unit)
    labels = _cluster_endpoints(a, runs, tol)

    groups_of: List[Optional[Tuple[int, int]]] = []
    flip_of: List[bool] = []
    pairs = set()
    for e, r in enumerate(runs):
        u, v = int(labels[2 * e]), int(labels[2 * e + 1])
        if u == v:
            groups_of.append(None)
            flip_of.append(False)
            continue
        groups_of.append((min(u, v), max(u, v)))
        flip_of.append(u > v)
        pairs.add((min(u, v), max(u, v)))
    if len(pairs) < 4:
        return None

    # One corridor per vertex pair -- the beams either side of a panel seam
    # merge into a single lane, as in pacman.py / border_chase.py.
    by_pair: Dict[Tuple[int, int], List[int]] = {}
    for e, g in enumerate(groups_of):
        if g is not None:
            by_pair.setdefault(g, []).append(e)
    order_keys = sorted(by_pair)
    cu = np.array([p[0] for p in order_keys], np.int64)
    cv = np.array([p[1] for p in order_keys], np.int64)
    clen = np.zeros(len(order_keys))
    rows_out, arc_out, counts = [], [], []
    for ci, pair in enumerate(order_keys):
        members = by_pair[pair]
        alongs, lens = [], []
        for e in members:
            r = runs[e]
            xy = a[np.ix_(r, np.array([LightColumns.X, LightColumns.Y], np.intp))]
            seg = np.hypot(*np.diff(xy, axis=0).T)
            along = np.concatenate([[0.0], np.cumsum(seg)])
            lens.append(max(1e-6, float(along[-1])))
            if flip_of[e]:
                along = along[-1] - along
            alongs.append(along)
        clen[ci] = float(np.mean(lens))
        rows_out.append(np.concatenate([runs[e] for e in members]))
        arc_out.append(
            np.concatenate([along * (clen[ci] / ln) for along, ln in zip(alongs, lens)])
        )
        counts.append(sum(len(runs[e]) for e in members))
    rows = np.concatenate(rows_out).astype(np.int64)
    arc = np.concatenate(arc_out)
    ptr = np.concatenate([[0], np.cumsum(counts)]).astype(np.int64)
    for ci in range(len(order_keys)):
        lo, hi = int(ptr[ci]), int(ptr[ci + 1])
        order = np.argsort(arc[lo:hi], kind="stable")
        rows[lo:hi] = rows[lo:hi][order]
        arc[lo:hi] = arc[lo:hi][order]

    nv = int(labels.max()) + 1
    vxy = np.zeros((nv, 2))
    for e, r in enumerate(runs):
        for i, end in ((0, 0), (-1, 1)):
            vxy[labels[2 * e + end]] = (
                a[r[i], LightColumns.X],
                a[r[i], LightColumns.Y],
            )

    comp = _largest_component(cu, cv, nv)
    if comp is None:
        return None
    keep_v, keep_c = comp
    remap = np.full(nv, -1, np.int64)
    remap[np.flatnonzero(keep_v)] = np.arange(int(keep_v.sum()))
    kept_idx = np.flatnonzero(keep_c)
    rows2_l, arc2_l, counts2 = [], [], []
    for ci in kept_idx:
        lo, hi = int(ptr[ci]), int(ptr[ci + 1])
        rows2_l.append(rows[lo:hi])
        arc2_l.append(arc[lo:hi])
        counts2.append(hi - lo)
    cu2 = remap[cu[keep_c]]
    cv2 = remap[cv[keep_c]]
    clen2 = clen[keep_c].copy()
    rows2 = np.concatenate(rows2_l) if rows2_l else np.empty(0, np.int64)
    arc2 = np.concatenate(arc2_l) if arc2_l else np.empty(0, np.float64)
    ptr2 = np.concatenate([[0], np.cumsum(counts2)]).astype(np.int64)
    vxy2 = vxy[keep_v]
    nv2 = int(keep_v.sum())
    nc2 = len(cu2)

    adj = _corridor_adj(cu2, cv2, nv2)
    dist = _hop_distances(adj, nv2)
    num_snakes = int(np.clip(nc2 // _SNAKE_PER_CORRIDORS + 1, 1, _MAX_SNAKES))
    starts = _pick_starts(dist, nv2, num_snakes)
    start = starts[0]
    total_len = float(clen2.sum())
    speed = _SPEED_MULT * unit
    round_len = float(
        np.clip(_ROUND_K * total_len / max(speed, 1e-6), _ROUND_MIN, _ROUND_MAX)
    )
    max_blips = int(np.clip(nc2 // _MAX_BLIPS_PER_CORRIDORS, 1, _MAX_BLIPS_CAP))
    total_units = total_len / max(unit, 1e-6)
    max_body = unit * max(
        _BABY_L_MULT + 4.0 * _GROW_UNIT_MULT,
        _MAX_BODY_FRAC * total_units / num_snakes,
    )

    return _Graph(
        cu2,
        cv2,
        clen2,
        rows2,
        arc2,
        ptr2,
        adj,
        dist,
        vxy2,
        unit,
        nv2,
        nc2,
        start,
        starts,
        num_snakes,
        round_len,
        max_blips,
        max_body,
    )


def _pick_starts(dist: np.ndarray, nv: int, num: int) -> Tuple[int, ...]:
    """Farthest-point sampling for ``num`` well-separated start vertices:
    the first is the graph's most-central-by-eccentricity vertex (same choice
    the single-snake round always used), each subsequent one maximizes its
    minimum hop distance to those already chosen. Deterministic -- ties in
    argmax resolve to the lowest index, independent of dict/set order."""
    first = int(np.argmax(dist.sum(axis=1)))
    chosen = [first]
    while len(chosen) < num:
        mind = dist[chosen].min(axis=0).astype(np.int64)
        mind[chosen] = -1  # never re-pick a chosen vertex
        chosen.append(int(np.argmax(mind)))
    return tuple(chosen)


def _vertex_blob(
    g: _Graph, v: int, sigma: float, max_reach: Optional[float] = None
) -> Tuple[List[np.ndarray], List[np.ndarray]]:
    """Light rows and weights for a glow sitting on a junction, reaching a
    little way down every corridor that meets there -- for blips, which sit
    exactly on a vertex.

    ``max_reach``, if given, caps how far the glow reaches down EVERY arm
    equally (radial symmetry) -- without it, a short bar off a junction
    gets fully swallowed while a long one only shows a partial stripe."""
    rows: List[np.ndarray] = []
    ws: List[np.ndarray] = []
    cut = 3.0 * sigma if max_reach is None else min(3.0 * sigma, max_reach)
    inv = -0.5 / (sigma * sigma)
    for _w, c in g.adj[v]:
        lo, hi = int(g.ptr[c]), int(g.ptr[c + 1])
        d = g.arc[lo:hi]
        if int(g.cv[c]) == v:
            d = float(g.clen[c]) - d
        keep = d < cut
        if keep.any():
            rows.append(g.rows[lo:hi][keep])
            ws.append(np.exp(inv * d[keep] ** 2))
    return rows, ws


# --- simulation ------------------------------------------------------


def _free_space(
    g: _Graph, start_v: int, banned_c: int, occ_mask: np.ndarray, threshold: float
) -> float:
    """Flood-filled corridor arclength reachable from ``start_v`` through
    corridors that are neither body-occupied (``occ_mask``) nor ``banned_c``
    (the corridor about to be entered -- it becomes occupied the instant the
    head commits to it, so it's excluded from its own downstream search).

    The classic snake-survival check: if the head can still reach at least
    as much open corridor as its own body is long, it can never be forced to
    self-collide -- worst case it just keeps circling that open region until
    its tail recedes and frees more of the board. This ignores the tail
    freeing up *during* the traversal (a strictly conservative simplification
    -- by the time the head is deep into newly-opened territory, the tail has
    only receded further, so treating "now" as the permanent floor never
    overstates safety).

    Stops early once the running total clears ``threshold`` -- callers only
    need to know "at least this much," not the exact figure, except in the
    rare fallback where every option is unsafe and the exact total is used
    to rank "least bad." That early exit is what keeps this cheap: most
    calls resolve within a few hops of ``start_v``, not a full graph walk.
    """
    visited_c = np.zeros(g.nc, bool)
    visited_c[banned_c] = True
    seen_v = [False] * g.nv
    seen_v[start_v] = True
    stack = [start_v]
    total = 0.0
    while stack:
        u = stack.pop()
        for w2, c2 in g.adj[u]:
            if visited_c[c2] or occ_mask[c2]:
                continue
            visited_c[c2] = True
            total += float(g.clen[c2])
            if total > threshold:
                return total
            if not seen_v[w2]:
                seen_v[w2] = True
                stack.append(w2)
    return total


class _SnakeRound(NamedTuple):
    """One snake's whole-round timeline -- the exact single-agent table the
    original design produced, now one per snake. path/ev/bp are looked up at
    render time; nothing here references the other snakes (all inter-snake
    coupling was resolved during simulation)."""

    path_rows: np.ndarray  # (m,) light row per path point, ascending by path_s
    path_s: np.ndarray  # (m,) arclength since round start
    path_smax: float
    ev_a: np.ndarray  # (e,) eat arclength, ascending
    ev_hue: np.ndarray  # (e,)
    bp_t: np.ndarray  # (b,) L-schedule breakpoints, ascending, bp_t[0] == 0
    bp_from: np.ndarray
    bp_to: np.ndarray
    bp_dur: np.ndarray


class _RoundSet(NamedTuple):
    """A whole round: every snake's timeline plus the SHARED blip records
    (any snake can eat any blip, so blips are simulated once, globally, not
    per snake). Crash tallies are carried for reporting."""

    snakes: List[_SnakeRound]
    blip_v: np.ndarray  # (k,) vertex
    blip_hue: np.ndarray
    blip_t0: np.ndarray  # spawned
    blip_t1: np.ndarray  # eaten (or well past round end if never eaten)
    n_crash_self: int  # own-body corridor re-entries (the classic self-swallow)
    n_crash_tron: int  # crashes into ANOTHER snake's corridor or covered vertex


class _SnakeState:
    """Mutable per-snake bookkeeping during co-simulation. One event = this
    snake arriving at ``v_cur`` at time ``t_cur`` and choosing its next
    corridor; the co-sim always advances whichever snake's arrival is
    earliest, so at any decision every OTHER snake's committed trip already
    covers the decision instant and its body there is fully determined."""

    __slots__ = (
        "sid",
        "v_cur",
        "prev_v",
        "t_cur",
        "s_cur",
        "l_state",
        "mstep",
        "done",
        "trip_c",
        "trip_rev",
        "trip_entry_s",
        "trip_clen",
        "trip_vfrom",
        "trip_vto",
        "ev_a",
        "ev_hue",
        "bp_t",
        "bp_from",
        "bp_to",
        "bp_dur",
        "n_self",
        "n_tron",
    )

    def __init__(self, sid: int, start: int, baby_l: float) -> None:
        self.sid = sid
        self.v_cur = start
        self.prev_v = -1
        self.t_cur = 0.0
        self.s_cur = 0.0
        self.l_state = baby_l
        self.mstep = 0
        self.done = False
        self.trip_c: List[int] = []
        self.trip_rev: List[bool] = []
        self.trip_entry_s: List[float] = []
        self.trip_clen: List[float] = []
        self.trip_vfrom: List[int] = []
        self.trip_vto: List[int] = []
        self.ev_a: List[float] = []
        self.ev_hue: List[float] = []
        self.bp_t: List[float] = [0.0]
        self.bp_from: List[float] = [baby_l]
        self.bp_to: List[float] = [baby_l]
        self.bp_dur: List[float] = [0.0]
        self.n_self = 0
        self.n_tron = 0

    def l_now(self, t: float) -> float:
        """TRUE eased L at time t from the breakpoints recorded so far --
        identical easing to render-side _l_at. Growth ramps commonly overlap,
        so a new breakpoint's ``from`` must be this eased value, not the last
        target (which may not have been reached yet)."""
        i = len(self.bp_t) - 1
        dur = self.bp_dur[i]
        frac = 0.0 if dur <= 0.0 else max(0.0, min(1.0, (t - self.bp_t[i]) / dur))
        ease = frac * frac * (3.0 - 2.0 * frac)
        return self.bp_from[i] + (self.bp_to[i] - self.bp_from[i]) * ease


def _self_occ(sn: "_SnakeState", nc: int) -> np.ndarray:
    """Corridors within a snake's OWN trailing body window (the classic
    self-collision mask -- unchanged from the single-agent round)."""
    mask = np.zeros(nc, bool)
    floor = sn.s_cur - sn.l_state
    i = len(sn.trip_c) - 1
    while i >= 0 and sn.trip_entry_s[i] >= floor:
        mask[sn.trip_c[i]] = True
        i -= 1
    return mask


def _self_vtx(sn: "_SnakeState") -> set:
    """Vertices the snake's own body currently sits on -- for the planner's
    own-vertex-crossing penalty (legal, but should read rarely)."""
    out = set()
    floor = sn.s_cur - sn.l_state
    i = len(sn.trip_c) - 1
    while i >= 0 and sn.trip_entry_s[i] >= floor:
        out.add(sn.trip_vfrom[i])
        out.add(sn.trip_vto[i])
        i -= 1
    return out


def _other_body(sn: "_SnakeState", t: float, speed: float) -> Tuple[set, set]:
    """Corridors and vertices covered by snake ``sn``'s body at global time
    ``t`` -- the tron wall another snake must not enter. Head arclength is
    speed*t for every snake (all start at s=0,t=0 and move at one speed), so
    the window is [speed*t - L(t), speed*t] in this snake's own path
    coordinate; walk its committed visits back from newest until they fall
    behind the tail. Cheap: the body spans only a few corridors."""
    head = speed * t
    floor = head - sn.l_now(t)
    corr: set = set()
    vtx: set = set()
    i = len(sn.trip_c) - 1
    while i >= 0:
        s0 = sn.trip_entry_s[i]
        s1 = s0 + sn.trip_clen[i]
        if s1 <= floor:
            break  # this and all older visits are behind the tail
        if s0 < head:
            corr.add(sn.trip_c[i])
            if floor <= s0 <= head:
                vtx.add(sn.trip_vfrom[i])
            if floor <= s1 <= head:
                vtx.add(sn.trip_vto[i])
        i -= 1
    return corr, vtx


def _sim_all(g: _Graph, idx: int) -> _RoundSet:
    speed = _SPEED_MULT * g.unit
    baby_l = _BABY_L_MULT * g.unit
    grow_unit = _GROW_UNIT_MULT * g.unit
    round_len = g.round_len
    nc = g.nc

    snakes = [_SnakeState(i, g.starts[i], baby_l) for i in range(g.num_snakes)]

    blips: Dict[int, Dict[str, float]] = {}
    blip_records: List[Tuple[int, float, float, float]] = []
    blip_counter = 0
    pending_spawns: List[float] = []

    def spawn_blip(now: float) -> None:
        # Uniform over eligible vertices: not live, and (stepwise-relaxed)
        # far enough from EVERY snake head. The hop floor relaxes to -1 when
        # nothing qualifies -- which both keeps small graphs (the diameter-2
        # hex, where dist>2 is always empty) from starving of blips and keeps
        # a crowded board spawning. Deterministic pick via _fnv.
        nonlocal blip_counter
        live_v = {int(b["v"]) for b in blips.values()}
        dmin_v = np.min([g.dist[sn.v_cur] for sn in snakes], axis=0)
        cands: List[int] = []
        for floor in (_SPAWN_MIN_HOPS, 1, 0, -1):
            cands = [
                v for v in range(g.nv) if v not in live_v and int(dmin_v[v]) > floor
            ]
            if cands:
                break
        if not cands:
            return
        pick = cands[_fnv(idx, blip_counter, 7) % len(cands)]
        hue = 360.0 * _frac(idx, blip_counter, 11)
        blips[blip_counter] = {"v": float(pick), "hue": hue, "t0": now}
        blip_counter += 1

    for _ in range(g.max_blips):
        spawn_blip(0.0)

    step = 0
    max_steps = 60000
    while step < max_steps:
        active = [sn for sn in snakes if not sn.done]
        if not active:
            break
        sn = min(active, key=lambda s: (s.t_cur, s.sid))
        if sn.t_cur >= round_len:
            break  # earliest arrival is already past the round -- all are
        step += 1
        t_now = sn.t_cur

        if pending_spawns:
            still = []
            for pt in pending_spawns:
                if pt <= t_now and len(blips) < g.max_blips:
                    spawn_blip(pt)
                else:
                    still.append(pt)
            pending_spawns = still

        # Other snakes as tron walls at this instant (union of their bodies).
        other_mask = np.zeros(nc, bool)
        other_vtx: set = set()
        for oj in snakes:
            if oj is sn:
                continue
            oc, ov = _other_body(oj, t_now, speed)
            if oc:
                other_mask[list(oc)] = True
            other_vtx |= ov

        om = _self_occ(sn, nc)
        combined = om | other_mask  # everything the flood-fill treats as wall

        opts_all = g.adj[sn.v_cur]
        opts_nb = [(w, c) for w, c in opts_all if w != sn.prev_v] or opts_all
        # Prefer options whose corridor is not a wall (self body or another
        # snake's body). A covered destination vertex is NOT filtered here --
        # only penalized below -- because vertex coverage sweeps many junctions
        # as bodies move, and hard-excluding it boxed snakes into far more
        # crashes than it prevented. So corridors are the tron walls; the
        # vertex-crossing rule survives as a strong penalty + crash detection.
        opts_pref = [(w, c) for w, c in opts_nb if not combined[c]] or opts_nb

        free_of: Dict[Tuple[int, int], float] = {}
        for w, c in opts_pref:
            free_of[(w, c)] = _free_space(g, w, c, combined, _SAFE_MARGIN * sn.l_state)
        safe_opts = [oc for oc in opts_pref if free_of[oc] >= sn.l_state]
        options = safe_opts or opts_pref
        if not options:
            sn.done = True
            continue

        blip_vs = [int(b["v"]) for b in blips.values()]
        self_vtx = _self_vtx(sn)
        other_heads = [oj.v_cur for oj in snakes if oj is not sn]
        best_score, w_next, c_next = None, options[0][0], options[0][1]
        for w, c in options:
            dmin = min((int(g.dist[w, bv]) for bv in blip_vs), default=0)
            free = free_of[(w, c)]
            if free < sn.l_state:
                soft_pen = _TRAP_PENALTY * (
                    1.0 - min(1.0, free / max(sn.l_state, 1e-6))
                )
            elif free < _SAFE_MARGIN * sn.l_state:
                span = max(1e-6, (_SAFE_MARGIN - 1.0) * sn.l_state)
                frac = (free - sn.l_state) / span
                soft_pen = _SOFT_TRAP_PENALTY * (1.0 - frac)
            else:
                soft_pen = 0.0
            own_pen = _OWN_VERTEX_PENALTY if w in self_vtx else 0.0
            crash_pen = _CRASH_PENALTY if (combined[c] or w in other_vtx) else 0.0
            avoid_pen = 0.0
            for oh in other_heads:
                slack = _AVOID_RADIUS - int(g.dist[w, oh])
                if slack > 0:
                    avoid_pen += _AVOID_WEIGHT * slack
            score = (
                dmin * _PULL_WEIGHT
                + _frac(idx, sn.sid, sn.mstep, c)
                + soft_pen
                + own_pen
                + crash_pen
                + avoid_pen
            )
            if best_score is None or score < best_score:
                best_score, w_next, c_next = score, w, c
        sn.mstep += 1

        self_hit = bool(om[c_next])
        tron_hit = bool(other_mask[c_next]) or (w_next in other_vtx)
        rev = sn.v_cur != int(g.cu[c_next])
        clen_c = float(g.clen[c_next])

        sn.trip_c.append(c_next)
        sn.trip_rev.append(rev)
        sn.trip_entry_s.append(sn.s_cur)
        sn.trip_clen.append(clen_c)
        sn.trip_vfrom.append(sn.v_cur)
        sn.trip_vto.append(w_next)

        entry_t = sn.t_cur
        exit_t = sn.t_cur + clen_c / speed
        exit_s = sn.s_cur + clen_c

        if self_hit or tron_hit:
            # The crasher collapses: gulp flash (recovered render-side from
            # this retraction breakpoint) then retract to baby length. Only
            # THIS snake retracts; the others continue untouched.
            true_l = sn.l_now(entry_t)
            sn.bp_t.append(entry_t)
            sn.bp_from.append(true_l)
            sn.bp_to.append(baby_l)
            # Slew-fit: smoothstep easing peaks at 1.5x the mean rate, so
            # budget for the peak when bounding the tail-sweep speed.
            sn.bp_dur.append(
                max(
                    _RETRACT_TIME,
                    1.5 * (true_l - baby_l) / (_CRASH_TAIL_RATE * g.unit),
                )
            )
            sn.l_state = baby_l
            if self_hit:
                sn.n_self += 1
            else:
                sn.n_tron += 1

        sn.t_cur, sn.s_cur = exit_t, exit_s
        sn.prev_v, sn.v_cur = sn.v_cur, w_next
        if sn.t_cur >= round_len:
            sn.done = True

        eaten_ids = sorted(bid for bid, b in blips.items() if int(b["v"]) == sn.v_cur)
        for bid in eaten_ids:
            b = blips.pop(bid)
            blip_records.append((int(b["v"]), b["hue"], b["t0"], exit_t))
            sn.ev_a.append(sn.s_cur)
            sn.ev_hue.append(b["hue"])
            # Eating always consumes the blip and paints its band; growth is
            # capped at g.max_body so multiple snakes can't saturate the board.
            true_l = sn.l_now(exit_t)
            target = min(true_l + grow_unit, g.max_body)
            sn.bp_t.append(exit_t)
            sn.bp_from.append(true_l)
            sn.bp_to.append(target)
            sn.bp_dur.append(_GROW_RAMP)
            sn.l_state = min(sn.l_state + grow_unit, g.max_body)
            delay = _SPAWN_DELAY[0] + (_SPAWN_DELAY[1] - _SPAWN_DELAY[0]) * _frac(
                idx, bid, 13
            )
            pending_spawns.append(exit_t + delay)

    for bid, b in blips.items():
        blip_records.append((int(b["v"]), b["hue"], b["t0"], round_len + 1.0e6))

    def arr(vals: List[float]) -> np.ndarray:
        return np.array(vals, np.float64) if vals else np.empty(0, np.float64)

    snake_rounds: List[_SnakeRound] = []
    n_self = 0
    n_tron = 0
    for sn in snakes:
        rows_out, s_out = [], []
        for k in range(len(sn.trip_c)):
            c, rv, s0 = sn.trip_c[k], sn.trip_rev[k], sn.trip_entry_s[k]
            lo, hi = int(g.ptr[c]), int(g.ptr[c + 1])
            rr, aa = g.rows[lo:hi], g.arc[lo:hi]
            local = (float(g.clen[c]) - aa) if rv else aa
            rows_out.append(rr)
            s_out.append(s0 + local)
        if rows_out:
            rows_cat = np.concatenate(rows_out)
            s_cat = np.concatenate(s_out)
            order = np.argsort(s_cat, kind="stable")
            path_rows, path_s = rows_cat[order], s_cat[order]
        else:
            path_rows, path_s = np.empty(0, np.int64), np.empty(0, np.float64)
        snake_rounds.append(
            _SnakeRound(
                path_rows,
                path_s,
                float(sn.s_cur),
                arr(sn.ev_a),
                arr(sn.ev_hue),
                arr(sn.bp_t),
                arr(sn.bp_from),
                arr(sn.bp_to),
                arr(sn.bp_dur),
            )
        )
        n_self += sn.n_self
        n_tron += sn.n_tron

    blip_v = arr([float(r[0]) for r in blip_records]).astype(np.int64)
    blip_hue = arr([r[1] for r in blip_records])
    blip_t0 = arr([r[2] for r in blip_records])
    blip_t1 = arr([r[3] for r in blip_records])

    return _RoundSet(snake_rounds, blip_v, blip_hue, blip_t0, blip_t1, n_self, n_tron)


def _l_at(rd: _SnakeRound, tau: float) -> float:
    i = int(np.searchsorted(rd.bp_t, tau, side="right")) - 1
    i = max(0, i)
    dur = float(rd.bp_dur[i])
    frac = 0.0 if dur <= 0.0 else float(np.clip((tau - rd.bp_t[i]) / dur, 0.0, 1.0))
    ease = frac * frac * (3.0 - 2.0 * frac)
    return float(rd.bp_from[i] + (rd.bp_to[i] - rd.bp_from[i]) * ease)


class Serpent(Pattern):
    name = "serpent"
    description = "A rainbow serpent hunting giant blips; swallowed color chases back through its body"

    def __init__(self) -> None:
        self._graph_cache: Dict[Tuple[int, int], Optional[_Graph]] = {}
        self._round_cache: Dict[Tuple[int, int, int], _RoundSet] = {}

    def _graph(self, lights: np.ndarray) -> Tuple[Tuple[int, int], Optional[_Graph]]:
        sample = lights[
            ::13,
            [
                LightColumns.CONTROLLER,
                LightColumns.CHANNEL,
                LightColumns.INDEX,
                LightColumns.X,
                LightColumns.Y,
            ],
        ]
        key = (
            lights.shape[0],
            zlib.crc32(np.ascontiguousarray(np.nan_to_num(sample)).tobytes()),
        )
        if key not in self._graph_cache:
            self._graph_cache[key] = _build_graph(lights)
        return key, self._graph_cache[key]

    def _round(self, key: Tuple[int, int], g: _Graph, idx: int) -> _RoundSet:
        ck = (key[0], key[1], idx)
        if ck not in self._round_cache:
            if len(self._round_cache) > 3:
                self._round_cache.pop(next(iter(self._round_cache)))
            self._round_cache[ck] = _sim_all(g, idx)
        return self._round_cache[ck]

    def render(self, lights: np.ndarray, t: float) -> np.ndarray:
        n = lights.shape[0]
        out = np.zeros((n, 3))

        bg_h = (255.0 + 12.0 * np.sin(2.0 * np.pi * t / _BG_H_PERIOD)) % 360.0
        out[:, 0] = _BG_L
        out[:, 1] = _BG_C
        out[:, 2] = bg_h

        # Faint hashed glitter -- dimmer and sparser than a full night sky,
        # since the serpent is the show. Each star's own peak brightness is
        # hashed too (a piecewise-linear quantile function of a per-light
        # uniform: most stars stay modest, a brighter fifth reach further),
        # instead of every star topping out at the same L -- matching
        # constellations' twinkle-tier variety rather than one flat plateau.
        pick = seeded_random("serpent-glitter-pick", n)
        phase = seeded_random("serpent-glitter-phase", n)
        amp_u = seeded_random("serpent-glitter-amp", n)
        is_star = pick < _GLITTER_FRAC
        period = 3.4 + 3.1 * phase
        tw = 0.5 + 0.5 * np.sin(2.0 * np.pi * (t / period + phase * 6.2831853))
        common = amp_u < _GLITTER_BRIGHT_SPLIT
        peak_l = np.where(
            common,
            _GLITTER_PEAK_LO
            + (amp_u / _GLITTER_BRIGHT_SPLIT) * (_GLITTER_PEAK_MID - _GLITTER_PEAK_LO),
            _GLITTER_PEAK_MID
            + ((amp_u - _GLITTER_BRIGHT_SPLIT) / (1.0 - _GLITTER_BRIGHT_SPLIT))
            * (_GLITTER_PEAK_HI - _GLITTER_PEAK_MID),
        )
        glitter_amp = np.clip(peak_l - _BG_L, 0.0, None)
        glitter = np.where(is_star, glitter_amp * tw * tw, 0.0)
        # Faint background tier: steady hashed glow + a whisper of the same
        # slow twinkle. The density, not the brightness, is what makes the
        # sky read populated.
        is_faint = (~is_star) & (pick < _GLITTER_FRAC + _GLITTER_BG_FRAC)
        faint_l = _GLITTER_BG_LO + amp_u * (_GLITTER_BG_HI - _GLITTER_BG_LO)
        faint = np.where(
            is_faint,
            np.clip(faint_l - _BG_L, 0.0, None) + _GLITTER_BG_TW * tw * tw,
            0.0,
        )
        out[:, 0] = np.clip(out[:, 0] + glitter + faint, 0.0, 1.0)

        key, g = self._graph(lights)
        if g is None:
            return nan_to_black(out)

        idx = int(t // g.round_len)
        tau = t - idx * g.round_len
        rs = self._round(key, g, idx)

        veil = min(1.0, tau / 1.2, max(0.0, (g.round_len - tau) / _FADE_OUT))

        rows_list: List[np.ndarray] = []
        lum_list: List[np.ndarray] = []
        a_list: List[np.ndarray] = []
        b_list: List[np.ndarray] = []

        def add(
            rows: np.ndarray, lum: np.ndarray, a: np.ndarray, b: np.ndarray
        ) -> None:
            rows_list.append(rows)
            lum_list.append(lum * veil)
            a_list.append(a * veil)
            b_list.append(b * veil)

        speed = _SPEED_MULT * g.unit
        head_sigma = _HEAD_SIGMA_MULT * g.unit
        num = len(rs.snakes)

        # Each snake renders exactly like the single-agent body/gulp did, but
        # with its own palette: a base-coat chroma tier (_PALETTES) and a
        # per-round hue-family offset so the snakes read as distinct color
        # identities rather than three copies of one rainbow.
        for si, rd in enumerate(rs.snakes):
            snake_base_c, snake_band_c = _PALETTES[si % len(_PALETTES)]
            hue_off = (si * 360.0 / num + 40.0 * _frac(idx, si, 91)) % 360.0

            s_head = min(speed * tau, rd.path_smax)
            l_now = _l_at(rd, tau)
            lo, hi = max(0.0, s_head - l_now), s_head
            # Extend the rendered window past the head by 3 sigma of its own
            # gaussian and render that stretch as forward-spilling headlight,
            # not body -- otherwise the window's leading edge is a hard cut and
            # the newest boundary light steps background -> full brightness in
            # one frame. Clamped to what the round actually simulated: past
            # path_smax there's no path data to spill onto, so the extension
            # (and with it the forward glow) gracefully shrinks to nothing --
            # right where the round's own crossfade is already fading to black.
            hi_ext = min(hi + 3.0 * head_sigma, rd.path_smax)

            if hi_ext > lo and len(rd.path_s):
                i0, i1 = np.searchsorted(rd.path_s, [lo, hi_ext])
                if i1 > i0:
                    rows_b = rd.path_rows[i0:i1]
                    s_b = rd.path_s[i0:i1]
                    ahead = s_b > hi

                    lspan = max(hi - lo, 1e-6)
                    tail_w = _smoothstep((s_b - lo) / lspan, 0.0, _TAIL_FADE_FRAC)

                    base_hue = (
                        _HUE_RATE * s_b / g.unit + _HUE_DRIFT * t + hue_off
                    ) % 360.0
                    # A traveling saturation wave along the base coat only
                    # -- bands keep their own fixed chroma, the signal stays clean.
                    wave_lambda = _CHROMA_WAVE_LAMBDA_MULT * g.unit
                    chroma_wave = 1.0 + _CHROMA_WAVE_AMP * np.sin(
                        2.0 * np.pi * (s_b / wave_lambda - t / _CHROMA_WAVE_PERIOD)
                    )
                    base_c = snake_base_c * chroma_wave
                    base_a = base_c * np.cos(np.radians(base_hue))
                    base_b = base_c * np.sin(np.radians(base_hue))

                    edge = _EDGE_BLEND_MULT * g.unit
                    band_w_full = _BAND_WIDTH_MULT * g.unit
                    if len(rd.ev_a):
                        bidx = np.searchsorted(rd.ev_a, s_b, side="right") - 1
                        valid = bidx >= 0
                        bidx_c = np.clip(bidx, 0, len(rd.ev_a) - 1)
                        rel = s_b - rd.ev_a[bidx_c]
                        w_in = _smoothstep(rel, -edge, edge)
                        w_out = 1.0 - _smoothstep(
                            rel, band_w_full - edge, band_w_full + edge
                        )
                        band_w = np.where(valid, np.clip(w_in * w_out, 0.0, 1.0), 0.0)
                        band_hue = rd.ev_hue[bidx_c]
                        band_a = snake_band_c * np.cos(np.radians(band_hue))
                        band_b = snake_band_c * np.sin(np.radians(band_hue))
                        row_a = base_a * (1.0 - band_w) + band_a * band_w
                        row_b = base_b * (1.0 - band_w) + band_b * band_w
                        bulge = 1.0 + _BAND_BULGE * band_w

                        # bulge exactly at the head, so the forward glow's peak
                        # matches the backward formula's boundary value even
                        # mid-reveal (tail_w(hi) is exactly 1.0 by construction,
                        # so bulge is the only thing that can break continuity).
                        bidx_hi = int(np.searchsorted(rd.ev_a, hi, side="right")) - 1
                        if bidx_hi >= 0:
                            rel_hi = hi - float(rd.ev_a[bidx_hi])
                            w_in_hi = float(
                                _smoothstep(np.array([rel_hi]), -edge, edge)[0]
                            )
                            w_out_hi = 1.0 - float(
                                _smoothstep(
                                    np.array([rel_hi]),
                                    band_w_full - edge,
                                    band_w_full + edge,
                                )[0]
                            )
                            bulge_hi = 1.0 + _BAND_BULGE * float(
                                np.clip(w_in_hi * w_out_hi, 0.0, 1.0)
                            )
                        else:
                            bulge_hi = 1.0
                    else:
                        row_a, row_b, bulge, bulge_hi = base_a, base_b, 1.0, 1.0

                    # Symmetric about the head -- squared, so the same expression
                    # serves both the backward falloff and the forward spill.
                    head_gauss = np.exp(-0.5 * ((s_b - hi) / head_sigma) ** 2)
                    lum_back = (
                        _BODY_ENERGY * tail_w * bulge * (1.0 + _HEAD_BOOST * head_gauss)
                    )
                    # No tail fade, no band ahead of the head -- it's the head's
                    # own glow spilling forward, not body it has laid down yet.
                    # Scaled by bulge_hi (not a bare 1.0) so the two formulas are
                    # exactly equal at s_b == hi, where head_gauss == 1 for both.
                    lum_fwd = _BODY_ENERGY * bulge_hi * (1.0 + _HEAD_BOOST) * head_gauss
                    lum = np.where(ahead, lum_fwd, lum_back)
                    eff_a = np.where(ahead, base_a, row_a)
                    eff_b = np.where(ahead, base_b, row_b)
                    add(rows_b, lum, lum * eff_a, lum * eff_b)

            # A collapse's bright beat, timed to the retraction it precedes:
            # every retraction breakpoint (bp_to < bp_from) -- a self-swallow OR
            # a tron crash -- is a gulp. Position is recovered from its time
            # alone: S(tau) = speed * tau always, so no separate bookkeeping is
            # needed to know where it happened.
            if len(rd.path_s):
                gulp_idx = np.flatnonzero(rd.bp_to < rd.bp_from)
                for gi in gulp_idx:
                    t_g = float(rd.bp_t[gi])
                    k = tau - t_g
                    if 0.0 <= k < _GULP_DUR:
                        s_g = speed * t_g
                        sigma = _GULP_SIGMA_MULT * g.unit
                        j0, j1 = np.searchsorted(
                            rd.path_s, [s_g - 3.0 * sigma, s_g + 3.0 * sigma]
                        )
                        if j1 > j0:
                            rows_g = rd.path_rows[j0:j1]
                            d_g = rd.path_s[j0:j1] - s_g
                            wgt = np.exp(-0.5 * (d_g / sigma) ** 2)
                            attack = min(1.0, k / 0.10)
                            decay = float(np.exp(-k / 0.18))
                            close = min(1.0, (_GULP_DUR - k) / 0.15)
                            blow = attack * decay * close
                            lum_g = _GULP_L * blow * wgt
                            gh, gc = _GULP_HC
                            ca, cb = gc * np.cos(np.radians(gh)), gc * np.sin(
                                np.radians(gh)
                            )
                            add(rows_g, lum_g, lum_g * ca, lum_g * cb)

        # Blips are SHARED across all snakes -- rendered once from the round's
        # single blip record list.
        if len(rs.blip_v):
            alive = (rs.blip_t0 <= tau) & (tau < rs.blip_t1)
            dying = (tau >= rs.blip_t1) & (tau < rs.blip_t1 + _BLIP_DEATH_DUR)
            for i in np.flatnonzero(alive | dying):
                v = int(rs.blip_v[i])
                hue = float(rs.blip_hue[i])
                t0_i = float(rs.blip_t0[i])
                t1_i = float(rs.blip_t1[i])
                # Attack/breathe/size freeze at the eat instant -- the death
                # envelope (flare then fade) plays from that frozen frame
                # rather than a live blip continuing to breathe after being
                # eaten. Never-eaten blips (t1 = round_len + 1e6) never see
                # tau >= t1_i inside a round, so this is a no-op for them.
                eval_tau = tau if tau < t1_i else t1_i
                attack = min(1.0, (eval_tau - t0_i) / _BLIP_ATTACK)
                breathe = 0.75 + 0.25 * np.sin(
                    2.0 * np.pi * eval_tau / _BLIP_BREATH_PERIOD + hue
                )
                death = 1.0 if tau < t1_i else _blip_death_scale(tau - t1_i)
                sigma = _BLIP_SIGMA_MULT * g.unit * (0.85 + 0.15 * breathe)
                shortest_arm = min(float(g.clen[c]) for _w, c in g.adj[v])
                max_reach = _BLIP_REACH_K * shortest_arm
                rr, ww = _vertex_blob(g, v, sigma, max_reach=max_reach)
                if rr:
                    rows_bl = np.concatenate(rr)
                    w_bl = np.concatenate(ww)
                    lum_bl = _BLIP_L * breathe * attack * death * w_bl
                    ca, cb = (
                        _BLIP_C * np.cos(np.radians(hue)),
                        _BLIP_C * np.sin(np.radians(hue)),
                    )
                    add(rows_bl, lum_bl, lum_bl * ca, lum_bl * cb)

        if rows_list:
            rows_all = np.concatenate(rows_list)
            lum_acc = np.bincount(
                rows_all, weights=np.concatenate(lum_list), minlength=n
            )
            a_acc = np.bincount(rows_all, weights=np.concatenate(a_list), minlength=n)
            b_acc = np.bincount(rows_all, weights=np.concatenate(b_list), minlength=n)
            out[:, 0] = np.clip(
                out[:, 0] + 0.92 * (1.0 - np.exp(-1.9 * lum_acc)), 0.0, 1.0
            )
            chroma_mag = np.hypot(a_acc, b_acc) / np.maximum(lum_acc, 1e-6)
            add_c = np.clip(chroma_mag, 0.0, 0.37) * (
                1.0 - np.exp(-_CHROMA_GATE * lum_acc)
            )
            out[:, 1] = np.clip(out[:, 1] + add_c, 0.0, 0.4)
            hue_field = np.degrees(np.arctan2(b_acc, a_acc)) % 360.0
            out[:, 2] = np.where(lum_acc > 1e-6, hue_field, out[:, 2])

        return nan_to_black(out)
