"""Pac-Man played on the sculpture's own borders.

The maze is recovered from the lights array: each (controller, channel)
strip is split into straight runs at sharp turns and long jumps, run
endpoints are clustered into vertices, and runs sharing a vertex pair
become one *corridor*. On the star that yields 140 vertices and 266
corridors: a real maze, drawn by the build itself.

The beams either side of a panel seam run parallel a couple of world
units apart, and merging them is what the eye does at sculpture distance
anyway. So a corridor is a lane, not a line: a dot lights both of its
beams at once, and a ghost sharing it is simply on it — no
across-the-gap special case to keep in sync with the catch rule.

Dots are spaced by arclength rather than counted per corridor. The short
beams run about half the length of the long ones, and a fixed count per
corridor crowded them to nearly double the density.

A whole round is simulated once and memoized, then played back. The
simulation is a pure function of (maze, round index): Pac hunting dots,
four ghosts running the arcade's targeting rules translated to a graph
(Blinky on Pac, Pinky two corridors ahead, Inky flanking away from
Blinky, Clyde chasing only beyond six hops), scatter/chase alternation
with the classic reversal, energizers, frightened ghosts, eyes returning
to the house, fruit, deaths. ~190 ms for a six-minute round on the
star, paid at the first frame that needs each round — so a round
boundary stalls one beat; the maze itself (runs, clustering, all-pairs
distances) is ~120 ms, once per geometry. Playback frames are direct
indexing into the recorded tables plus bincounts over the accumulated
contributions: ~0.6 ms steady state at 6,660 lights.

Round length is derived from the maze — a ghost-free dry run of Pac's
covering walk, times a slack factor — so the board clears with room to
spare, then flourishes and immediately starts a faster level 2 rather
than sitting empty. Round index is floor(t / round_len): no chaining,
no state. Same (lights, t) in, same colors out, in any call order
(spec §9.1.3); the caches are memoization keyed by content.
"""

import zlib
from collections import deque
from typing import Dict, List, Optional, Tuple

import numpy as np

from luminary.geometry.lights import LightColumns
from luminary.patterns.base import Pattern

# --- maze extraction -------------------------------------------------
_TURN_DEG = 28.0  # split a strip where it bends more than this
_GAP_FACTOR = 4.0  # ... or jumps more than this multiple of its spacing
_MIN_RUN = 4  # runs shorter than this merge into a neighbor or drop

# --- game ------------------------------------------------------------
_DT = 0.05  # simulation tick (20 Hz); playback interpolates
_PAC_SPEED = 2.0  # corridors per second
_GHOST_SPEED = 0.82  # x Pac
_FRIGHT_SPEED = 0.55
_EYES_SPEED = 2.4
_LEVEL2_GHOST = 1.15  # ghosts speed up on the second level
_FRIGHT_TIME = 6.5
_DOT_SPACING = 0.40  # of the median corridor: dots sit this far apart
_DOT_SIGMA = 0.064  # gaussian half-width; 3 sigma stays under the spacing
_ENER_SIGMA = 0.16  # energizers: the board's big bright dots
_ENERGIZERS = 5
_LIVES = 3
_DEATH_TIME = 1.8  # collapse animation
_RESPAWN_PAUSE = 0.9  # dark beat before the board resumes
_CATCH_FRAC = 0.10  # of a corridor length
_HOUSE_HOLD = 1.0  # eyes wait this long in the house
_RELEASE = (1.6, 4.2, 7.6, 11.0)  # ghost release times after a reset;
# the first gap is the arcade's READY! beat, and it keeps round 0 —
# the one every restart opens on — from losing a life in six seconds.
_SCATTER_CHASE = (7.0, 20.0, 7.0, 20.0, 5.0, 20.0, 5.0)  # then chase forever
_CLEAR_FLOURISH = 3.0
_ROUND_SLACK = 1.7  # dry-run clear time x this, + tail
_ROUND_TAIL = 10.0
_FADE_OUT = 2.5  # the seam between rounds

# --- look ------------------------------------------------------------
_BG_L, _BG_C, _BG_H = 0.045, 0.020, 268.0
# The arcade's blue walls: the corridors stay lit even once their dots
# are gone, so the piece keeps its shape instead of going black.
_MAZE_HC = (266.0, 0.125)
_MAZE_L = 0.105
_JUNC_L = 0.075  # extra at the intersections, pulled violet
_DOT_H, _DOT_C = 78.0, 0.135  # warm amber, to read over the blue
_PAC_H, _PAC_C = 95.0, 0.185  # yellow
_GHOST_HC = ((28.0, 0.19), (350.0, 0.14), (200.0, 0.15), (60.0, 0.17))
_FRIGHT_HC = (272.0, 0.16)
_EYE_HC = (230.0, 0.05)
# cherry, strawberry, orange, apple, grape, galaxian, bell, key
_FRUITS = (
    (25.0, 0.21),
    (5.0, 0.19),
    (52.0, 0.20),
    (146.0, 0.18),
    (312.0, 0.19),
    (248.0, 0.18),
    (88.0, 0.20),
    (196.0, 0.17),
)
_FRUIT_GATES = (0.12, 0.26, 0.40, 0.54, 0.68, 0.82)
_FRUIT_DWELL = 14.0
_FLASH_SPEED = 2.1  # death shockwave, corridors per second
_FLASH_TIME = 1.7


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


def _fnv(*vals: int) -> int:
    """Deterministic integer hash — pure arithmetic, identical in any
    process (unlike Python's salted hash())."""
    h = 2166136261
    for v in vals:
        h = ((h ^ (int(v) & 0xFFFFFFFF)) * 16777619) & 0xFFFFFFFF
    return h


class _Maze:
    """Corridors, the graph over them, and where every light sits."""

    def __init__(
        self,
        cu: np.ndarray,
        cv: np.ndarray,
        clen: np.ndarray,
        adj: List[List[Tuple[int, int]]],
        dist: np.ndarray,
        vxy: np.ndarray,
        rows: np.ndarray,
        arc: np.ndarray,
        ptr: np.ndarray,
        unit: float,
    ):
        self.cu, self.cv = cu, cv  # (nc,) corridor endpoints
        self.clen = clen  # (nc,) corridor length, world units
        self.adj = adj  # adj[v] = [(other vertex, corridor), ...]
        self.dist = dist  # (nv, nv) hop distance
        self.vxy = vxy  # (nv, 2) vertex positions
        self.rows = rows  # (m,) light row per corridor visit
        self.arc = arc  # (m,) distance from cu along its corridor
        self.ptr = ptr  # (nc+1,) slice bounds into rows/arc
        self.unit = unit  # median corridor length
        self.dry = 0.0  # ghost-free time to clear the board
        self.nc = len(cu)
        self.nv = len(vxy)
        # Per-visit corridor identity and the distance to each of its ends,
        # so a field measured from any vertex is two gathers.
        self.vis_c = np.repeat(np.arange(self.nc), np.diff(ptr))
        self.vis_u = cu[self.vis_c]
        self.vis_v = cv[self.vis_c]
        self.vis_du = arc
        self.vis_dv = clen[self.vis_c] - arc
        # Fixtures: chosen once, so every round shares a board layout.
        self.house = int(np.argmin(dist.max(axis=1)))
        self.corners = _spread_vertices(self, 4)
        self.fruit_spots = _spread_vertices(self, 8)
        (
            self.pel_c,
            self.pel_s,
            self.pel_kind,
            self.pel_ptr,
            self.pel_n,
        ) = _lay_pellets(self)
        self.start = int(self.cu[int(np.argmax(dist[self.house][self.cu]))])
        self.round_len = 0.0  # filled in by _dry_run


def _spread_vertices(m: _Maze, k: int) -> List[int]:
    """k mutually distant vertices, farthest-point sampled from the house
    — scatter targets, and where the fruit shows up."""
    picks = [int(np.argmax(m.dist[m.house]))]
    while len(picks) < k and len(picks) < m.nv:
        d = m.dist[picks].min(axis=0)
        picks.append(int(np.argmax(d)))
    while len(picks) < k:
        picks.append(picks[-1])
    return picks


def _lay_pellets(m: _Maze) -> Tuple[np.ndarray, ...]:
    """A row of dots down every corridor, evenly spaced *in world units*
    — a fixed count per corridor would crowd the short beams, which run
    about half the length of the long ones. Energizers replace the middle
    dot on corridors hanging off the far corners."""
    step = _DOT_SPACING * m.unit
    counts = np.maximum(2, np.rint(m.clen / step).astype(np.int64))
    pptr = np.concatenate([[0], np.cumsum(counts)]).astype(np.int64)
    pc = np.repeat(np.arange(m.nc), counts)
    ps = np.concatenate([(np.arange(k) + 0.5) / k for k in counts])
    kind = np.zeros(len(pc), np.int8)
    # Spread the energizers: the corners first, then whatever is farthest
    # from every energizer already placed.
    seeds = list(m.corners)
    while len(seeds) < _ENERGIZERS:
        seeds.append(int(np.argmax(m.dist[seeds].min(axis=0))))
    used = set()
    for v in seeds[:_ENERGIZERS]:
        for _, c in sorted(m.adj[v], key=lambda oc: oc[1]):
            if c not in used:
                used.add(c)
                kind[int(pptr[c]) + int(counts[c]) // 2] = 1
                break
    return pc, ps, kind, pptr, counts


def _build_maze(a: np.ndarray) -> Optional[_Maze]:
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

    # One corridor per *vertex pair*, not per run. The beams either side of
    # a panel seam run parallel a couple of world units apart; treating them
    # as one wide corridor is what the eye does at sculpture distance
    # anyway, and it halves the board — a dot lights both beams, and a ghost
    # sharing the corridor is simply on it, with no across-the-gap special
    # case to keep in sync.
    #
    # Each run is oriented u->v and its arclength normalized onto the
    # group's mean length, so parallel beams of slightly different length
    # stay in lockstep: one `s` in [0, 1] means the same place on all of
    # them.
    by_pair: Dict[Tuple[int, int], List[int]] = {}
    for e, g in enumerate(groups_of):
        if g is not None:
            by_pair.setdefault(g, []).append(e)
    order_keys = sorted(by_pair)
    cu = np.array([p[0] for p in order_keys], np.int32)
    cv = np.array([p[1] for p in order_keys], np.int32)
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
            lens.append(max(1e-6, float(along[-1])))  # before the flip zeroes it
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
    # Sort each corridor's visits by arclength so a blob is a slice.
    for ci in range(len(order_keys)):
        lo, hi = int(ptr[ci]), int(ptr[ci + 1])
        order = np.argsort(arc[lo:hi], kind="stable")
        rows[lo:hi] = rows[lo:hi][order]
        arc[lo:hi] = arc[lo:hi][order]

    nv = int(labels.max()) + 1
    adj: List[List[Tuple[int, int]]] = [[] for _ in range(nv)]
    for ci in range(len(order_keys)):
        adj[int(cu[ci])].append((int(cv[ci]), ci))
        adj[int(cv[ci])].append((int(cu[ci]), ci))
    for lst in adj:
        lst.sort(key=lambda oc: oc[1])

    far = nv + 1
    dist = np.full((nv, nv), far, np.int16)
    for s in range(nv):
        dist[s, s] = 0
        q = deque([s])
        while q:
            u = q.popleft()
            for w, _ in adj[u]:
                if dist[s, w] == far:
                    dist[s, w] = dist[s, u] + 1
                    q.append(w)

    vxy = np.zeros((nv, 2))
    for e, r in enumerate(runs):
        for i, end in ((0, 0), (-1, 1)):
            vxy[labels[2 * e + end]] = (
                a[r[i], LightColumns.X],
                a[r[i], LightColumns.Y],
            )

    m = _Maze(cu, cv, clen, adj, dist, vxy, rows, arc, ptr, unit)
    # Reject a maze the ghost house cannot reach in full. ``dist`` is int16
    # with ``far`` as the unreachable sentinel, so this must compare against
    # ``far`` -- np.isfinite() on an integer array is unconditionally True and
    # let every disconnected maze through. That mattered more than it sounds:
    # ``start`` is argmax of hop distance from the house, so with ``far`` in
    # the table Pac was *preferentially* spawned in a component the ghosts
    # cannot reach and that holds almost none of the board. Some nets really
    # do have detached panels (3A-33 has 10 components, 4A-31 five); on those
    # this pattern now declines to play rather than play wrong.
    if not (m.dist[m.house] < far).all():
        return None
    m.round_len = _dry_run(m)
    return m


# --- simulation ------------------------------------------------------


class _Agent:
    __slots__ = ("c", "f", "p", "mode", "timer", "nchoice")

    def __init__(self, c: int, f: int) -> None:
        self.c, self.f, self.p = c, f, 0.0
        self.mode = 0  # ghosts: 0 hunt 1 frightened 2 eyes 3 housed
        self.timer = 0.0
        self.nchoice = 0

    def far(self, m: _Maze) -> int:
        return int(m.cv[self.c]) if self.f == int(m.cu[self.c]) else int(m.cu[self.c])

    def s(self, m: _Maze) -> float:
        return self.p if self.f == int(m.cu[self.c]) else 1.0 - self.p

    def enter(self, m: _Maze, v: int, c: int, carry: float) -> None:
        self.p = carry * m.clen[self.c] / m.clen[c]
        self.c, self.f = c, v


def _options(m: _Maze, ag: _Agent, allow_back: bool) -> List[Tuple[int, int]]:
    """Where an agent can go from the end of its corridor. Doubling back
    down the *other* beam of the same panel is still doubling back, so
    reversal is judged by the vertex left behind, not the corridor."""
    v = ag.far(m)
    opts = [(w, c) for w, c in m.adj[v] if w != ag.f]
    if not opts:
        opts = [(w, c) for w, c in m.adj[v] if c != ag.c]
    if not opts or allow_back:
        opts = list(m.adj[v])
    return opts


def _toward(m: _Maze, opts: List[Tuple[int, int]], target: int, salt: int) -> int:
    """Index of the option whose far vertex is closest to target; ties
    broken by a hash so symmetric mazes don't march in lockstep."""
    best, bi = None, 0
    for i, (w, c) in enumerate(opts):
        key = (int(m.dist[w, target]), _fnv(salt, c))
        if best is None or key < best:
            best, bi = key, i
    return bi


class _Round:
    """A simulated round, sampled at _DT and ready to interpolate."""

    def __init__(
        self,
        pos_c: np.ndarray,
        pos_s: np.ndarray,
        pos_m: np.ndarray,
        levels: List[Tuple[float, np.ndarray]],
        fruit: List[Tuple[int, float, float, float, int]],
        clears: List[float],
        deaths: List[Tuple[float, int]],
        length: float,
    ):
        self.pos_c = pos_c  # (T, 5) corridor per agent (0 = Pac)
        self.pos_s = pos_s  # (T, 5) position in [0,1] from corridor's cu
        self.pos_m = pos_m  # (T, 5) mode
        self.levels = levels  # per level: (start time, eaten time per pellet)
        self.fruit = fruit  # (junction, t0, t1, t_eaten, kind)
        self.clears = clears  # times the board was cleared
        self.deaths = deaths  # (time, junction the shockwave starts from)
        self.length = length

    def board(self, tau: float) -> np.ndarray:
        """The eaten-times array in force at tau (a cleared board re-dots)."""
        best = self.levels[0][1]
        for t0, e in self.levels:
            if t0 <= tau:
                best = e
        return best


def _sim(m: _Maze, rnd: int, duration: float, ghosts: bool) -> _Round:
    steps = int(duration / _DT) + 2
    npel = len(m.pel_c)
    pos_c = np.zeros((steps, 5), np.int32)
    pos_s = np.zeros((steps, 5), np.float32)
    pos_m = np.zeros((steps, 5), np.int8)
    eaten = np.full(npel, np.inf, np.float32)
    levels: List[Tuple[float, np.ndarray]] = [(0.0, eaten)]
    left = m.pel_n.astype(np.int32).copy()
    fruit: List[Tuple[int, float, float, float, int]] = []
    clears: List[float] = []
    deaths: List[Tuple[float, int]] = []

    speed = _PAC_SPEED * m.unit
    catch = _CATCH_FRAC * m.unit
    eat_r = 0.10 * m.unit

    def spawn() -> Tuple[_Agent, List[_Agent]]:
        pv = m.start
        pc = min(m.adj[pv], key=lambda oc: oc[1])[1]
        pac = _Agent(pc, pv)
        gs = []
        for gi in range(4):
            hc = m.adj[m.house][gi % len(m.adj[m.house])][1]
            g = _Agent(hc, m.house)
            g.mode, g.timer = 3, _RELEASE[gi]
            gs.append(g)
        return pac, gs

    pac, gh = spawn()
    lives = _LIVES
    level = 0
    lvl_t = 0.0  # time since the level (or a death) started
    power_until = -1.0
    pause_until = -1.0
    pause_kind = 0  # 1 = caught, 2 = board cleared
    ghost_mult = 1.0
    prev_phase = 0
    last_turn = -9.0
    lag = 0.0
    fade_at = duration - _FADE_OUT
    n_dots = float(npel)

    for step in range(steps):
        t = step * _DT

        if pause_kind and t >= pause_until:
            pause_kind = 0
            pac, gh = spawn()
            lvl_t = 0.0
            if lives <= 0:
                lives = _LIVES
        dead = pause_kind != 0

        # Scatter/chase phases, with the classic reversal on every flip.
        phase, acc = 0, 0.0
        for dwell in _SCATTER_CHASE:
            if lvl_t < acc + dwell:
                break
            acc += dwell
            phase += 1
        scatter = phase % 2 == 0 and phase < len(_SCATTER_CHASE)
        if ghosts and not dead and step > 0 and phase != prev_phase:
            for g in gh:
                if g.mode in (0, 1):
                    g.p, g.f = 1.0 - g.p, g.far(m)
        prev_phase = phase
        powered = t < power_until

        # --- Pac ------------------------------------------------------
        if not dead:
            # How far behind the schedule that has the board cleared with
            # time to spare. Falling behind makes him quicker and bolder —
            # without the second part he will not go near the ghost house,
            # and its corridors never get eaten at all.
            lag = 0.0
            if ghosts and level == 0:
                # Work left, priced against the ghost-free dry run — and
                # scaled up as the board empties, because the last few
                # corridors are scattered and travel dominates.
                share = np.count_nonzero(left) / m.nc
                work = m.dry * share * (1.0 + 2.0 * (1.0 - share))
                have = max(0.0, 0.92 * fade_at - t)
                lag = float(np.clip(1.0 - have / max(work, 1e-6), 0.0, 1.0))
            behind = 1.0 + 1.2 * lag
            pac.p += speed * behind * _DT / m.clen[pac.c]
            while pac.p >= 1.0:
                v = pac.far(m)
                carry = pac.p - 1.0
                opts = _options(m, pac, allow_back=True)
                pac.nchoice += 1
                tgt = _pac_target(m, pac, gh, left, fruit, t, powered, v)
                if ghosts and not powered:
                    safe = [
                        min(
                            (int(m.dist[w, g.far(m)]) for g in gh if g.mode == 0),
                            default=99,
                        )
                        for w, _ in opts
                    ]
                    # Never walk into a ghost's lap; if every way out is
                    # bad, take the least bad one — and accept worse odds
                    # the further behind he is.
                    want_bar = 2 if lag < 0.15 else 1
                    bar = min(want_bar, max(safe))
                    opts = [o for o, s in zip(opts, safe) if s >= bar]
                i = _toward(m, opts, tgt, _fnv(rnd, 1, pac.nchoice))
                # Prefer an uneaten corridor among equally good choices.
                best = int(m.dist[opts[i][0], tgt])
                cand = [o for o in opts if int(m.dist[o[0], tgt]) == best]
                withdots = [o for o in cand if left[o[1]] > 0]
                w, c = (withdots or cand)[
                    _fnv(rnd, 2, pac.nchoice) % len(withdots or cand)
                ]
                pac.enter(m, v, c, carry)

            # Eat whatever he passes over.
            a0 = pac.s(m) * m.clen[pac.c]
            lo, hi = int(m.pel_ptr[pac.c]), int(m.pel_ptr[pac.c + 1])
            for k in range(lo, hi):
                if eaten[k] == np.inf:
                    if abs(m.pel_s[k] * m.clen[pac.c] - a0) < eat_r:
                        eaten[k] = t
                        left[pac.c] -= 1
                        if m.pel_kind[k] == 1 and ghosts:
                            power_until = t + _FRIGHT_TIME
                            for g in gh:
                                if g.mode == 0:
                                    g.mode = 1
                                    g.p, g.f = 1.0 - g.p, g.far(m)
            for fi, (fv, f0, f1, fe, fk) in enumerate(fruit):
                if not (f0 <= t < f1 and fe == np.inf):
                    continue
                # How close Pac is to the junction the fruit sits on.
                reach = min(
                    a0 if int(m.cu[pac.c]) == fv else np.inf,
                    m.clen[pac.c] - a0 if int(m.cv[pac.c]) == fv else np.inf,
                )
                if reach < eat_r * 2.5:
                    fruit[fi] = (fv, f0, f1, t, fk)

            # An energizer eaten this tick must take effect before the
            # ghosts move, or frightened mode is cancelled the instant it
            # begins.
            powered = t < power_until
            if ghosts and not powered:
                for g in gh:
                    # Judge the threat on the same terms as the catch.
                    if g.mode != 0 or g.c != pac.c:
                        continue
                    if t - last_turn < 0.7:
                        continue
                    gap = (g.s(m) - pac.s(m)) * m.clen[pac.c]
                    if pac.f != int(m.cu[pac.c]):
                        gap = -gap
                    if 0.0 < gap < 0.5 * m.clen[pac.c]:  # cut off ahead: turn
                        pac.p, pac.f = 1.0 - pac.p, pac.far(m)
                        last_turn = t
                        break

        # --- ghosts ---------------------------------------------------
        if ghosts and not dead:
            for gi, g in enumerate(gh):
                if g.mode == 3:
                    g.timer -= _DT
                    if g.timer <= 0.0:
                        g.mode, g.p, g.f = 0, 0.0, m.house
                    continue
                if g.mode == 1 and not powered:
                    g.mode = 0
                # Ghosts tire as Pac falls behind. Invisible from the
                # ground, and it is what makes the board actually clear.
                sp = (
                    _EYES_SPEED
                    if g.mode == 2
                    else (
                        _FRIGHT_SPEED
                        if g.mode == 1
                        else _GHOST_SPEED * ghost_mult * (1.0 - 0.35 * lag)
                    )
                )
                g.p += sp * speed * _DT / m.clen[g.c]
                while g.p >= 1.0:
                    v = g.far(m)
                    carry = g.p - 1.0
                    if g.mode == 2 and v == m.house:
                        g.mode, g.timer, g.p = 3, _HOUSE_HOLD, 0.0
                        break
                    g.nchoice += 1
                    opts = _options(m, g, allow_back=g.mode == 2)
                    if g.mode == 1:
                        i = _fnv(rnd, 3, gi, g.nchoice) % len(opts)
                    else:
                        tgt = _ghost_target(m, gi, g, gh, pac, scatter)
                        i = _toward(m, opts, tgt, _fnv(rnd, 4, gi, g.nchoice))
                    g.enter(m, v, opts[i][1], carry)

                if g.mode in (0, 1) and g.c == pac.c:
                    d = abs(g.s(m) - pac.s(m)) * m.clen[g.c]
                    if d < catch:
                        if g.mode == 1:
                            g.mode = 2
                        else:
                            pause_until = t + _DEATH_TIME + _RESPAWN_PAUSE
                            pause_kind = 1
                            ps = pac.s(m) * m.clen[pac.c]
                            deaths.append(
                                (
                                    t,
                                    (
                                        int(m.cu[pac.c])
                                        if ps < 0.5 * m.clen[pac.c]
                                        else int(m.cv[pac.c])
                                    ),
                                )
                            )
                            lives -= 1
                            power_until = -1.0
                            break

        # Fruit: four a level, sitting on a junction, each a different one.
        if ghosts and not dead:
            frac = 1.0 - left.sum() / max(1.0, n_dots)
            for idx, gate in enumerate(_FRUIT_GATES):
                key = level * len(_FRUIT_GATES) + idx
                if frac >= gate and len(fruit) == key:
                    v = m.fruit_spots[_fnv(rnd, 5, key) % len(m.fruit_spots)]
                    kind = (key + rnd) % len(_FRUITS)
                    fruit.append((v, t, t + _FRUIT_DWELL, np.inf, kind))

        # Board cleared: flourish, then re-dot and speed the ghosts up, so
        # a finished board never leaves the sculpture sitting empty.
        if left.sum() == 0 and not dead:
            clears.append(t)
            if not ghosts:
                return _Round(
                    pos_c[: step + 1],
                    pos_s[: step + 1],
                    pos_m[: step + 1],
                    levels,
                    fruit,
                    clears,
                    deaths,
                    t,
                )
            pause_until = t + _CLEAR_FLOURISH
            pause_kind = 2
            eaten = np.full(npel, np.inf, np.float32)
            levels.append((t + _CLEAR_FLOURISH, eaten))
            left[:] = m.pel_n
            level += 1
            ghost_mult = _LEVEL2_GHOST**level

        for ai, ag in enumerate((pac, *gh)):
            pos_c[step, ai] = ag.c
            pos_s[step, ai] = ag.s(m)
            if ai == 0:
                pos_m[step, 0] = (
                    (2 if pause_kind == 1 else 3) if dead else (1 if powered else 0)
                )
            else:
                pos_m[step, ai] = 4 if dead else ag.mode
        lvl_t += _DT

    return _Round(pos_c, pos_s, pos_m, levels, fruit, clears, deaths, duration)


def _pac_target(
    m: _Maze,
    pac: _Agent,
    gh: List[_Agent],
    left: np.ndarray,
    fruit: List[Tuple[int, float, float, float, int]],
    t: float,
    powered: bool,
    v: int,
) -> int:
    """Where Pac wants to be: a frightened ghost, then fruit within
    reach, then the nearest corridor that still has dots."""
    if powered:
        prey = [g for g in gh if g.mode == 1]
        if prey:
            return min(prey, key=lambda g: (int(m.dist[v, g.far(m)]), g.c)).far(m)
    for fv, f0, f1, fe, _k in fruit:
        if f0 <= t < f1 and fe == np.inf and m.dist[v, fv] <= 5:
            return fv
    dotted = np.flatnonzero(left > 0)
    if len(dotted) == 0:
        return v
    du = m.dist[v][m.cu[dotted]]
    dv = m.dist[v][m.cv[dotted]]
    near = np.minimum(du, dv)
    k = int(np.argmin(near))
    return int(m.cu[dotted[k]] if du[k] <= dv[k] else m.cv[dotted[k]])


def _ghost_target(
    m: _Maze, gi: int, g: _Agent, gh: List[_Agent], pac: _Agent, scatter: bool
) -> int:
    if g.mode == 2:
        return m.house
    if scatter:
        return m.corners[gi]
    pv = pac.far(m)
    if gi == 0:  # Blinky: straight at him
        return pv
    if gi == 1:  # Pinky: two corridors ahead of his heading
        prev, cur = pac.f, pv
        for _ in range(2):
            opts = [(w, c) for w, c in m.adj[cur] if w != prev] or m.adj[cur]
            w, _c = max(opts, key=lambda oc: (int(m.dist[oc[0], prev]), -oc[1]))
            prev, cur = cur, w
        return cur
    if gi == 2:  # Inky: flanks — near Pac's lead, far from Blinky
        bv = gh[0].far(m)
        cand = np.flatnonzero(m.dist[pv] <= 2)
        return int(cand[int(np.argmax(m.dist[bv][cand]))])
    return pv if m.dist[g.far(m), pv] > 6 else m.corners[3]  # Clyde


def _dry_run(m: _Maze) -> float:
    """Length of a round: how long Pac needs to cover the board with no
    ghosts in the way, plus slack for the ones there will be."""
    cap = 60.0 + 3.0 * m.nc / _PAC_SPEED
    r = _sim(m, 0, cap, ghosts=False)
    m.dry = float(r.clears[0] if r.clears else cap)
    return float(m.dry * _ROUND_SLACK + _ROUND_TAIL)


# --- rendering -------------------------------------------------------


def _blob(
    m: _Maze, c: int, s: float, sigma: float, spill: bool = True
) -> Tuple[List[np.ndarray], List[np.ndarray]]:
    """Light rows and gaussian weights for a point on a corridor, spilling
    around the corner when it sits near a vertex (agents do; dots, which
    would otherwise pile up into a blot at every intersection, don't)."""
    rows: List[np.ndarray] = []
    ws: List[np.ndarray] = []
    ln = float(m.clen[c])
    a0 = s * ln
    cut = 3.0 * sigma
    inv = -0.5 / (sigma * sigma)
    lo, hi = int(m.ptr[c]), int(m.ptr[c + 1])
    d = m.arc[lo:hi] - a0
    keep = np.abs(d) < cut
    if keep.any():
        rows.append(m.rows[lo:hi][keep])
        ws.append(np.exp(inv * d[keep] ** 2))
    if not spill:
        return rows, ws
    for v, back in ((int(m.cu[c]), a0), (int(m.cv[c]), ln - a0)):
        if back >= cut:
            continue
        for _w, c2 in m.adj[v]:
            if c2 == c:
                continue
            lo2, hi2 = int(m.ptr[c2]), int(m.ptr[c2 + 1])
            dv = m.arc[lo2:hi2]
            if int(m.cv[c2]) == v:
                dv = float(m.clen[c2]) - dv
            d2 = dv + back
            keep2 = d2 < cut
            if keep2.any():
                rows.append(m.rows[lo2:hi2][keep2])
                ws.append(np.exp(inv * d2[keep2] ** 2))
    return rows, ws


def _vertex_blob(
    m: _Maze, v: int, sigma: float
) -> Tuple[List[np.ndarray], List[np.ndarray]]:
    """Light rows and weights for a glow sitting on a junction, reaching
    a little way down every corridor that meets there."""
    rows: List[np.ndarray] = []
    ws: List[np.ndarray] = []
    cut, inv = 3.0 * sigma, -0.5 / (sigma * sigma)
    for _w, c in m.adj[v]:
        lo, hi = int(m.ptr[c]), int(m.ptr[c + 1])
        d = m.arc[lo:hi]
        if int(m.cv[c]) == v:
            d = float(m.clen[c]) - d
        keep = d < cut
        if keep.any():
            rows.append(m.rows[lo:hi][keep])
            ws.append(np.exp(inv * d[keep] ** 2))
    return rows, ws


class PacMan(Pattern):
    name = "pacman"
    description = "Pac-Man, dots, and four ghosts running the borders"

    def __init__(self) -> None:
        self._maze_cache: Dict[Tuple[int, int], Optional[_Maze]] = {}
        self._round_cache: Dict[Tuple[int, int, int], _Round] = {}
        self._pel_cache: Dict[Tuple[int, int], Tuple[np.ndarray, ...]] = {}
        self._junc_cache: Dict[Tuple[int, int], Tuple[np.ndarray, np.ndarray]] = {}

    def _maze(self, lights: np.ndarray) -> Tuple[Tuple[int, int], Optional[_Maze]]:
        # Content fingerprint over a strided sample of identity + position:
        # cheap per frame, still purely a function of the array contents.
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
        if key not in self._maze_cache:
            self._maze_cache[key] = _build_maze(lights)
        return key, self._maze_cache[key]

    def _round(self, key: Tuple[int, int], m: _Maze, idx: int) -> _Round:
        ck = (key[0], key[1], idx)
        if ck not in self._round_cache:
            if len(self._round_cache) > 3:
                self._round_cache.pop(next(iter(self._round_cache)))
            self._round_cache[ck] = _sim(m, idx, m.round_len, ghosts=True)
        return self._round_cache[ck]

    def _junction_lights(
        self, key: Tuple[int, int], m: _Maze
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Static extra glow at every intersection — the maze's joints."""
        if key not in self._junc_cache:
            rows, ws = [], []
            for v in range(m.nv):
                r, w = _vertex_blob(m, v, 0.075 * m.unit)
                rows.extend(r)
                ws.extend(w)
            self._junc_cache[key] = (np.concatenate(rows), np.concatenate(ws))
        return self._junc_cache[key]

    def _pellet_lights(self, key: Tuple[int, int], m: _Maze) -> Tuple[np.ndarray, ...]:
        """Flat (row, weight, pellet) table — the board's dots are static
        geometry; only whether they're still there changes per frame."""
        if key not in self._pel_cache:
            rows, ws, ids = [], [], []
            for k in range(len(m.pel_c)):
                c = int(m.pel_c[k])
                sig = (_ENER_SIGMA if m.pel_kind[k] else _DOT_SIGMA) * m.unit
                r, w = _blob(m, c, float(m.pel_s[k]), sig, spill=False)
                for rr, ww in zip(r, w):
                    rows.append(rr)
                    ws.append(ww)
                    ids.append(np.full(len(rr), k, np.int64))
            self._pel_cache[key] = (
                np.concatenate(rows),
                np.concatenate(ws),
                np.concatenate(ids),
            )
        return self._pel_cache[key]

    def render(self, lights: np.ndarray, t: float) -> np.ndarray:
        n = lights.shape[0]
        out = np.zeros((n, 3))
        out[:, 0] = _BG_L
        out[:, 1] = _BG_C
        out[:, 2] = _BG_H

        key, m = self._maze(lights)
        if m is None:
            return out

        idx = int(t // m.round_len)
        tau = t - idx * m.round_len
        rd = self._round(key, m, idx)
        # Rounds cross-fade through black rather than cutting mid-chase.
        veil = min(1.0, tau / 1.2, max(0.0, (m.round_len - tau) / _FADE_OUT))

        lum: List[np.ndarray] = []
        av: List[np.ndarray] = []
        bv: List[np.ndarray] = []
        rws: List[np.ndarray] = []

        def add(rows: np.ndarray, w: np.ndarray, lv: float, c: float, h: float) -> None:
            e = w * (lv * veil)
            rws.append(rows)
            lum.append(e)
            av.append(e * (c * np.cos(np.radians(h))))
            bv.append(e * (c * np.sin(np.radians(h))))

        # --- the maze itself ------------------------------------------
        # Blue walls, the one thing the arcade board never lost. Without
        # them an eaten corridor goes black and the piece loses its shape.
        mh = _MAZE_HC[0] + 9.0 * np.sin(2.0 * np.pi * tau / 41.0)
        breathe = 0.82 + 0.18 * np.sin(2.0 * np.pi * tau / 23.0 + m.vis_c * 0.9)
        add(m.rows, breathe, _MAZE_L, _MAZE_HC[1], mh)
        jrow, jw = self._junction_lights(key, m)
        add(jrow, jw, _JUNC_L, _MAZE_HC[1] * 1.2, mh + 16.0)

        # --- the board ------------------------------------------------
        prow, pw, pid = self._pellet_lights(key, m)
        age = tau - rd.board(tau)
        # Eaten dots pop once and go out; energizers breathe while they last.
        alive = np.where(
            age < 0.0,
            np.where(
                m.pel_kind == 1,
                0.62 + 0.38 * np.sin(2.0 * np.pi * tau / 0.9 + m.pel_c * 0.7),
                1.0,
            ),
            np.clip(1.0 - age / 0.30, 0.0, 1.0) * 2.2,
        )
        alive = np.where(np.isfinite(age) & (age > 0.30), 0.0, alive)
        big = np.where(m.pel_kind == 1, 2.6, 1.0)
        gate = (alive * big)[pid]
        hot = gate > 1e-3
        if hot.any():
            add(prow[hot], pw[hot] * gate[hot], 0.24, _DOT_C, _DOT_H)

        # --- fruit ----------------------------------------------------
        # Sits on a junction, one colour each, and flares as it's taken.
        for fv, f0, f1, fe, fk in rd.fruit:
            end = min(f1, fe + 0.5) if np.isfinite(fe) else f1
            if not (f0 <= tau < end):
                continue
            if tau < fe:
                k = 0.80 + 0.20 * np.sin(2.0 * np.pi * tau / 1.15 + fk)
                k *= min(1.0, (tau - f0) / 0.4)  # blooms in, never snaps on
                if f1 - tau < 3.0:  # about to go: falter
                    k *= 0.45 + 0.55 * (0.5 + 0.5 * np.sin(2.0 * np.pi * tau * 1.6))
            else:
                k = np.clip(1.0 - (tau - fe) / 0.5, 0.0, 1.0) ** 0.6 * 3.4
            fh, fc_ = _FRUITS[fk % len(_FRUITS)]
            for r, w in zip(*_vertex_blob(m, fv, 0.135 * m.unit)):
                add(r, w * k, 0.62, fc_, fh)

        # --- agents ---------------------------------------------------
        step = min(len(rd.pos_c) - 2, max(0, int(tau / _DT)))
        frac = np.clip(tau / _DT - step, 0.0, 1.0)
        for ai in range(5):
            c = int(rd.pos_c[step, ai])
            s = float(rd.pos_s[step, ai])
            if int(rd.pos_c[step + 1, ai]) == c:  # interpolate within a corridor
                s += frac * (float(rd.pos_s[step + 1, ai]) - s)
            mode = int(rd.pos_m[step, ai])
            sig = 0.19 * m.unit
            if ai == 0:
                if mode == 3:  # off the board while it re-dots
                    continue
                if mode == 2:  # caught: swells and fades
                    k = _death_phase(rd, step, tau)
                    if k is None:
                        continue
                    for r, w in zip(*_blob(m, c, s, sig * (1.0 + 2.4 * k))):
                        add(r, w, 0.95 * (1.0 - k) ** 2, _PAC_C, _PAC_H - 70.0 * k)
                    continue
                # A gentle chomp — amplitude, never a strobe.
                chomp = 0.84 + 0.16 * np.sin(2.0 * np.pi * 3.6 * tau)
                boost = 1.12 if mode == 1 else 1.0
                for r, w in zip(*_blob(m, c, s, sig)):
                    add(r, w, 0.95 * chomp * boost, _PAC_C, _PAC_H)
                continue
            if mode in (3, 4):  # housed, or hidden during a death
                continue
            gi = ai - 1
            if mode == 2:  # eyes
                for r, w in zip(*_blob(m, c, s, 0.115 * m.unit)):
                    add(r, w, 0.45, _EYE_HC[1], _EYE_HC[0])
                continue
            if mode == 1:
                left = _power_left(rd, step)
                blink = 0.0 if left > 2.0 else 0.5 + 0.5 * np.sin(2.0 * np.pi * tau)
                h = _FRIGHT_HC[0]
                ch = _FRIGHT_HC[1] * (1.0 - 0.75 * blink)
                lv = 0.55 + 0.30 * blink
            else:
                h, ch = _GHOST_HC[gi]
                lv = 0.80
            for r, w in zip(*_blob(m, c, s, sig)):
                add(r, w, lv, ch, h)
            # A short skirt trailing the way it came.
            ahead = int(rd.pos_c[step + 1, ai]) == c and rd.pos_s[step + 1, ai] >= s
            back = s - 0.21 if ahead else s + 0.21
            if 0.0 <= back <= 1.0:
                for r, w in zip(*_blob(m, c, back, 0.125 * m.unit)):
                    add(r, w * 0.45, lv, ch, h)

        # --- death: a shockwave out through the maze -------------------
        for td, dv in rd.deaths:
            k = tau - td
            if not (0.0 <= k < _FLASH_TIME):
                continue
            # White blow-out over the whole board for a beat, then a ring
            # racing outward along the corridors and reddening as it goes.
            hop = m.dist[dv].astype(np.float64) * m.unit
            d = np.minimum(hop[m.vis_u] + m.vis_du, hop[m.vis_v] + m.vis_dv)
            ring = np.exp(-(((d - _FLASH_SPEED * m.unit * k) / (0.62 * m.unit)) ** 2))
            amp = np.exp(-k / 0.62)
            # Slow enough that the wire's per-frame slew cap (~0.24 L)
            # can actually reach it before it decays.
            blow = np.exp(-k / 0.30) * min(1.0, k / 0.12)
            w = ring * amp * 1.35 + blow * 0.75
            hot = w > 2e-3
            if hot.any():
                add(
                    m.rows[hot],
                    w[hot],
                    0.9,
                    0.02 + 0.19 * min(1.0, k / 0.45),
                    30.0,
                )

        # --- board-cleared flourish -----------------------------------
        for tc in rd.clears:
            k = tau - tc
            if 0.0 <= k < _CLEAR_FLOURISH:
                pulse = np.exp(-k / 1.1) * (0.5 + 0.5 * np.cos(2.0 * np.pi * k / 0.75))
                add(m.rows, np.full(len(m.rows), pulse), 0.75, _PAC_C, _PAC_H)

        if not rws:
            return out
        rows = np.concatenate(rws)
        L = np.bincount(rows, weights=np.concatenate(lum), minlength=n)
        A = np.bincount(rows, weights=np.concatenate(av), minlength=n)
        B = np.bincount(rows, weights=np.concatenate(bv), minlength=n)
        out[:, 0] = _BG_L + 0.93 * (1.0 - np.exp(-1.9 * L))
        chroma = np.hypot(A, B) / np.maximum(L, 1e-6)
        out[:, 1] = _BG_C + np.clip(chroma, 0.0, 0.37) * (1.0 - np.exp(-2.6 * L))
        out[:, 2] = np.where(
            L > 1e-6, np.degrees(np.arctan2(B, A)) % 360.0, float(_BG_H)
        )
        return out


def _death_phase(rd: _Round, step: int, tau: float) -> Optional[float]:
    """0..1 through the collapse, or None once it should be dark."""
    i = step
    while i > 0 and rd.pos_m[i - 1, 0] == 2:
        i -= 1
    k = (tau - i * _DT) / _DEATH_TIME
    return None if k >= 1.0 else float(np.clip(k, 0.0, 1.0))


def _power_left(rd: _Round, step: int) -> float:
    """Seconds of frightened time remaining, read off the sampled track."""
    i = step
    while i + 1 < len(rd.pos_m) and rd.pos_m[i + 1, 0] == 1:
        i += 1
        if i - step > 200:
            break
    return float((i - step) * _DT)
