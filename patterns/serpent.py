"""A serpent roams the lattice: rainbow body, giant blips to eat, and every
swallowed color chases back through the body as it travels.

The corridor graph is recovered from the lights array exactly as in
`pacman.py` and `border_chase.py` (runs split at turns/gaps, endpoints
clustered into vertices, parallel beams either side of a seam merged into
one corridor) but kept much simpler: one agent needs no thinning and no
portals, just a connected graph with per-corridor row/arc tables sorted by
arclength.

A round is simulated once, corridor-hop by corridor-hop rather than at a
fixed tick rate -- the serpent moves at constant speed between the turns it
actually has to decide (a junction, an eaten blip), so its whole trip is a
sequence of closed-form segments. Concatenating each segment's per-corridor
row/arc table (offset by the trip's running arclength) and sorting once by
that arclength gives a single `(row, s)` table for the entire round -- the
same idiom `border_chase.py` uses for its closed cycle, just for a
round-length, blip-aware, self-avoiding walk instead of a fixed loop.

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
_ROUND_K = 1.6  # round length ~= K * total corridor length / speed
_ROUND_MIN = 30.0
_ROUND_MAX = 300.0
_FADE_OUT = 2.5  # round-boundary crossfade, seconds
_PULL_WEIGHT = 0.6  # mild pull toward a live blip; noise can still overturn it
_TRAP_PENALTY = 4.0  # one-hop lookahead: discourage (not forbid) walking into a
# vertex whose only other exits are already body -- a dead end the body itself
# just built

# --- body ---------------------------------------------------------------
_BABY_L_MULT = 1.4  # starting body length, x unit
_GROW_UNIT_MULT = 1.0  # body growth per eat, x unit
_GROW_RAMP = 2.0  # seconds to ramp a growth in -- never a jump
_RETRACT_TIME = 0.65  # seconds to retract after a self-swallow (>= 0.5)
_TAIL_FADE_FRAC = 0.30  # fraction of body length that fades in at the tail
_BODY_C = 0.15
_HUE_RATE = 46.0  # degrees per corridor unit of arclength (s/g.unit): the base
# rainbow cycle -- normalized by the corridor unit, not raw world arclength,
# so the hue step per light stays geometry-independent (a world-unit step
# scales with the strip's light spacing, which varies wildly by geometry).
_HUE_DRIFT = 25.0  # degrees/second: stripes flow tailward (against travel) at
# drift * unit / _HUE_RATE world-units/s -- ~12 world-units/s on the star
# with these constants, a visibly-moving counter-flow. Per-light per-frame
# hue slew from this term alone is drift/30fps =~ 0.83 deg/frame, far under
# the wire's 89 deg/frame cap.
_BODY_ENERGY = 1.05

# --- traveling saturation wave on the base coat (bands are unaffected) ---
_CHROMA_WAVE_AMP = 0.25  # relative to _BODY_C
_CHROMA_WAVE_LAMBDA_MULT = 4.0  # x unit
_CHROMA_WAVE_PERIOD = 6.7  # seconds; incommensurate with the blip breath (1.1s)

# --- the signature mechanic: swallowed-color bands -----------------------
_BAND_WIDTH_MULT = 3.0  # x unit; at _SPEED_MULT=2.0 that's ~1.5s to reveal
_EDGE_BLEND_MULT = 0.5  # x unit, OKLab edge blend (~0.5 facet, per craft)
_BAND_C = 0.24
_BAND_BULGE = 0.35  # brightness bulge riding the band -- the meal digesting

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
_GLITTER_FRAC = 0.010  # sparser than a full night sky -- the serpent is the show
_GLITTER_AMP = 0.05


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
        runs.extend(m for m in merged if len(m) >= _MIN_RUN)
    med_all = float(np.median(np.concatenate(spacings))) if spacings else 1.0
    return runs, med_all


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
    start: int  # a far-out vertex the round begins from
    round_len: float
    max_blips: int


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
    labels = _cluster_endpoints(a, runs, max(3.0 * spacing, 0.3 * unit))

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
    start = int(np.argmax(dist.sum(axis=1)))
    total_len = float(clen2.sum())
    speed = _SPEED_MULT * unit
    round_len = float(
        np.clip(_ROUND_K * total_len / max(speed, 1e-6), _ROUND_MIN, _ROUND_MAX)
    )
    max_blips = int(np.clip(nc2 // _MAX_BLIPS_PER_CORRIDORS, 1, _MAX_BLIPS_CAP))

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
        round_len,
        max_blips,
    )


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


class _Round(NamedTuple):
    path_rows: np.ndarray  # (m,) light row per path point, ascending by path_s
    path_s: np.ndarray  # (m,) arclength since round start
    path_smax: float
    ev_a: np.ndarray  # (e,) eat arclength, ascending
    ev_hue: np.ndarray  # (e,)
    bp_t: np.ndarray  # (b,) L-schedule breakpoints, ascending, bp_t[0] == 0
    bp_from: np.ndarray
    bp_to: np.ndarray
    bp_dur: np.ndarray
    blip_v: np.ndarray  # (k,) vertex
    blip_hue: np.ndarray
    blip_t0: np.ndarray  # spawned
    blip_t1: np.ndarray  # eaten (or well past round end if never eaten)


def _sim(g: _Graph, idx: int) -> _Round:
    speed = _SPEED_MULT * g.unit
    baby_l = _BABY_L_MULT * g.unit
    grow_unit = _GROW_UNIT_MULT * g.unit
    round_len = g.round_len

    v_cur, prev_v = g.start, -1
    t_cur, s_cur = 0.0, 0.0
    l_state = baby_l

    trip_c: List[int] = []
    trip_rev: List[bool] = []
    trip_entry_s: List[float] = []

    ev_a: List[float] = []
    ev_hue: List[float] = []

    bp_t: List[float] = [0.0]
    bp_from: List[float] = [baby_l]
    bp_to: List[float] = [baby_l]
    bp_dur: List[float] = [0.0]

    def l_now_in_sim(t: float) -> float:
        """The TRUE eased L at simulation time t, from the breakpoints
        recorded so far -- same easing _l_at uses at render time. Growth
        ramps (2s) commonly overlap in real time when several blips are
        eaten close together, so a new breakpoint's ``from`` must be this,
        not ``l_state`` (which is the *target* of the last event, not
        necessarily reached yet) -- otherwise the still-in-flight previous
        ramp's un-earned target gets treated as already-arrived-at, and the
        next breakpoint opens with a silent jump up to it."""
        i = len(bp_t) - 1
        dur = bp_dur[i]
        frac = 0.0 if dur <= 0.0 else max(0.0, min(1.0, (t - bp_t[i]) / dur))
        ease = frac * frac * (3.0 - 2.0 * frac)
        return bp_from[i] + (bp_to[i] - bp_from[i]) * ease

    blips: Dict[int, Dict[str, float]] = {}
    blip_records: List[Tuple[int, float, float, float]] = []
    blip_counter = 0
    pending_spawns: List[float] = []

    def spawn_blip(now: float) -> None:
        # Uniform over every eligible vertex -- not the farthest one. Only
        # excluded: vertices already holding a live blip, and vertices
        # within _SPAWN_MIN_HOPS of the head (so it never spawns on top of
        # it). Ties/picks are still deterministic via _fnv.
        nonlocal blip_counter
        live_v = {int(b["v"]) for b in blips.values()}
        d = g.dist[v_cur]
        cands = [
            v for v in range(g.nv) if v not in live_v and int(d[v]) > _SPAWN_MIN_HOPS
        ]
        if not cands:
            return
        pick = cands[_fnv(idx, blip_counter, 7) % len(cands)]
        hue = 360.0 * _frac(idx, blip_counter, 11)
        blips[blip_counter] = {"v": float(pick), "hue": hue, "t0": now}
        blip_counter += 1

    for _ in range(g.max_blips):
        spawn_blip(0.0)

    def occupied(c: int) -> bool:
        i = len(trip_c) - 1
        floor = s_cur - l_state
        while i >= 0 and trip_entry_s[i] >= floor:
            if trip_c[i] == c:
                return True
            i -= 1
        return False

    def is_trap(w: int, c: int) -> bool:
        """One-hop lookahead: true if every corridor out of w other than the
        one just entered (c) is currently body-occupied -- a pocket the body
        itself just sealed. No deeper search than this."""
        others = [c2 for _w2, c2 in g.adj[w] if c2 != c]
        return bool(others) and all(occupied(c2) for c2 in others)

    step = 0
    max_steps = 20000
    while t_cur < round_len and step < max_steps:
        step += 1
        if pending_spawns:
            still = []
            for pt in pending_spawns:
                if pt <= t_cur and len(blips) < g.max_blips:
                    spawn_blip(pt)
                else:
                    still.append(pt)
            pending_spawns = still

        opts_all = g.adj[v_cur]
        opts_nb = [(w, c) for w, c in opts_all if w != prev_v] or opts_all
        opts_pref = [(w, c) for w, c in opts_nb if not occupied(c)] or opts_nb
        options = opts_pref
        if not options:
            break

        blip_vs = [int(b["v"]) for b in blips.values()]
        best_score, w_next, c_next = None, options[0][0], options[0][1]
        for w, c in options:
            dmin = min((int(g.dist[w, bv]) for bv in blip_vs), default=0)
            score = dmin * _PULL_WEIGHT + _frac(idx, step, c)
            if is_trap(w, c):
                score += _TRAP_PENALTY
            if best_score is None or score < best_score:
                best_score, w_next, c_next = score, w, c

        was_occupied = occupied(c_next)
        rev = v_cur != int(g.cu[c_next])
        clen_c = float(g.clen[c_next])

        trip_c.append(c_next)
        trip_rev.append(rev)
        trip_entry_s.append(s_cur)

        entry_t = t_cur
        exit_t = t_cur + clen_c / speed
        exit_s = s_cur + clen_c

        if was_occupied:
            true_l = l_now_in_sim(entry_t)
            bp_t.append(entry_t)
            bp_from.append(true_l)
            bp_to.append(baby_l)
            bp_dur.append(_RETRACT_TIME)
            l_state = baby_l

        t_cur, s_cur = exit_t, exit_s
        prev_v, v_cur = v_cur, w_next

        eaten_ids = sorted(bid for bid, b in blips.items() if int(b["v"]) == v_cur)
        for bid in eaten_ids:
            b = blips.pop(bid)
            blip_records.append((int(b["v"]), b["hue"], b["t0"], t_cur))
            ev_a.append(s_cur)
            ev_hue.append(b["hue"])
            true_l = l_now_in_sim(t_cur)
            bp_t.append(t_cur)
            bp_from.append(true_l)
            bp_to.append(true_l + grow_unit)
            bp_dur.append(_GROW_RAMP)
            # l_state is a separate, deliberately coarser bookkeeping value:
            # occupied()'s self-collision window only needs a reasonable
            # body-length estimate, not the precise eased curve, so it keeps
            # its own running target rather than tracking true_l.
            l_state += grow_unit
            delay = _SPAWN_DELAY[0] + (_SPAWN_DELAY[1] - _SPAWN_DELAY[0]) * _frac(
                idx, bid, 13
            )
            pending_spawns.append(t_cur + delay)

    for bid, b in blips.items():
        blip_records.append((int(b["v"]), b["hue"], b["t0"], round_len + 1.0e6))

    rows_out, s_out = [], []
    for k in range(len(trip_c)):
        c, rv, s0 = trip_c[k], trip_rev[k], trip_entry_s[k]
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

    def arr(vals: List[float]) -> np.ndarray:
        return np.array(vals, np.float64) if vals else np.empty(0, np.float64)

    blip_v = arr([float(r[0]) for r in blip_records]).astype(np.int64)
    blip_hue = arr([r[1] for r in blip_records])
    blip_t0 = arr([r[2] for r in blip_records])
    blip_t1 = arr([r[3] for r in blip_records])

    return _Round(
        path_rows,
        path_s,
        float(s_cur),
        arr(ev_a),
        arr(ev_hue),
        arr(bp_t),
        arr(bp_from),
        arr(bp_to),
        arr(bp_dur),
        blip_v,
        blip_hue,
        blip_t0,
        blip_t1,
    )


def _l_at(rd: _Round, tau: float) -> float:
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
        self._round_cache: Dict[Tuple[int, int, int], _Round] = {}

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

    def _round(self, key: Tuple[int, int], g: _Graph, idx: int) -> _Round:
        ck = (key[0], key[1], idx)
        if ck not in self._round_cache:
            if len(self._round_cache) > 3:
                self._round_cache.pop(next(iter(self._round_cache)))
            self._round_cache[ck] = _sim(g, idx)
        return self._round_cache[ck]

    def render(self, lights: np.ndarray, t: float) -> np.ndarray:
        n = lights.shape[0]
        out = np.zeros((n, 3))

        bg_h = (255.0 + 12.0 * np.sin(2.0 * np.pi * t / _BG_H_PERIOD)) % 360.0
        out[:, 0] = _BG_L
        out[:, 1] = _BG_C
        out[:, 2] = bg_h

        # Faint hashed glitter -- dimmer and sparser than a full night sky,
        # since the serpent is the show.
        pick = seeded_random("serpent-glitter-pick", n)
        phase = seeded_random("serpent-glitter-phase", n)
        is_star = pick < _GLITTER_FRAC
        period = 3.4 + 3.1 * phase
        tw = 0.5 + 0.5 * np.sin(2.0 * np.pi * (t / period + phase * 6.2831853))
        glitter = np.where(is_star, _GLITTER_AMP * tw * tw, 0.0)
        out[:, 0] = np.clip(out[:, 0] + glitter, 0.0, 1.0)

        key, g = self._graph(lights)
        if g is None:
            return nan_to_black(out)

        idx = int(t // g.round_len)
        tau = t - idx * g.round_len
        rd = self._round(key, g, idx)

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

                base_hue = (_HUE_RATE * s_b / g.unit + _HUE_DRIFT * t) % 360.0
                # A gentle traveling saturation wave along the base coat only
                # -- bands keep their own fixed _BAND_C, the signal stays clean.
                wave_lambda = _CHROMA_WAVE_LAMBDA_MULT * g.unit
                chroma_wave = 1.0 + _CHROMA_WAVE_AMP * np.sin(
                    2.0 * np.pi * (s_b / wave_lambda - t / _CHROMA_WAVE_PERIOD)
                )
                base_c = _BODY_C * chroma_wave
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
                    band_a = _BAND_C * np.cos(np.radians(band_hue))
                    band_b = _BAND_C * np.sin(np.radians(band_hue))
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
                        w_in_hi = float(_smoothstep(np.array([rel_hi]), -edge, edge)[0])
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

        # A self-swallow's bright beat, timed to the retraction it precedes:
        # every retraction breakpoint (bp_to < bp_from) is a gulp. Position
        # is recovered from its time alone -- S(tau) = speed * tau always,
        # so no separate bookkeeping is needed to know where it happened.
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

        if len(rd.blip_v):
            alive = (rd.blip_t0 <= tau) & (tau < rd.blip_t1)
            dying = (tau >= rd.blip_t1) & (tau < rd.blip_t1 + _BLIP_DEATH_DUR)
            for i in np.flatnonzero(alive | dying):
                v = int(rd.blip_v[i])
                hue = float(rd.blip_hue[i])
                t0_i = float(rd.blip_t0[i])
                t1_i = float(rd.blip_t1[i])
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
            add_c = np.clip(chroma_mag, 0.0, 0.37) * (1.0 - np.exp(-2.6 * lum_acc))
            out[:, 1] = np.clip(out[:, 1] + add_c, 0.0, 0.4)
            hue_field = np.degrees(np.arctan2(b_acc, a_acc)) % 360.0
            out[:, 2] = np.where(lum_acc > 1e-6, hue_field, out[:, 2])

        return nan_to_black(out)
