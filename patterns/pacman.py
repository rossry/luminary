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

The board is then *thinned*: every interior spoke is dropped except in
dead-end panels (those stitched to the rest of the net by a single
seam), which keep all three — the game runs on the border lattice with
a few dense pockets, 105 junctions and 161 corridors on the star.
Dropped spokes keep a dim structural glow, so the panel still reads as
built, but carry no dots and no traffic.

Dots are spaced by arclength rather than counted per corridor. The short
beams run about half the length of the long ones, and a fixed count per
corridor crowded them to nearly double the density.

The board's far tips are travel sinks and ghost-camp pockets, so after
thinning it is *shortcut*: the two most distant junctions are joined by a
lightless portal corridor, worst pair first, up to four times, until the
graph is tight. A portal carries no dots and takes real time to cross,
and hunting ghosts labour through it (the arcade's tunnel rule) — Pac's
escape valve, and what keeps a corner from being a death trap.

A whole round is simulated once and memoized, then played back. The
simulation is a pure function of (maze, round index): Pac sweeping the
board a clump of dots at a time — committing to a corridor until it is
clean rather than leaving crumbs — routing around energizers until they
are worth taking and turning on them when the pack closes in; four ghosts
running the arcade's targeting rules translated to a graph (Blinky on
Pac and growing bolder as the board empties — Cruise Elroy — Pinky two
corridors ahead, Inky flanking away from Blinky, Clyde chasing only
beyond six hops), scatter/chase alternation with the classic reversal,
energizers, frightened ghosts, eyes returning to the house, fruit,
deaths. The maze (runs, clustering, thinning, portals, all-pairs
distances) is ~80–90 ms, once per geometry; a full round is ~130 ms on
the star, paid at the first frame that needs it — so a round boundary
stalls one beat. Playback frames are direct indexing into the recorded
tables plus bincounts over the accumulated contributions: ~0.7 ms steady
state at 6,660 lights.

The round is a fixed-length window, not one game: its length comes from a
ghost-free dry run of Pac's covering walk times a slack factor, and
inside it games play out to their natural ends — a cleared board
flourishes and re-dots a faster level; a Pac who spends all five lives
triggers a red anti-victory flash and the ghosts tour the empty board
(the cabinet's attract screen) until the window fades. Fixing the length
rather than the outcome is what keeps random access O(1): round index is
floor(t / round_len), and pricing an arbitrary t would otherwise mean
summing the simulated outcomes of every game before it. Same (lights, t)
in, same colors out, in any call order (spec §9.1.3); the caches are
memoization keyed by content.

The living things — Pac, the ghosts, the fruit, an energizer at the top
of its breath — are driven hard against the wire's luminance ceiling, so
they read at full brightness over the dim blue lattice and its quiet
amber dots. Their glow spills around corners onto the thinned-away spokes
too, and the death ripple washes down them, so the dark strips are part
of the piece and not merely switched off.
"""

import zlib
from collections import deque
from typing import Dict, List, NamedTuple, Optional, Tuple

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
# Blinky's Cruise Elroy: (dots-left fraction, speed multiplier). The endgame
# needs to converge on *something*, and a ghost growing bolder as the board
# empties is the arcade's own answer — tension the eye can read, where a Pac
# who simply outruns everyone reads as the game being rigged for him.
_ELROY = ((0.35, 1.09), (0.15, 1.18))
_FRIGHT_TIME = 6.5
_DOT_SPACING = 0.40  # of the median corridor: dots sit this far apart
_DOT_SIGMA = 0.064  # gaussian half-width; 3 sigma stays under the spacing
_ENER_SIGMA = 0.16  # energizers: the board's big bright dots
_ENERGIZERS = 5
# Five, not the arcade's three. Clearing the board means walking every
# corridor — dot density cannot shorten that — so a full round is a long
# errand, and on the star even a clever Pac needs the extra credits to reach
# the end of it more often than not. Fewer, and the round spends most of its
# length on the attract screen with the board already eaten.
_LIVES = 5
_DEATH_TIME = 1.8  # collapse animation
_RESPAWN_PAUSE = 0.9  # dark beat before the board resumes
_CATCH_FRAC = 0.10  # of a corridor length
_HOUSE_HOLD = 1.0  # eyes wait this long in the house
_RELEASE = (1.6, 4.2, 7.6, 11.0)  # ghost release times after a reset;
# the first gap is the arcade's READY! beat, and it keeps round 0 —
# the one every restart opens on — from losing a life in six seconds.
_SCATTER_CHASE = (7.0, 20.0, 7.0, 20.0, 5.0, 20.0, 5.0)  # then chase forever
_CLEAR_FLOURISH = 3.0
_GAMEOVER_FLOURISH = 3.2  # the red anti-victory flash, then attract mode
# Pac may hurry when he is behind, but only just. At the old 1.2 he reached
# 2.2x the ghosts and the game stopped being a chase; worse, his per-tick
# stride (0.22 x unit) outran his own eat diameter (0.20), so he could skip
# dots mid-corridor — the cheat manufactured the very remains it existed to
# clean up.
_LAG_BOOST = 0.25
# --- Pac's head ------------------------------------------------------
_SAFE_BAR = 2  # never turn into a corridor a hunter is within this many hops of
_HUNT_NEAR = 3  # a hunter this close makes an energizer worth going for
_BLOCKED_N = 3  # choices pushed off-target before he changes his approach
_LURE_TIME = 6.0  # how long he draws the pack away from food they are sitting on
_LURE_FREE = 4  # ... and how far they have to be for it to have worked
# --- portals ---------------------------------------------------------
# The build is a partial shell, so the board is a star: its tips are far
# from each other in hops, and a corner is where a ghost pins you. Rather
# than hope Pac routes around that, join the tips — repeatedly bridge the
# two most distant junctions, which is exactly the pair a diameter-shrinking
# shortcut helps most. Portals carry no lights and no dots: they are pure
# graph edges that agents take time to cross, and the render draws them as
# a hand-off between their two mouths.
_MAX_PORTALS = 4
_PORTAL_MIN_DIAM = 8  # stop once the graph is this tight (hops)
_PORTAL_LEN = 1.0  # x unit: transit is real travel, not a teleport
_PORTAL_GHOST_SLOW = 0.55  # the arcade's tunnel rule — Pac's escape valve
_ROUND_SLACK = 1.8  # dry-run clear time x this, + tail
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
# The luminance the living things are driven to. The wire maps accumulated
# energy through 1 - exp(-1.9 L) onto a 0.975 ceiling; at this level the
# heroes sit hard against it, so Pac, the ghosts, the fruit and a fully
# swelled energizer all read at full brightness while the walls and the
# quiet field of dots stay well below — the piece is a glowing structure,
# and these are the lights that move on it.
_HERO_L = 2.2
_GHOST_HC = ((28.0, 0.19), (350.0, 0.14), (200.0, 0.15), (60.0, 0.17))
_FRIGHT_HC = (272.0, 0.16)
_EYE_HC = (230.0, 0.05)
_PORTAL_HC = (185.0, 0.15)  # teal: a colour the maze wears nowhere else, so
# the two mouths of a portal read as one gate; they breathe in lockstep to
# say the same thing a second way.
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
_FRUIT_GATES = (0.10, 0.21, 0.32, 0.43, 0.54, 0.65, 0.76, 0.86)
_FRUIT_DWELL = 14.0
_FLASH_SPEED = 2.1  # death shockwave, corridors per second
_FLASH_TIME = 2.6  # the ripple's whole life; it fades to nothing by the end


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


class _Dim(NamedTuple):
    """The thinned-away spokes. No dots, no traffic, no junction glow — but
    the render still reaches down them (a turning agent's spill, the death
    ripple, the board-wide flashes), so they need arclength and a live
    endpoint to hang from, not merely a list of rows."""

    rows: np.ndarray  # (k,) light rows, grouped by dropped corridor
    arc: np.ndarray  # (k,) arclength from the corridor's u end
    ptr: np.ndarray  # (nd+1,) slice bounds into rows/arc
    clen: np.ndarray  # (nd,) corridor length, world units
    u: np.ndarray  # (nd,) live vertex at the u end, or -1 if compacted away
    v: np.ndarray  # (nd,) live vertex at the v end, or -1


_NO_DIM = _Dim(
    np.empty(0, np.int64),
    np.empty(0, np.float64),
    np.zeros(1, np.int64),
    np.empty(0, np.float64),
    np.empty(0, np.int32),
    np.empty(0, np.int32),
)


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
        dim: _Dim,
        is_portal: np.ndarray,
    ):
        self.cu, self.cv = cu, cv  # (nc,) corridor endpoints
        self.dim = dim  # thinned-away spokes: render-only geometry
        self.is_portal = is_portal  # (nc,) lightless shortcut corridors
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
        # Which thinned-away spokes hang off each live vertex, and whether
        # their arclength runs from that end — so a glow at a junction can
        # spill down the dropped spokes as readily as down the live ones.
        self.dim_adj: List[List[Tuple[int, bool]]] = [[] for _ in range(self.nv)]
        for di in range(len(dim.clen)):
            if int(dim.u[di]) >= 0:
                self.dim_adj[int(dim.u[di])].append((di, True))
            if int(dim.v[di]) >= 0:
                self.dim_adj[int(dim.v[di])].append((di, False))
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
    counts[m.is_portal] = 0  # a portal is a way through, not a place to eat
    pptr = np.concatenate([[0], np.cumsum(counts)]).astype(np.int64)
    pc = np.repeat(np.arange(m.nc), counts)
    ps = np.concatenate([(np.arange(k) + 0.5) / max(k, 1) for k in counts])
    kind = np.zeros(len(pc), np.int8)
    # Spread the energizers: the corners first, then whatever is farthest
    # from every energizer already placed.
    seeds = list(m.corners)
    while len(seeds) < _ENERGIZERS:
        seeds.append(int(np.argmax(m.dist[seeds].min(axis=0))))
    used = set()
    for v in seeds[:_ENERGIZERS]:
        for _, c in sorted(m.adj[v], key=lambda oc: oc[1]):
            # counts[c] == 0 on a portal, and indexing its empty slice would
            # brand the *next* corridor's first dot an energizer.
            if c not in used and counts[c] > 0:
                used.add(c)
                kind[int(pptr[c]) + int(counts[c]) // 2] = 1
                break
    return pc, ps, kind, pptr, counts


def _spokes_to_drop(
    cu: np.ndarray, cv: np.ndarray, vxy: np.ndarray, nv: int
) -> List[int]:
    """Interior spokes to remove: all of them, except in dead-end panels.

    Spokes are found geometrically — the pattern only sees lights. An
    incenter is a degree-3 vertex whose three corridors leave roughly
    120° apart; at a border midpoint (also degree 3 on the net's outer
    boundary) the gaps run ~90/90/180, so a 150° cap separates them
    cleanly: one incenter per structural triangle on 4A-33/35/37, zero
    on the hex demo. A panel's edge midpoints are degree 4 where it
    seams onto another panel and degree 3 on the outer boundary, so a
    dead-end panel — one you enter and must back out of — has at most
    one degree-4 neighbor around its incenter. Those keep all three
    spokes; every other panel loses all three, and its unused incenter
    is compacted out of the graph after thinning. Border corridors are
    never touched, so the maze stays connected; the reachability guard
    below would catch a classifier regression loudly.
    """
    adj: List[List[Tuple[int, int]]] = [[] for _ in range(nv)]
    for ci in range(len(cu)):
        adj[int(cu[ci])].append((int(cv[ci]), ci))
        adj[int(cv[ci])].append((int(cu[ci]), ci))
    drops: List[int] = []
    for v in range(nv):
        if len(adj[v]) != 3:
            continue
        p = vxy[v]
        ang = sorted(
            float(np.arctan2(vxy[w][1] - p[1], vxy[w][0] - p[0])) for w, _ in adj[v]
        )
        gaps = (ang[1] - ang[0], ang[2] - ang[1], 2.0 * np.pi - (ang[2] - ang[0]))
        if max(gaps) >= np.radians(150.0):
            continue  # a border vertex, not an incenter
        seams = sum(1 for w, _ in adj[v] if len(adj[w]) >= 4)
        if seams > 1:
            drops.extend(c for _, c in adj[v])
    return drops


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


def _hop_distances(adj: List[List[Tuple[int, int]]], nv: int) -> Tuple[np.ndarray, int]:
    """All-pairs hop distance by BFS, with ``far`` marking unreachable."""
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
    return dist, far


def _add_portals(
    cu: np.ndarray,
    cv: np.ndarray,
    clen: np.ndarray,
    ptr: np.ndarray,
    unit: float,
    nv: int,
    adj: List[List[Tuple[int, int]]],
    dist: np.ndarray,
    far: int,
) -> Tuple[
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    List[List[Tuple[int, int]]],
    np.ndarray,
]:
    """Bridge the most distant pairs of junctions, worst first.

    Each pass takes the two *reachable* vertices furthest apart in hops and
    joins them with a lightless corridor, then recomputes distances so the
    next pass sees a board the previous shortcut already tightened. Vertices
    already wearing a mouth are excluded from later passes, which spreads the
    gates around the board instead of stacking them on one stubborn tip.

    Only finite distances are considered. A net with detached panels keeps
    them detached — the reachability guard downstream still gets to decline
    the maze, rather than a portal silently stitching a component the build
    does not physically connect.
    """
    is_portal = np.zeros(len(cu), bool)
    mouths: List[int] = []
    for _ in range(_MAX_PORTALS):
        d = np.where(dist < far, dist, -1).astype(np.int32)
        if mouths:
            gone = np.array(mouths, np.intp)
            d[gone, :] = -1
            d[:, gone] = -1
        best = int(d.max()) if d.size else -1
        if best < _PORTAL_MIN_DIAM:
            break
        # argwhere is row-major, so the first hit is the lexicographically
        # smallest (u, v) among the ties: same maze in, same portals out.
        u, v = (int(x) for x in np.argwhere(d == best)[0])
        cu = np.append(cu, u).astype(np.int32)
        cv = np.append(cv, v).astype(np.int32)
        clen = np.append(clen, _PORTAL_LEN * unit)
        ptr = np.append(ptr, ptr[-1]).astype(np.int64)  # no lights of its own
        is_portal = np.append(is_portal, True)
        mouths.extend((u, v))
        # Refresh distances without redoing 105 breadth-first searches. One
        # new edge of length 1 means any route from i to j either ignores it
        # or crosses it exactly once — twice would leave a vertex and return
        # to it, a loop you can cut for a shorter path. So three cases, and
        # the elementwise minimum of them is exact:
        #   ignore it       dist[i, j]
        #   cross u -> v    dist[i, u] + 1 + dist[v, j]
        #   cross v -> u    dist[i, v] + 1 + dist[u, j]
        # A column plus a row broadcasts to the whole table at once. The far
        # sentinel needs no clamp: the result always includes the old value,
        # so it can never climb above it.
        dist = np.minimum(
            dist,
            np.minimum(
                dist[:, u][:, None] + 1 + dist[v, :][None, :],
                dist[:, v][:, None] + 1 + dist[u, :][None, :],
            ),
        )
    if mouths:
        adj = _corridor_adj(cu, cv, nv)
    return cu, cv, clen, ptr, is_portal, adj, dist


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
    vxy = np.zeros((nv, 2))
    for e, r in enumerate(runs):
        for i, end in ((0, 0), (-1, 1)):
            vxy[labels[2 * e + end]] = (
                a[r[i], LightColumns.X],
                a[r[i], LightColumns.Y],
            )

    # Thin the interior (see _spokes_to_drop). Dropped corridors leave the
    # game entirely — dots, traffic, junction glow — but their light rows
    # are kept aside so the render can hold them at a dim structural level
    # instead of letting a physical strip go black.
    dim = _NO_DIM
    drops = _spokes_to_drop(cu, cv, vxy, nv)
    if drops:
        keep = np.ones(len(cu), bool)
        keep[drops] = False
        kept = np.flatnonzero(keep)
        # Captured here because the kept-filter just below rebuilds
        # rows/arc/ptr and the dropped slices stop being addressable.
        dropped = np.array(sorted(drops), np.int64)
        dim = _Dim(
            np.concatenate([rows[int(ptr[ci]) : int(ptr[ci + 1])] for ci in dropped]),
            np.concatenate([arc[int(ptr[ci]) : int(ptr[ci + 1])] for ci in dropped]),
            np.concatenate(
                [[0], np.cumsum([int(ptr[ci + 1] - ptr[ci]) for ci in dropped])]
            ).astype(np.int64),
            clen[dropped].copy(),
            cu[dropped].copy(),
            cv[dropped].copy(),
        )
        arc = np.concatenate([arc[int(ptr[ci]) : int(ptr[ci + 1])] for ci in kept])
        rows = np.concatenate([rows[int(ptr[ci]) : int(ptr[ci + 1])] for ci in kept])
        ptr = np.concatenate(
            [[0], np.cumsum([int(ptr[ci + 1] - ptr[ci]) for ci in kept])]
        ).astype(np.int64)
        cu, cv, clen = cu[keep], cv[keep], clen[keep]
        # A rule that strips a vertex of every corridor (deadend does, to
        # most incenters) must also remove the vertex, or the reachability
        # guard below would reject the maze for a vertex the game no
        # longer contains.
        used = np.zeros(nv, bool)
        used[cu] = True
        used[cv] = True
        if not used.all():
            remap = (np.cumsum(used) - 1).astype(np.int32)
            # A dropped spoke's incenter end goes with it. -1 means "no live
            # vertex this side", so the render hangs the spoke off its other
            # end. The mask is load-bearing: remap sends an unused vertex to
            # its predecessor's index, which would silently graft the spoke
            # onto a stranger somewhere else on the board.
            dim = dim._replace(
                u=np.where(used[dim.u], remap[dim.u], -1).astype(np.int32),
                v=np.where(used[dim.v], remap[dim.v], -1).astype(np.int32),
            )
            cu, cv = remap[cu], remap[cv]
            vxy = vxy[used]
            nv = int(used.sum())
        assert bool(
            ((dim.u >= 0) | (dim.v >= 0)).all()
        ), "a thinned spoke lost both of its endpoints"

    adj = _corridor_adj(cu, cv, nv)
    dist, far = _hop_distances(adj, nv)
    cu, cv, clen, ptr, is_portal, adj, dist = _add_portals(
        cu, cv, clen, ptr, unit, nv, adj, dist, far
    )

    m = _Maze(cu, cv, clen, adj, dist, vxy, rows, arc, ptr, unit, dim, is_portal)
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
        gameovers: List[float],
        length: float,
    ):
        self.pos_c = pos_c  # (T, 5) corridor per agent (0 = Pac)
        self.pos_s = pos_s  # (T, 5) position in [0,1] from corridor's cu
        self.pos_m = pos_m  # (T, 5) mode
        self.levels = levels  # per level: (start time, eaten time per pellet)
        self.fruit = fruit  # (junction, t0, t1, t_eaten, kind)
        self.clears = clears  # times the board was cleared
        self.deaths = deaths  # (time, junction the shockwave starts from)
        self.gameovers = gameovers  # times the last life ran out
        self.length = length

    def board(self, tau: float) -> Tuple[float, np.ndarray]:
        """The board in force at tau, as (when it was laid, eaten times) — a
        cleared board re-dots, and the render blooms it in from that instant
        rather than snapping every dot on at once."""
        best = self.levels[0]
        for lv in self.levels:
            if lv[0] <= tau:
                best = lv
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
    gameovers: List[float] = []

    speed = _PAC_SPEED * m.unit
    catch = _CATCH_FRAC * m.unit
    eat_r = 0.10 * m.unit

    def _walkable(v: int) -> List[int]:
        """Corridors at v that someone can be *seen* standing on: a portal
        renders as a hand-off between its mouths, so nobody starts inside
        one. Falls back to any corridor if a vertex somehow has only portals."""
        opts = [c for _w, c in m.adj[v] if not m.is_portal[c]]
        return opts or [c for _w, c in m.adj[v]]

    def spawn() -> Tuple[_Agent, List[_Agent]]:
        pv = m.start
        pc = min(_walkable(pv))
        pac = _Agent(pc, pv)
        gs = []
        house_opts = _walkable(m.house)
        for gi in range(4):
            hc = house_opts[gi % len(house_opts)]
            g = _Agent(hc, m.house)
            g.mode, g.timer = 3, _RELEASE[gi]
            gs.append(g)
        return pac, gs

    pac, gh = spawn()
    brain = _PacBrain(m)
    lives = _LIVES
    level = 0
    lvl_t = 0.0  # time since the level (or a death) started
    power_until = -1.0
    pause_until = -1.0
    pause_kind = 0  # 1 = caught, 2 = board cleared, 3 = out of lives
    attract = False  # the cabinet playing to an empty room
    ghost_mult = 1.0
    prev_phase = 0
    last_turn = -9.0
    lag = 0.0
    fade_at = duration - _FADE_OUT
    n_dots = float(npel)

    for step in range(steps):
        t = step * _DT

        if pause_kind and t >= pause_until:
            # Out of lives ends the game for good. The window is fixed, so
            # what follows is not a fresh credit but the attract screen: the
            # ghosts keep the board moving until the round fades out.
            if pause_kind == 3:
                attract = True
            pause_kind = 0
            pac, gh = spawn()
            lvl_t = 0.0
        dead = pause_kind != 0

        # Scatter/chase phases, with the classic reversal on every flip.
        phase, acc = 0, 0.0
        for dwell in _SCATTER_CHASE:
            if lvl_t < acc + dwell:
                break
            acc += dwell
            phase += 1
        scatter = phase % 2 == 0 and phase < len(_SCATTER_CHASE)
        if ghosts and not dead and not attract and step > 0 and phase != prev_phase:
            for g in gh:
                if g.mode in (0, 1):
                    g.p, g.f = 1.0 - g.p, g.far(m)
        prev_phase = phase
        powered = t < power_until

        # --- Pac ------------------------------------------------------
        if not dead and not attract:
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
            behind = 1.0 + _LAG_BOOST * lag
            pac.p += speed * behind * _DT / m.clen[pac.c]
            while pac.p >= 1.0:
                v = pac.far(m)
                carry = pac.p - 1.0
                opts = _options(m, pac, allow_back=True)
                pac.nchoice += 1
                tgt, want_power = brain.target(
                    m, gh, fruit, t, powered, power_until - t, v
                )
                if ghosts:
                    safe = [
                        min(
                            (int(m.dist[w, g.far(m)]) for g in gh if g.mode == 0),
                            default=99,
                        )
                        for w, _ in opts
                    ]
                    # Never walk into a ghost's lap; if every way out is
                    # bad, take the least bad one. This runs while he is
                    # powered too: only *hunting* ghosts count, so it costs
                    # nothing during a clean fright, and it is the one thing
                    # standing between him and a ghost that left the house
                    # after the pellet went down.
                    bar = min(_SAFE_BAR, max(safe))
                    opts = [o for o, s in zip(opts, safe) if s >= bar]

                def _cost(oc: Tuple[int, int]) -> Tuple[int, int, int]:
                    w2, c2 = oc
                    d = int(m.dist[w2, tgt])
                    if not want_power and brain.ener[c2] > 0:
                        # Two hops of reluctance: enough to route around a
                        # power pellet while tidying, not enough to make one
                        # unreachable when it is the only way on.
                        d += 2
                    return (d, 0 if left[c2] > 0 else 1, _fnv(rnd, 1, pac.nchoice, c2))

                w, c = min(opts, key=_cost)
                pac.enter(m, v, c, carry)
                brain.note_progress(m, tgt, w, v, t)

            # Eat whatever he passes over.
            a0 = pac.s(m) * m.clen[pac.c]
            lo, hi = int(m.pel_ptr[pac.c]), int(m.pel_ptr[pac.c + 1])
            for k in range(lo, hi):
                if eaten[k] == np.inf:
                    if abs(m.pel_s[k] * m.clen[pac.c] - a0) < eat_r:
                        eaten[k] = t
                        left[pac.c] -= 1
                        brain.ate(pac.c, bool(m.pel_kind[k] == 1))
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
            if ghosts:
                for g in gh:
                    # Judge the threat on the same terms as the catch. Mode 0
                    # only, so a frightened ghost sharing his corridor is prey
                    # rather than a reason to turn — but a hunter is a hunter
                    # whether or not he happens to be powered.
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
                        # Not frightened, even mid-energizer: a ghost that was
                        # in the house when the pellet went down comes out its
                        # own colour, as in the arcade. Pac has to watch for
                        # it — see the safety filter, which is why that filter
                        # runs while he is powered too.
                        g.mode, g.p, g.f = 0, 0.0, m.house
                    continue
                if g.mode == 1 and not powered:
                    g.mode = 0
                # Blinky alone grows bolder as the board empties, so the
                # endgame tightens by a ghost getting braver rather than by
                # Pac quietly being handed the legs to outrun everyone.
                hunt_sp = _GHOST_SPEED * ghost_mult
                if gi == 0:
                    frac_left = left.sum() / max(1.0, n_dots)
                    for gate, mult in _ELROY:
                        if frac_left <= gate:
                            hunt_sp = _GHOST_SPEED * ghost_mult * mult
                sp = (
                    _EYES_SPEED
                    if g.mode == 2
                    else (_FRIGHT_SPEED if g.mode == 1 else hunt_sp)
                )
                # The arcade's tunnel: ghosts labour through a portal while
                # Pac does not. This is what makes a shortcut an escape and
                # not merely a shorter way to be cornered.
                if g.mode in (0, 1) and m.is_portal[g.c]:
                    sp *= _PORTAL_GHOST_SLOW
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
                        # With no Pac to hunt, the pack tours the corners on
                        # a slow rotation — the cabinet's attract screen.
                        tgt = (
                            m.corners[(gi + int(t / 7.0)) % len(m.corners)]
                            if attract
                            else _ghost_target(m, gi, g, gh, pac, scatter)
                        )
                        i = _toward(m, opts, tgt, _fnv(rnd, 4, gi, g.nchoice))
                    g.enter(m, v, opts[i][1], carry)

                if g.mode in (0, 1) and g.c == pac.c and not attract:
                    d = abs(g.s(m) - pac.s(m)) * m.clen[g.c]
                    if d < catch:
                        if g.mode == 1:
                            g.mode = 2
                        else:
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
                            if lives <= 0:
                                # The red flash starts as the ripple finishes,
                                # so the board is never running two of its own
                                # full-width effects at once.
                                pause_kind = 3
                                pause_until = t + _FLASH_TIME + _GAMEOVER_FLOURISH
                                gameovers.append(t + _FLASH_TIME)
                            else:
                                pause_kind = 1
                                pause_until = t + _DEATH_TIME + _RESPAWN_PAUSE
                            break

        # Fruit: eight a level, sitting on a junction, each a different one.
        if ghosts and not dead and not attract:
            frac = 1.0 - left.sum() / max(1.0, n_dots)
            for idx, gate in enumerate(_FRUIT_GATES):
                key = level * len(_FRUIT_GATES) + idx
                if frac >= gate and len(fruit) == key:
                    v = m.fruit_spots[_fnv(rnd, 5, key) % len(m.fruit_spots)]
                    kind = (key + rnd) % len(_FRUITS)
                    fruit.append((v, t, t + _FRUIT_DWELL, np.inf, kind))

        # Board cleared: flourish, then re-dot and speed the ghosts up, so
        # a finished board never leaves the sculpture sitting empty.
        if left.sum() == 0 and not dead and not attract:
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
                    gameovers,
                    t,
                )
            pause_until = t + _CLEAR_FLOURISH
            pause_kind = 2
            eaten = np.full(npel, np.inf, np.float32)
            levels.append((t + _CLEAR_FLOURISH, eaten))
            left[:] = m.pel_n
            brain.reset(m)
            level += 1
            ghost_mult = _LEVEL2_GHOST**level

        for ai, ag in enumerate((pac, *gh)):
            pos_c[step, ai] = ag.c
            pos_s[step, ai] = ag.s(m)
            if ai == 0:
                if attract:
                    pos_m[step, 0] = 3  # gone; the ghosts have the board
                elif dead:
                    # A game-over pause collapses him too — the last life
                    # ends the same way the others did.
                    pos_m[step, 0] = 2 if pause_kind in (1, 3) else 3
                else:
                    pos_m[step, 0] = 1 if powered else 0
            else:
                pos_m[step, ai] = 4 if dead else ag.mode
        lvl_t += _DT

    return _Round(
        pos_c, pos_s, pos_m, levels, fruit, clears, deaths, gameovers, duration
    )


class _PacBrain:
    """What Pac is trying to do, and why he stops changing his mind.

    Everything here is *simulation* state. The pattern stays a pure function
    of (lights, t) because a round is simulated once from a fixed seed and
    memoized; what has to hold inside is determinism, so this works in
    arrays and sorted lists, breaks ties with _fnv, and never lets set or
    dict ordering reach a decision.

    Three habits, against three ways the old greedy Pac looked stupid:
    he sweeps the clump of dots he is standing in before starting another,
    instead of leaving crumbs to walk back for; he routes *around* power
    pellets until they are worth something; and when the pack has simply
    parked on the last of the food he pulls them off it rather than
    twitching toward the dots and away again.
    """

    __slots__ = (
        "cadj",
        "plain",
        "ener",
        "comp",
        "cur_rep",
        "goal_c",
        "goal_power",
        "dirty",
        "blocked",
        "lure_until",
        "lure_tgt",
        "contested",
        "free_ener_until",
    )

    def __init__(self, m: _Maze):
        # Corridors meeting at a junction, precomputed: the clump sweep is
        # then a walk over a static graph rather than a re-derivation.
        self.cadj: List[List[int]] = [[] for _ in range(m.nc)]
        for v in range(m.nv):
            cs = [c for _w, c in m.adj[v]]
            for i, c in enumerate(cs):
                for c2 in cs[i + 1 :]:
                    self.cadj[c].append(c2)
                    self.cadj[c2].append(c)
        for lst in self.cadj:
            lst.sort()
        self.comp = np.full(m.nc, -1, np.int32)
        self.reset(m)

    def reset(self, m: _Maze) -> None:
        """A fresh board: every dot back, no clump chosen yet."""
        self.plain = np.zeros(m.nc, np.int32)
        self.ener = np.zeros(m.nc, np.int32)
        for k in range(len(m.pel_c)):
            c = int(m.pel_c[k])
            if m.pel_kind[k] == 1:
                self.ener[c] += 1
            else:
                self.plain[c] += 1
        self.cur_rep = -1
        self.goal_c = -1
        self.goal_power = False
        self.dirty = True
        self.blocked = 0
        self.lure_until = -1.0
        self.lure_tgt = -1
        self.contested = -1
        self.free_ener_until = -1.0

    def ate(self, c: int, energizer: bool) -> None:
        if energizer:
            self.ener[c] -= 1
        else:
            self.plain[c] -= 1
        if self.plain[c] + self.ener[c] <= 0:
            self.dirty = True  # a corridor emptying can split a clump

    def _label(self, m: _Maze) -> None:
        """Connected clumps of still-dotted corridors. Portals conduct but
        never hold dots, so two tips joined by one count as a single clump."""
        self.comp[:] = -1
        live = (self.plain + self.ener) > 0
        pass_through = live | m.is_portal
        n = 0
        for c0 in range(m.nc):
            if self.comp[c0] >= 0 or not pass_through[c0]:
                continue
            self.comp[c0] = n
            q = deque([c0])
            while q:
                c = q.popleft()
                for c2 in self.cadj[c]:
                    if self.comp[c2] < 0 and pass_through[c2]:
                        self.comp[c2] = n
                        q.append(c2)
            n += 1
        self.dirty = False

    @staticmethod
    def _closest(m: _Maze, v: int, mask: np.ndarray) -> Tuple[int, int]:
        """The corridor in ``mask`` nearest to v, and the end of it to aim
        for. (-1, v) when the mask is empty.

        Aim at the *far* end. Aiming at the near one means that the moment he
        arrives at the corridor's mouth he has reached his target, every way
        on looks equally good, and the tiebreak walks him off down whichever
        one it likes — the corridor he came for still full of dots. Targeting
        the far end makes "arrived" and "swept it" the same event.
        """
        cs = np.flatnonzero(mask)
        if not len(cs):
            return -1, v
        du = m.dist[v][m.cu[cs]]
        dv = m.dist[v][m.cv[cs]]
        k = int(np.argmin(np.minimum(du, dv)))
        far_end = m.cv[cs[k]] if du[k] <= dv[k] else m.cu[cs[k]]
        return int(cs[k]), int(far_end)

    def target(
        self,
        m: _Maze,
        gh: List[_Agent],
        fruit: List[Tuple[int, float, float, float, int]],
        t: float,
        powered: bool,
        power_left: float,
        v: int,
    ) -> Tuple[int, bool]:
        """Where he wants to be, and whether he currently wants a power
        pellet (which switches off the penalty that keeps him off them)."""
        hunters = [g for g in gh if g.mode == 0]

        # (a) Run down a frightened ghost — but only one he can actually
        #     catch before the fright wears off. Chasing a ghost across the
        #     board and arriving as it turns blue-to-solid is the single
        #     dumbest thing the old Pac did.
        if powered:
            reach = 0.8 * power_left * _PAC_SPEED * (1.0 - _FRIGHT_SPEED)
            prey = [g for g in gh if g.mode == 1 and int(m.dist[v, g.far(m)]) <= reach]
            if prey:
                pick = min(prey, key=lambda g: (int(m.dist[v, g.far(m)]), g.c))
                return pick.far(m), False

        if self.dirty:
            self._label(m)
        live = (self.plain + self.ener) > 0
        near_hunter = min((int(m.dist[v, g.far(m)]) for g in hunters), default=99)

        # (b) Cornered with a power pellet still on the board: turn around
        #     and go take it. This is the whole point of saving them.
        if self.ener.sum() > 0 and near_hunter <= _HUNT_NEAR:
            return self._closest(m, v, self.ener > 0)[1], True

        # (c) Fruit, if it is close enough to be on the way.
        for fv, f0, f1, fe, _k in fruit:
            if f0 <= t < f1 and fe == np.inf and m.dist[v, fv] <= 5:
                return fv, False

        # (d) Pulling the pack off food they have parked on.
        if t < self.lure_until:
            if self.contested >= 0 and all(
                int(m.dist[g.far(m), self.contested]) >= _LURE_FREE for g in hunters
            ):
                self.lure_until = -1.0  # it worked; go back for the food
            elif self.lure_tgt >= 0:
                return self.lure_tgt, False

        # (e) Otherwise: sweep the clump he is in, one corridor at a time.
        #     He commits to a corridor and holds it until it is empty. This
        #     is the part that stops the flinching — re-deciding at every
        #     junction let two corridors swap places as "nearest" and he
        #     rocked between them indefinitely, eating nothing. Worse, the
        #     blocked counter could not see it: each flip looked like
        #     progress toward a freshly chosen target.
        want_ener = t < self.free_ener_until
        if self.goal_c >= 0 and not live[self.goal_c]:
            self.goal_c = -1  # swept it; pick the next
        if self.goal_c < 0:
            if self.cur_rep < 0 or not live[self.cur_rep]:
                self.cur_rep = self._closest(m, v, live)[0]
            if self.cur_rep < 0:
                return v, False
            mine = self.comp == self.comp[self.cur_rep]
            # Corridors carrying a power pellet are left for later, so he
            # never commits to one he is also routing around.
            plain_only = (self.plain > 0) & (self.ener == 0)
            for mask, forced in (
                (plain_only & mine, False),  # this clump first
                (plain_only, False),  # then the nearest other clump
                (self.plain > 0, True),  # only pellet corridors left
                (self.ener > 0, True),  # and finally the pellets themselves
            ):
                c0 = self._closest(m, v, mask)[0]
                if c0 >= 0:
                    self.goal_c, self.goal_power = c0, forced
                    break
        if self.goal_c < 0:
            return v, False
        du = int(m.dist[v, int(m.cu[self.goal_c])])
        dv = int(m.dist[v, int(m.cv[self.goal_c])])
        end = int(m.cv[self.goal_c]) if du <= dv else int(m.cu[self.goal_c])
        return end, (self.goal_power or want_ener)

    def note_progress(self, m: _Maze, tgt: int, went: int, v: int, t: float) -> None:
        """A choice that does not close on the target is a choice he was
        pushed into. A few in a row means standing there is not working."""
        if int(m.dist[went, tgt]) < int(m.dist[v, tgt]):
            self.blocked = 0
            return
        self.blocked += 1
        if self.blocked < _BLOCKED_N:
            return
        self.blocked = 0
        if self.ener.sum() > 0:
            # Either ghosts are in the way or his own detour around the
            # power pellets is. Both are answered by taking one.
            self.free_ener_until = t + 4.0
        else:
            self.contested = tgt
            self.lure_tgt = int(np.argmax(m.dist[tgt]))
            self.lure_until = t + _LURE_TIME


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
        # ... and on around the corner onto any thinned-away spoke, so a
        # turning agent's glow washes over the dark strips too, not only the
        # live lattice.
        for di, from_u in m.dim_adj[v]:
            lo2, hi2 = int(m.dim.ptr[di]), int(m.dim.ptr[di + 1])
            arc = m.dim.arc[lo2:hi2]
            dv = arc if from_u else (float(m.dim.clen[di]) - arc)
            d2 = dv + back
            keep2 = d2 < cut
            if keep2.any():
                rows.append(m.dim.rows[lo2:hi2][keep2])
                ws.append(np.exp(inv * d2[keep2] ** 2))
    return rows, ws


def _portal_transit(
    m: _Maze, c: int, s: float, sigma: float
) -> Tuple[List[np.ndarray], List[np.ndarray]]:
    """An agent crossing a portal, drawn as a hand-off between its two
    mouths: it fades out of the near mouth and into the far one as it goes,
    so the jump between distant junctions reads as travel rather than a
    blink. A portal corridor holds no lights of its own, so without this an
    agent would simply vanish for the crossing."""
    rows: List[np.ndarray] = []
    ws: List[np.ndarray] = []
    for v, weight in ((int(m.cu[c]), 1.0 - s), (int(m.cv[c]), s)):
        if weight <= 1e-3:
            continue
        for r, w in zip(*_vertex_blob(m, v, sigma)):
            rows.append(r)
            ws.append(w * weight)
    return rows, ws


def _dim_field(m: _Maze, hop: np.ndarray) -> np.ndarray:
    """A per-vertex world-distance field (e.g. the death ripple's ``hop``),
    carried onto every dim-spoke light row. A spoke hangs off one live end
    (occasionally two); the distance to a row is the field at that end plus
    the row's arclength from it, and the nearer end wins when there are two."""
    d = m.dim
    out = np.full(len(d.rows), np.inf)
    for di in range(len(d.clen)):
        lo, hi = int(d.ptr[di]), int(d.ptr[di + 1])
        if hi == lo:
            continue
        arc = d.arc[lo:hi]
        u, v = int(d.u[di]), int(d.v[di])
        best = np.full(hi - lo, np.inf)
        if u >= 0:
            best = np.minimum(best, hop[u] + arc)
        if v >= 0:
            best = np.minimum(best, hop[v] + (float(d.clen[di]) - arc))
        out[lo:hi] = best
    return out


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
        self._portal_cache: Dict[
            Tuple[int, int], Tuple[np.ndarray, np.ndarray, np.ndarray]
        ] = {}

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

    def _portal_lights(
        self, key: Tuple[int, int], m: _Maze
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Rows, gaussian weights, and a fixed per-portal breath phase for a
        glow at every portal mouth, so a portal's two ends pulse together.
        All three arrays empty when the board has no portals."""
        if key not in self._portal_cache:
            rows, ws, phase = [], [], []
            for pc in np.flatnonzero(m.is_portal):
                ph = _fnv(int(pc)) % 1000 / 1000.0  # a fixed phase per portal
                for v in (int(m.cu[pc]), int(m.cv[pc])):
                    for r, w in zip(*_vertex_blob(m, v, 0.10 * m.unit)):
                        rows.append(r)
                        ws.append(w)
                        phase.append(np.full(len(r), ph))
            if rows:
                self._portal_cache[key] = (
                    np.concatenate(rows),
                    np.concatenate(ws),
                    np.concatenate(phase),
                )
            else:
                z = np.empty(0, np.int64)
                self._portal_cache[key] = (
                    z,
                    z.astype(np.float64),
                    z.astype(np.float64),
                )
        return self._portal_cache[key]

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
        #
        # On the last life the whole lattice slides from blue toward red —
        # the danger the arcade put in a shrinking row of little Pacs, put
        # here where there is no HUD, only the piece. Lives fall by one at
        # each death (never refilled), so counting deaths up to now gives
        # the count directly; the shift ramps in over two seconds from the
        # death that spent the penultimate life.
        danger = 0.0
        n_dead = sum(1 for td, _ in rd.deaths if td <= tau)
        if n_dead >= _LIVES - 1:  # on the last life, or the game is ending
            t_last = rd.deaths[_LIVES - 2][0]  # the death that spent life two
            danger = float(np.clip((tau - t_last) / 2.0, 0.0, 1.0))
            # Once the last life is gone, the red does not snap off — it drains
            # away over the game-over flourish, in step with the flash fading,
            # so the walls are blue again exactly as attract mode opens.
            if rd.gameovers:
                g = rd.gameovers[0]
                if tau >= g:
                    danger = float(
                        np.clip(1.0 - (tau - g) / _GAMEOVER_FLOURISH, 0.0, 1.0)
                    )
        mh = _MAZE_HC[0] + 79.0 * danger + 9.0 * np.sin(2.0 * np.pi * tau / 41.0)
        breathe = 0.82 + 0.18 * np.sin(2.0 * np.pi * tau / 23.0 + m.vis_c * 0.9)
        add(m.rows, breathe, _MAZE_L, _MAZE_HC[1], mh)
        if len(m.dim.rows):
            # Thinned-away spokes: still part of the physical panel, so
            # they hold a steady half-glow — structure without gameplay.
            add(
                m.dim.rows,
                np.full(len(m.dim.rows), 0.55),
                _MAZE_L * 0.5,
                _MAZE_HC[1] * 0.6,
                mh,
            )
        jrow, jw = self._junction_lights(key, m)
        add(jrow, jw, _JUNC_L, _MAZE_HC[1] * 1.2, mh + 16.0)

        # --- portal mouths --------------------------------------------
        # A teal glow at each gate, the two ends of a portal breathing in
        # lockstep so they read as one thing across the board.
        prow_p, pw_p, pph = self._portal_lights(key, m)
        if len(prow_p):
            breath = 0.6 + 0.4 * np.sin(2.0 * np.pi * (tau / 3.1 + pph))
            add(prow_p, pw_p * breath, 0.5, _PORTAL_HC[1], _PORTAL_HC[0])

        # --- the board ------------------------------------------------
        prow, pw, pid = self._pellet_lights(key, m)
        laid, eaten_at = rd.board(tau)
        age = tau - eaten_at
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
        # Energizers are the board's other hero: at the top of their breath
        # they blow up to full brightness, the swell doing the work the
        # arcade's blink did. Plain dots stay the quiet amber field.
        big = np.where(m.pel_kind == 1, 9.0, 1.0)
        # A freshly laid board blooms in over its first beat instead of every
        # dot snapping on at once — the seam after a clear, softened.
        bloom = float(np.clip((tau - laid) / 0.9, 0.0, 1.0))
        gate = (alive * big)[pid] * bloom
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
                add(r, w * k, _HERO_L, fc_, fh)

        # --- agents ---------------------------------------------------
        step = min(len(rd.pos_c) - 2, max(0, int(tau / _DT)))
        frac = np.clip(tau / _DT - step, 0.0, 1.0)

        def blob(
            c: int, s: float, sigma: float
        ) -> Tuple[List[np.ndarray], List[np.ndarray]]:
            """An agent's glow, transparently handling a portal crossing."""
            if m.is_portal[c]:
                return _portal_transit(m, c, s, sigma)
            return _blob(m, c, s, sigma)

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
                    for r, w in zip(*blob(c, s, sig * (1.0 + 2.4 * k))):
                        add(r, w, 0.95 * (1.0 - k) ** 2, _PAC_C, _PAC_H - 70.0 * k)
                    continue
                # Driven hard into the top of the range — he is the piece's
                # brightest thing. The chomp rides as a size pulse rather
                # than a brightness one: a mouth that opens and shuts, kept
                # off the luminance where a max-bright blob would swallow it.
                chomp = 1.0 + 0.16 * np.sin(2.0 * np.pi * 3.6 * tau)
                boost = 1.12 if mode == 1 else 1.0
                for r, w in zip(*blob(c, s, sig * chomp)):
                    add(r, w, _HERO_L * boost, _PAC_C, _PAC_H)
                continue
            if mode in (3, 4):  # housed, or hidden during a death
                continue
            gi = ai - 1
            if mode == 2:  # eyes
                for r, w in zip(*blob(c, s, 0.115 * m.unit)):
                    add(r, w, 0.45, _EYE_HC[1], _EYE_HC[0])
                continue
            if mode == 1:
                left = _power_left(rd, step)
                blink = 0.0 if left > 2.0 else 0.5 + 0.5 * np.sin(2.0 * np.pi * tau)
                h = _FRIGHT_HC[0]
                ch = _FRIGHT_HC[1] * (1.0 - 0.75 * blink)
                lv = _HERO_L * (0.72 + 0.28 * blink)
            else:
                h, ch = _GHOST_HC[gi]
                lv = _HERO_L
            for r, w in zip(*blob(c, s, sig)):
                add(r, w, lv, ch, h)
            # A short skirt trailing the way it came — kept well under the
            # head so the direction still reads once the head is at ceiling.
            # Skipped mid-portal, where head and skirt would land on the same
            # pair of mouths and only muddy the hand-off.
            ahead = int(rd.pos_c[step + 1, ai]) == c and rd.pos_s[step + 1, ai] >= s
            back = s - 0.21 if ahead else s + 0.21
            if not m.is_portal[c] and 0.0 <= back <= 1.0:
                for r, w in zip(*_blob(m, c, back, 0.125 * m.unit)):
                    add(r, w * 0.25, lv, ch, h)

        # --- death: a shockwave out through the maze -------------------
        for td, dv in rd.deaths:
            k = tau - td
            if not (0.0 <= k < _FLASH_TIME):
                continue
            # White blow-out over the whole board for a beat, then a ring
            # racing outward along the corridors and reddening as it goes.
            hop = m.dist[dv].astype(np.float64) * m.unit
            d = np.minimum(hop[m.vis_u] + m.vis_du, hop[m.vis_v] + m.vis_dv)
            # The ring broadens as it travels — a sharp shock softening into
            # a swell — and a closing envelope drains it to true zero by
            # _FLASH_TIME instead of the old hard cut at ~6% amplitude.
            sigma = (0.62 + 0.62 * k) * m.unit
            ring = np.exp(-(((d - _FLASH_SPEED * m.unit * k) / sigma) ** 2))
            amp = np.exp(-k / 0.62)
            close = min(1.0, (_FLASH_TIME - k) / 0.6)
            # Slow enough that the wire's per-frame slew cap (~0.24 L)
            # can actually reach it before it decays.
            blow = np.exp(-k / 0.30) * min(1.0, k / 0.12)
            w = (ring * amp * 1.35 + blow * 0.75) * close
            hot = w > 2e-3
            if hot.any():
                add(
                    m.rows[hot],
                    w[hot],
                    0.9,
                    0.02 + 0.19 * min(1.0, k / 0.45),
                    30.0,
                )
            # The same wave washing down the thinned-away spokes, so the ring
            # does not stop dead at the border lattice.
            if len(m.dim.rows):
                dd = _dim_field(m, hop)
                dring = np.exp(-(((dd - _FLASH_SPEED * m.unit * k) / sigma) ** 2))
                dw = dring * amp * 1.35 * close
                dhot = dw > 2e-3
                if dhot.any():
                    add(
                        m.dim.rows[dhot],
                        dw[dhot],
                        0.9,
                        0.02 + 0.19 * min(1.0, k / 0.45),
                        30.0,
                    )

        # --- board-cleared flourish -----------------------------------
        for tc in rd.clears:
            k = tau - tc
            if 0.0 <= k < _CLEAR_FLOURISH:
                # A yellow pulse over the whole piece, dim spokes included,
                # closed to zero at the end so it dissolves into the fresh
                # board rather than cutting off.
                pulse = np.exp(-k / 1.1) * (0.5 + 0.5 * np.cos(2.0 * np.pi * k / 0.75))
                pulse *= min(1.0, (_CLEAR_FLOURISH - k) / 0.7)
                add(m.rows, np.full(len(m.rows), pulse), 0.75, _PAC_C, _PAC_H)
                if len(m.dim.rows):
                    add(
                        m.dim.rows,
                        np.full(len(m.dim.rows), pulse * 0.55),
                        0.75,
                        _PAC_C,
                        _PAC_H,
                    )

        # --- game over: the anti-victory ------------------------------
        # A red wash over the whole board once the last life is gone,
        # starting as the final death ripple reaches zero and fading out
        # over the flourish, before the ghosts take the empty board.
        for tg in rd.gameovers:
            k = tau - tg
            if 0.0 <= k < _GAMEOVER_FLOURISH:
                pulse = (
                    (0.35 + 0.65 * np.exp(-k / 1.3))
                    * min(1.0, k / 0.4)
                    * min(1.0, (_GAMEOVER_FLOURISH - k) / 0.7)
                )
                add(m.rows, np.full(len(m.rows), pulse), 0.7, 0.24, 18.0)
                if len(m.dim.rows):
                    add(
                        m.dim.rows,
                        np.full(len(m.dim.rows), pulse * 0.55),
                        0.7,
                        0.24,
                        18.0,
                    )

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
