"""Border chase: paired lights pursuing each other along the borders.

The borders are recovered from the lights array itself: each
(controller, channel) strip is split into straight runs at sharp turns
and long jumps, run endpoints are clustered into vertices, and a seeded
random walk over the resulting graph — a fresh edge choice at every
vertex — is closed back to its start (BFS) so the cycle wraps
seamlessly. Arclength along that closed path is the coordinate: a
chaser is a point at `speed * t` (mod cycle length) with an exponential
tail behind it, and every light knows where on the path it lies.

Each pair is a leader and a pursuer sharing the path: the pursuer hangs
about a border-length behind, surging closer and falling back on a slow
cycle. Both hues wander; the pursuer's wanders fast (and its brightness
shivers), the leader's slowly.

The walk and the per-light path positions are pure functions of the
geometry, cached per geometry fingerprint — memoization, not state:
same (lights, t) in, same colors out, in any call order (spec §9.1.3).
"""

import zlib
from typing import Dict, List, Optional, Tuple

import numpy as np

from luminary.geometry.lights import LightColumns
from luminary.patterns.base import Pattern
from luminary.patterns.util import seeded_random

_TURN_DEG = 28.0  # split a strip where it bends more than this
_GAP_FACTOR = 4.0  # ... or jumps more than this multiple of its spacing
_MIN_RUN = 4  # runs shorter than this merge into a neighbor or drop
_WALK_STEPS = 240  # borders per cycle before closing back to the start


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
        # Corner lights split off as tiny pieces; keep them on the path by
        # merging into the preceding run when spatially contiguous.
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
    """Union-find run endpoints into vertex labels; label of run i's
    ends are out[2i] (first light) and out[2i+1] (last)."""
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


def _closed_walk(labels: np.ndarray, n_runs: int) -> List[Tuple[int, bool]]:
    """Seeded random walk over (vertex, border) graph, closed into a
    cycle: [(run index, reversed?), ...]. Empty if the graph is unusable."""
    incident: Dict[int, List[int]] = {}
    ends = {}
    for e in range(n_runs):
        u, v = int(labels[2 * e]), int(labels[2 * e + 1])
        if u == v:
            continue
        ends[e] = (u, v)
        incident.setdefault(u, []).append(e)
        incident.setdefault(v, []).append(e)
    if not ends:
        return []
    for lst in incident.values():
        lst.sort()

    def far(e: int, frm: int) -> int:
        u, v = ends[e]
        return v if frm == u else u

    start = min(incident)
    node, prev_edge, prev_node = start, -1, -1
    walk: List[Tuple[int, bool]] = []
    for step in range(_WALK_STEPS):
        # Never head back to the node we just left: borders often come in
        # parallel pairs (a strip run on each side of the same pipe), and
        # taking the twin back reads as the chaser doubling back on itself.
        options = [e for e in incident[node] if far(e, node) != prev_node]
        if not options:
            options = [e for e in incident[node] if e != prev_edge]
        if not options:  # true dead end: turn back
            options = incident[node]
        pick = options[
            int(seeded_random(f"border-chase-{step}", 1)[0] * len(options))
            % len(options)
        ]
        walk.append((pick, node != ends[pick][0]))
        node, prev_edge, prev_node = far(pick, node), pick, node

    # Close the cycle: BFS (deterministic, adjacency sorted) back to start.
    # The first hop avoids the node the walk just left — otherwise the
    # stitch itself doubles back (retry unrestricted if that strands us).
    if node != start:
        for banned in (prev_node, -1):
            prev: Dict[int, Tuple[int, int]] = {}
            frontier = [node]
            seen = {node, banned}
            while frontier and start not in seen:
                nxt = []
                for u in frontier:
                    for e in incident[u]:
                        a_, b_ = ends[e]
                        w = b_ if u == a_ else a_
                        if w not in seen:
                            seen.add(w)
                            prev[w] = (u, e)
                            nxt.append(w)
                frontier = nxt
            if start in prev:
                break
        if start not in prev:
            return []  # disconnected from start; give up on this graph
        back: List[Tuple[int, bool]] = []
        w = start
        while w != node:
            u, e = prev[w]
            back.append((e, ends[e][0] != u))
            w = u
        walk.extend(reversed(back))
    return walk


class _Path:
    """A closed path: per-light-visit path arclength, sorted so a
    chaser's tail window is a `searchsorted` slice."""

    def __init__(
        self, rows: np.ndarray, s: np.ndarray, length: float, unit: float, n_runs: int
    ):
        order = np.argsort(s, kind="stable")
        self.rows = rows[order]  # (m,) light row per path visit
        self.s = s[order]  # (m,) arclength of that visit, ascending
        self.length = length  # total cycle length
        self.unit = unit  # median border length (the feature scale)
        self.n_runs = n_runs  # distinct borders in the geometry


def _build_path(a: np.ndarray) -> Optional[_Path]:
    runs, spacing = _build_runs(a)
    if not runs:
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
    labels = _cluster_endpoints(a, runs, tol)
    walk = _closed_walk(labels, len(runs))
    if not walk:
        return None

    alongs = []
    for r in runs:
        xy = a[np.ix_(r, np.array([LightColumns.X, LightColumns.Y], np.intp))]
        seg = np.hypot(*np.diff(xy, axis=0).T)
        alongs.append(np.concatenate([[0.0], np.cumsum(seg)]))

    rows_out, s_out = [], []
    s0 = 0.0
    for e, reverse in walk:
        along = alongs[e]
        total = float(along[-1])
        rows_out.append(runs[e])
        s_out.append(s0 + (total - along if reverse else along))
        s0 += total
    return _Path(np.concatenate(rows_out), np.concatenate(s_out), s0, unit, len(runs))


class BorderChase(Pattern):
    name = "border_chase"
    description = "Paired lights pursuing each other along the borders"

    def __init__(self) -> None:
        self._cache: Dict[Tuple[int, int], Optional[_Path]] = {}

    def _path(self, lights: np.ndarray) -> Optional[_Path]:
        # Content fingerprint over a strided sample of identity + position:
        # cheap per frame, and still purely a function of the array contents.
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
        if key not in self._cache:
            self._cache[key] = _build_path(lights)
        return self._cache[key]

    def render(self, lights: np.ndarray, t: float) -> np.ndarray:
        n = lights.shape[0]
        out = np.zeros((n, 3))

        # Near-black resting field, hue adrift so the dark never sits still.
        bg_hue = (252.0 + 10.0 * np.sin(2.0 * np.pi * t / 47.0)) % 360.0
        out[:, 0] = 0.045
        out[:, 1] = 0.025
        out[:, 2] = bg_hue

        path = self._path(lights)
        if path is None:
            return out

        unit, cycle = path.unit, path.length
        # More pairs on bigger pieces: one per ~90 borders, capped at 4.
        n_pairs = int(np.clip(path.n_runs // 90, 1, 4))
        speed = 6.8 * unit  # per second: several borders a second
        tail = 0.9 * unit

        # Chaser positions and per-chaser color: even entries leaders,
        # odd entries pursuers.
        phases = seeded_random("border-chase-phase", n_pairs)
        bases = 360.0 * seeded_random("border-chase-hue", n_pairs)
        heads, hues, amps = [], [], []
        for j in range(n_pairs):
            phase = float(phases[j])
            base = float(bases[j])
            lead = speed * t + (j / n_pairs) * cycle
            gap = unit * (1.6 + 0.6 * np.sin(2.0 * np.pi * t / 13.0 + phase * 6.28))
            heads += [lead, lead - gap]
            # Leader's hue wanders slowly; the pursuer's fast, and its
            # brightness shivers (gentle ~0.6 Hz sine, no strobe).
            hues += [
                base
                + 16.0 * np.sin(2.0 * np.pi * t / 19.0 + phase)
                + 9.0 * np.sin(2.0 * np.pi * t / 7.3),
                base
                + 150.0
                + 55.0 * np.sin(2.0 * np.pi * t / 2.6 + phase * 3.0)
                + 24.0 * np.sin(2.0 * np.pi * t / 1.1),
            ]
            amps += [1.0, 0.78 + 0.22 * np.sin(2.0 * np.pi * t / 1.7 + phase * 9.0)]

        # Exponential tail behind each head (cut at 3.5 tails) plus a
        # smoothstep rise just ahead of it, so a light attacks over ~0.3 s
        # instead of snapping on. The path is sorted by arclength, so each
        # chaser is a couple of searchsorted slices (split where its window
        # crosses the cycle seam) — never an m x K matrix.
        rise = 0.2 * speed  # ~200 ms attack regardless of speed
        win = min(3.5 * tail, 0.9 * cycle - rise)
        rows_cat, w_cat, a_cat, b_cat = [], [], [], []
        for k, head in enumerate(heads):
            sh = float(np.mod(head, cycle))
            lo, hi = sh - win, sh + rise
            ck, sk = np.cos(np.radians(hues[k])), np.sin(np.radians(hues[k]))
            for shift in (-cycle, 0.0, cycle):
                a0, b0 = max(0.0, lo - shift), min(cycle, hi - shift)
                if a0 >= b0:
                    continue
                i0, i1 = np.searchsorted(path.s, [a0, b0])
                if i0 == i1:
                    continue
                u = (sh - shift) - path.s[i0:i1]  # signed distance behind head
                ramp = np.clip((u + rise) / rise, 0.0, 1.0)
                ramp = ramp * ramp * (3.0 - 2.0 * ramp)
                w = np.exp(-np.maximum(u, 0.0) / tail) * ramp * amps[k]
                rows_cat.append(path.rows[i0:i1])
                w_cat.append(w)
                a_cat.append(w * ck)
                b_cat.append(w * sk)
        if not rows_cat:
            return out
        rows = np.concatenate(rows_cat)
        intensity = np.bincount(rows, weights=np.concatenate(w_cat), minlength=n)
        av = np.bincount(rows, weights=np.concatenate(a_cat), minlength=n)
        bv = np.bincount(rows, weights=np.concatenate(b_cat), minlength=n)
        # Fold in a whisper of the background hue so the blend to dark is smooth.
        av = av + 0.05 * np.cos(np.radians(bg_hue))
        bv = bv + 0.05 * np.sin(np.radians(bg_hue))

        out[:, 0] = 0.045 + 0.72 * (1.0 - np.exp(-1.6 * intensity))
        out[:, 1] = 0.025 + 0.30 * (1.0 - np.exp(-2.2 * intensity))
        out[:, 2] = np.degrees(np.arctan2(bv, av)) % 360.0
        return out
