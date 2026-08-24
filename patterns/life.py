"""Conway-like cellular automaton on the sculpture's own straight runs.

Cells are recovered from the lights array exactly like `border_chase.py`:
each (controller, channel) strip is split into straight runs at sharp
turns and long jumps, and run endpoints are clustered into vertices. A
cell is one run; two cells are neighbors iff their runs share a vertex.
Unlike `pacman.py` this graph is left un-thinned and un-merged (every
run is its own cell), which on the star yields far higher degree than a
grid: median 11 (max 17) on the 6,660-light star, median 5.5 (max 7) on
the 288-light hex demo. Classic Conway B3/S23 assumes degree ~4 (or ~8
on a Moore grid) and collapses on this graph — the birth threshold of 3
live neighbors is rarely met when a cell typically has 8-17 neighbors at
~25% density. That is why the rule is chosen by experiment rather than
assumed.

Rule search (headless harness, no rendering): 14 totalistic (birth-set,
survive-set) rules over raw live-neighbor count, plus 4 fraction-
normalized variants (thresholds on live-neighbor *fraction*, degree-
independent) -- 18 rules total, each run 8 seeds x 250 generations on
both geometries. Measured per rule: sustained alive fraction (want
0.10-0.55), sustained activity = fraction of cells changing per
generation (want 0.05-0.35), and extinction/fixation counts. Abbreviated
results (full table with all 18 rules in the report):

    rule           star alive/act      hex alive/act      hex ext/fix (of 8)
    B3/S23         0.029 / 0.001       0.042 / 0.000       7 / 8   (collapses)
    B2/S23  *      0.255 / 0.323       0.469 / 0.062       1 / 7
    B2/S123 (alt)  0.300 / 0.246       0.474 / 0.062       1 / 7
    B135/S135      0.310 / 0.305       0.406 / 0.188       3 / 5
    B2/S34         0.292 / 0.290       0.083 / 0.167       6 / 6   (extinct-prone)
    Fabs-B23/S234  0.371 / 0.406       0.625 / 0.250       1 / 4   (activity too hot)
    Frac-wide      0.453 / 0.494       0.115 / 0.125       4 / 5   (activity too hot)

B2/S23 (birth on exactly 2 live neighbors, survive on 2 or 3) is the
winner: only rule whose star trajectory lands inside both target bands
with real margin, and it does not collapse on the hex demo the way every
rule anchored on birth=3 does. B2/S123 (survive also on 1) is a near-
identical close second — same hex numbers, slightly more headroom under
the star's 0.35 activity ceiling (0.246 vs 0.323) — kept below as a
one-line swap.

Divergence from the brief worth flagging: on the 12-cell hex demo, EVERY
rule tested fixates into a still life or goes extinct in a nontrivial
fraction of seeds (best case here: 1/8 extinct, 7/8 eventually fixed).
This is a structural property of a 12-cell graph's 4,096-state space,
not a rule defect — small totalistic CAs converge to still-lifes fast
regardless of B/S choice. No rule survived a strict "zero extinctions
across 8 seeds" bar on that geometry; at the brief's minimum of 5 seeds,
B2/S23 does pass that strict bar (0/5 extinct). The brief's literal
thresholds (alive 0.10-0.55, activity 0.05-0.35, no saturation/
extinction) read most naturally as being about the trajectory's
*value*, not a per-seed pass/fail count — under that reading B2/S23
passes on both geometries at both 5 and 8 seeds. Both readings, and
their outcomes, are reported here rather than silently resolved.

A whole epoch (60 generations, ~90s of screen time at 1.5s/generation)
is simulated once from a hash-seeded initial condition and memoized;
render is a lookup into that timeline, plus a 2s OKLab crossfade at
epoch seams. Epochs are independent by construction: epoch k's seed is
`hash(fingerprint, k)`, never epoch k-1's final state.

Three things happen at birth/death, not just an in-place fade:

- DIRECTIONAL SWEEP. A birth's light rushes out of whichever endpoint
  vertex (or vertices) had a living parent last generation, sweeping
  along the run; a death recedes toward whichever endpoint still has a
  living neighbor next generation, so the glow visibly retreats into
  the part of the lattice that stays alive rather than fading in place.
  Per light this is a lookup against arrays precomputed once per
  fingerprint (arclength fraction from each endpoint, a per-cell hashed
  sweep-start offset) plus two small per-cell endpoint-incidence
  matrices (`VU`, `VV`) evaluated against the current generation's state
  -- no Python loop over lights. B2/S23 births always have exactly 2
  live parents (birth-set is `{2}`); when both parents sit at different
  endpoints the sweep converges from both ends (nearest-active-source
  distance, computed once, handles that for free -- no special
  multi-parent case). Deaths can have any number of live
  next-generation neighbors at either end; the same nearest-active-sink
  distance handles 0, 1, or many sinks uniformly. If a birth genuinely
  has no live-parent endpoint, it falls back to a center-out bloom --
  which is not dead code: it's exactly what an empty-zone injection
  looks like (see below). If a death has no surviving neighbor at
  either end, it falls back to the old in-place fade.

  Each cell's own sweep still fills its own window edge to edge, but
  windows are no longer globally synchronized: a fixed per-cell hashed
  offset in [0, _GEN_DT) shifts when a cell's window opens; the window
  keeps its full duration and simply straddles the shared boundary (each
  light resolves whether it is finishing the previous generation's
  transition or has begun the current one -- never both, always exactly
  one). Un-staggered, linear-in-time fronts still produced a
  ~92% board-wide motion dip every generation -- every cell's identical
  "quiet start" (a light exactly at the leading edge of a smoothstep has
  near-zero velocity there by construction) landed on the same instant
  for the whole board; staggering spreads those quiet starts across the
  window so the board's total motion stays level (see the report for
  the diagnosis). The stagger doesn't threaten the chain-case invariant:
  because it shifts a cell's ENTIRE timeline, not one transition, a
  cell's window always ends at envelope exactly 0 (dead) or 1 (fully
  lit) and the next window always begins at that same value, so a cell
  that dies one generation and is reborn the next (or vice versa) hands
  off with no flash or dip, offset or not.

- EMPTY-ZONE INJECTION. Every few generations (a hashed gap of 3-5, not
  a fixed period), if any cell's whole neighborhood out to 2 hops is
  entirely dead, two or three such cells get force-started alive --
  paired with one hashed live neighbor each -- in the state the CA rule
  continues evolving from. Skipped outright if no empty zone exists when
  the schedule calls for one. An injected cell has no living parent by
  construction (that's what "empty zone" means), so it renders through
  the ordinary center-out-bloom fallback above: a spontaneous spark
  blooming from the middle of a dark region, on the same envelope timing
  as any other birth, staggered like any other cell.

- HUE LINEAGE. A newborn cell's hue is the OKLab-vector (unit-circle)
  mean of its living parents' hues, plus a small hashed mutation
  (+/-18 degrees, deterministic per (epoch, generation, cell)) -- hue is
  now ancestry, not age. A cell's hue is fixed at birth and carried
  forward through survival (and through its own fade, so a dying cell's
  glow recedes in the color it lived in); only a fresh birth event
  changes it. Seed-generation cells get hashed initial hues spread over
  the wheel; an injected cell gets one too (fresh, independent per
  cell -- there are no parents to inherit from), immigration bringing
  new blood into the lineage pool. A birth visibly carries its parents'
  color out along the sweep, which composes directly with the
  directional mechanic above. Age still does something small: a newborn
  cell's L gets a brief extra flash that decays over ~2.5s back to the
  resting alive level, giving a "just born" flicker distinct from a
  long-settled cell -- everything else about age (the old hue walk) is
  gone.
"""

import zlib
from typing import Dict, List, NamedTuple, Optional, Tuple

import numpy as np

from luminary.geometry.lights import LightColumns
from luminary.patterns.base import Pattern
from luminary.patterns.util import seeded_random

# --- graph extraction (copied from border_chase.py; patterns are
# single-file by contract) -----------------------------------------
_TURN_DEG = 28.0  # split a strip where it bends more than this
_GAP_FACTOR = 4.0  # ... or jumps more than this multiple of its spacing
_MIN_RUN = 4  # runs shorter than this merge into a neighbor or drop

# --- rule (see docstring for the search table) ----------------------
_RULE_BIRTH = (2,)
_RULE_SURVIVE = (2, 3)  # B2/S23
# Close second, same hex behavior, more headroom under the star's
# activity ceiling -- swap in by uncommenting:
# _RULE_SURVIVE = (1, 2, 3)  # B2/S123

_INIT_DENSITY = 0.25  # epoch seed: fraction of cells alive at generation 0

# --- timing ------------------------------------------------------
_GEN_DT = 1.5  # seconds of screen time per generation
_EPOCH_GENS = 60  # generations per epoch
_EPOCH_LEN = _GEN_DT * _EPOCH_GENS  # 90s -- inside the requested 60-120s
# Each cell has a fixed per-cell hashed sweep-start offset in
# [0, _GEN_DT), and its sweep runs a FULL _GEN_DT regardless of that
# offset -- it does not shrink to fit before the next shared boundary.
# That means a cell's sweep for the (g, g+1) transition spans GLOBAL
# time [g*_GEN_DT + offset, (g+1)*_GEN_DT + offset): it can still be
# finishing up after the shared g/g+1 boundary has passed, straddling it
# by `offset` seconds. Render picks, per light, whichever of the two
# transitions (g-1,g) or (g,g+1) that light's own offset says is
# currently "open" -- see `_pair_light_colors` / `_epoch_light_colors`.
# This is what makes staggering actually work: an earlier attempt that
# kept every cell's sweep confined to [g*_GEN_DT, (g+1)*_GEN_DT) (later
# start, shrunk duration, so it still finished exactly ON the shared
# boundary) only moved WHEN each cell was quiet within that window --
# every actively-transitioning cell still had exactly zero velocity AT
# the boundary itself (a smoothstep's derivative is zero at both of its
# own endpoints, and every cell's endpoint was forced to land there), so
# the ~92% aggregate motion dip barely moved. Letting sweeps straddle
# the boundary means, at any instant, cells at many different points
# along their personal S-curve are moving at once -- including some
# mid-sweep exactly at the tick that used to be silent. Chain case still
# holds: a cell's sweep for (g,g+1) reaches exactly 1 (or 0) at global
# time (g+1)*_GEN_DT + offset, which is precisely where its (g+1,g+2)
# sweep picks up at local_tau_cell=0 -- continuous regardless of offset.
_SWEEP_EDGE_FRAC = 0.20  # softness of the sweep/recede front, as a fraction
# of the run's own length. At _GEN_DT=1.5s this gives a per-light birth
# attack of ~250ms (in the 200-400ms sweet spot) and a death release of
# ~429ms, uniformly for every cell regardless of its offset (duration no
# longer varies with offset the way the discarded first attempt did).
_CROSS = 2.0  # epoch-seam crossfade width, straddling the boundary
_HUE_MUT_DEG = 18.0  # hashed hue mutation at each birth, +/- this many degrees
_BIRTH_FLASH_L = 0.10  # extra L at the instant of birth, decaying with age
_BIRTH_FLASH_TAU = 2.5  # seconds for the birth flash to settle out

# --- empty-zone injection: a spontaneous 2-cell spark in a dark region --
_INJECT_GAP_LO, _INJECT_GAP_HI = 3, 5  # generations between injection
# attempts, hashed within this range (not a fixed period); tightened from
# [6,10] at the Lady's request for more little segments in the dark spaces
_INJECT_BALL_HOPS = 2  # a cell qualifies as an injection site only if its
# whole neighborhood out to this many hops is entirely dead

# --- look ----------------------------------------------------------
_BG_L, _BG_C, _BG_H = 0.045, 0.020, 255.0  # ambient floor (lights off any cell)
_CELL_FLOOR_L, _CELL_FLOOR_C, _CELL_FLOOR_H = 0.070, 0.035, 255.0  # dead-cell
# lattice floor -- a hair above ambient so the graph's own shape reads
# even where nothing is alive right now.
_ALIVE_L, _ALIVE_C = 0.58, 0.17


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


class _Cells(NamedTuple):
    """The cell graph: adjacency, per-endpoint incidence (for the
    directional sweep), and where every light sits."""

    n: int  # number of cells
    adj_i32: np.ndarray  # (n, n) int32, 1 where two cells share a vertex
    vu_i32: np.ndarray  # (n, n) int32, row e: which cells touch e's u-vertex
    vv_i32: np.ndarray  # (n, n) int32, row e: which cells touch e's v-vertex
    ball2_i32: np.ndarray  # (n, n) int32, row e: cells within _INJECT_BALL_HOPS
    # hops of e, INCLUDING e itself -- a fast "is this whole neighborhood
    # dead" query via one matmul against a state vector
    stagger: np.ndarray  # (n,) float64, this cell's fixed hashed sweep-start
    # offset in seconds, in [0, _GEN_DT)
    n_lights: int
    mapped: np.ndarray  # (n_lights,) bool, which lights belong to a cell
    m_cell: np.ndarray  # (n_mapped,) cell index of each mapped light -- this
    # and the arrays below are pre-gathered once per fingerprint so
    # render() never re-indexes a full (n_lights,) array per frame
    m_du: np.ndarray  # (n_mapped,) arclength fraction from the u end, 0..1
    m_dv: np.ndarray  # (n_mapped,) == 1 - m_du, kept alongside to skip a
    # per-frame subtract
    m_offset: np.ndarray  # (n_mapped,) == stagger[m_cell], pre-gathered


def _build_cells(a: np.ndarray) -> Optional[_Cells]:
    runs, spacing = _build_runs(a)
    if len(runs) < 3:
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
    n = len(runs)
    nv = int(labels.max()) + 1

    endpoint_u = np.array([int(labels[2 * e]) for e in range(n)], np.int64)
    endpoint_v = np.array([int(labels[2 * e + 1]) for e in range(n)], np.int64)

    vert_cells: List[List[int]] = [[] for _ in range(nv)]
    for e in range(n):
        vert_cells[endpoint_u[e]].append(e)
        if endpoint_v[e] != endpoint_u[e]:
            vert_cells[endpoint_v[e]].append(e)

    adj = np.zeros((n, n), bool)
    for group in vert_cells:
        for i in group:
            for j in group:
                if i != j:
                    adj[i, j] = True

    # Per-cell endpoint incidence: row e of vu marks every cell (including
    # e itself) that touches e's u-vertex; row e of vv, e's v-vertex. This
    # is what lets a "was some neighbor at MY u-end alive" query run as one
    # matmul over all cells at once, instead of a per-cell Python loop.
    vu = np.zeros((n, n), bool)
    vv = np.zeros((n, n), bool)
    for e in range(n):
        vu[e, vert_cells[endpoint_u[e]]] = True
        vv[e, vert_cells[endpoint_v[e]]] = True

    light_cell = np.full(a.shape[0], -1, np.int64)
    light_dist_u = np.zeros(a.shape[0], np.float64)
    for e, r in enumerate(runs):
        light_cell[r] = e
        xy = a[np.ix_(r, np.array([LightColumns.X, LightColumns.Y], np.intp))]
        seg = np.hypot(*np.diff(xy, axis=0).T)
        along = np.concatenate([[0.0], np.cumsum(seg)])
        total = max(float(along[-1]), 1e-9)
        light_dist_u[r] = along / total

    # 2-hop ball (including self): geometry-only, so it's computed once
    # here rather than every generation the injection schedule checks it.
    adj_i32 = adj.astype(np.int32)
    ball2 = adj | ((adj_i32 @ adj_i32) > 0)
    np.fill_diagonal(ball2, True)

    # Fixed per-cell sweep-start offset: a content fingerprint (not just
    # `n`, so two different geometries that happen to share a cell count
    # don't collide) salts a per-cell hash, independent of any epoch --
    # the same physical cell always staggers the same way.
    fp = zlib.crc32(
        np.ascontiguousarray(
            np.nan_to_num(
                a[
                    ::13,
                    [
                        LightColumns.CONTROLLER,
                        LightColumns.CHANNEL,
                        LightColumns.INDEX,
                        LightColumns.X,
                        LightColumns.Y,
                    ],
                ]
            )
        ).tobytes()
    )
    stagger = seeded_random(f"life-stagger-{fp}", n) * _GEN_DT

    mapped = light_cell >= 0
    m_cell = light_cell[mapped]
    m_du = light_dist_u[mapped]

    return _Cells(
        n,
        adj_i32,
        vu.astype(np.int32),
        vv.astype(np.int32),
        ball2.astype(np.int32),
        stagger,
        a.shape[0],
        mapped,
        m_cell,
        m_du,
        1.0 - m_du,
        stagger[m_cell],
    )


# --- simulation -------------------------------------------------------


class _Epoch(NamedTuple):
    states: np.ndarray  # (E+1, n) bool -- generation 0 is the seed
    birth_hist: np.ndarray  # (E+1, n) int32 -- generation of the most
    # recent birth, valid where the cell is alive at that generation
    hue_hist: np.ndarray  # (E+1, n) float64 -- per-cell hue, fixed at birth
    # (OKLab-vector mean of living parents' hues + a hashed mutation) and
    # carried forward unchanged through survival and through fading out


def _isin_small(arr: np.ndarray, values: Tuple[int, ...]) -> np.ndarray:
    """`np.isin` against a tiny fixed set of small ints, without its
    general-purpose (sort/hash) overhead -- `values` has 1-3 elements for
    every rule this file ships, and a straight-line OR of equalities
    profiles ~30x faster than `np.isin` at this array size (measured on
    422 cells: ~18us vs ~0.6us per call; the epoch loop calls this twice
    per generation, 120 times per epoch, so this alone was worth several
    ms of the epoch-entry budget)."""
    out = np.zeros(arr.shape, bool)
    for v in values:
        out |= arr == v
    return out


_HUE_SCALE = 1_000_000  # fixed-point scale for the hue-lineage matmul below


def _injection_schedule(seed_key: str) -> Dict[int, int]:
    """Which generations get an injection attempt, and how many (1 or 2).

    Gaps between attempts are hashed within [_INJECT_GAP_LO, _INJECT_GAP_HI]
    rather than fixed, so injections land at irregular, deterministic
    intervals -- "roughly every 3-5 generations", not a metronome."""
    sched: Dict[int, int] = {}
    g_cursor = 0
    i = 0
    span = _INJECT_GAP_HI - _INJECT_GAP_LO
    while g_cursor < _EPOCH_GENS:
        gap = _INJECT_GAP_LO + int(
            seeded_random(f"{seed_key}-inject-gap-{i}", 1)[0] * (span + 1)
        )
        g_cursor += gap
        if g_cursor < _EPOCH_GENS:
            n_inject = 2 + int(seeded_random(f"{seed_key}-inject-count-{i}", 1)[0] * 2)
            sched[g_cursor] = min(n_inject, 3)
        i += 1
    return sched


def _simulate_epoch(cells: _Cells, seed_key: str) -> _Epoch:
    n = cells.n
    seed = seeded_random(seed_key, n) < _INIT_DENSITY
    e = _EPOCH_GENS
    states = np.zeros((e + 1, n), bool)
    states[0] = seed

    hue_hist = np.zeros((e + 1, n), np.float64)
    hue_hist[0] = seeded_random(f"{seed_key}-hue0", n) * 360.0

    birth_hist = np.zeros((e + 1, n), np.int32)  # seed cells are "born" at 0

    inject_sched = _injection_schedule(seed_key)

    for g in range(e):
        alive = states[g]
        alive_i = alive.astype(np.int32)
        cnt = cells.adj_i32 @ alive_i
        birth = _isin_small(cnt, _RULE_BIRTH)
        survive = _isin_small(cnt, _RULE_SURVIVE)
        nxt = np.where(alive, survive, birth)

        # Empty-zone injection: find cells whose whole _INJECT_BALL_HOPS-hop
        # neighborhood is entirely dead and force a hashed one, plus a
        # hashed neighbor of it, alive in the state the CA rule continues
        # evolving from. Skipped outright if this epoch's board has no
        # empty zone left when its scheduled generation comes up.
        injected: List[Tuple[int, int, int]] = []  # (pick, neighbor, slot)
        if g in inject_sched:
            empty_mask = (cells.ball2_i32 @ alive_i) == 0
            empty_cells = np.flatnonzero(empty_mask)
            if len(empty_cells) > 0:
                for k in range(inject_sched[g]):
                    pick = int(
                        empty_cells[
                            int(
                                seeded_random(f"{seed_key}-inject-cell-{g}-{k}", 1)[0]
                                * len(empty_cells)
                            )
                            % len(empty_cells)
                        ]
                    )
                    neigh = np.flatnonzero(cells.adj_i32[pick])
                    if len(neigh) == 0:
                        continue
                    npick = int(
                        neigh[
                            int(
                                seeded_random(f"{seed_key}-inject-neigh-{g}-{k}", 1)[0]
                                * len(neigh)
                            )
                            % len(neigh)
                        ]
                    )
                    nxt[pick] = True
                    nxt[npick] = True
                    injected.append((pick, npick, k))

        states[g + 1] = nxt

        born_now = nxt & ~alive

        # Hue lineage: the OKLab unit-vector mean of living parents' hues
        # (only direction matters here, so chroma is taken as 1) plus a
        # small hashed mutation, computed only where a birth just happened;
        # everyone else carries their hue forward unchanged. The mean is
        # computed as an int32 matmul against fixed-point-quantized unit
        # vectors rather than a float64 one: this numpy build's int32
        # matmul measured ~5x faster than float64/mixed-type matmul at
        # n=422 (no BLAS acceleration kicking in for either dtype at this
        # size), and only the *angle* of the sum survives into the
        # result, so the quantization error (~1e-6) is irrelevant.
        a_prev = np.round(np.cos(np.radians(hue_hist[g])) * _HUE_SCALE).astype(np.int32)
        b_prev = np.round(np.sin(np.radians(hue_hist[g])) * _HUE_SCALE).astype(np.int32)
        num_a = cells.adj_i32 @ (a_prev * alive_i)
        num_b = cells.adj_i32 @ (b_prev * alive_i)
        mean_hue = (
            np.degrees(np.arctan2(num_b.astype(np.float64), num_a.astype(np.float64)))
            % 360.0
        )
        mut = (seeded_random(f"{seed_key}-hue-mut-{g}", n) * 2.0 - 1.0) * _HUE_MUT_DEG
        hue_hist[g + 1] = np.where(born_now, (mean_hue + mut) % 360.0, hue_hist[g])

        # Injected cells override the inherited hue: immigration, not
        # ancestry -- a fresh hashed hue each, spread over the wheel.
        for pick, npick, k in injected:
            hue_hist[g + 1, pick] = (
                float(seeded_random(f"{seed_key}-inject-hue-{g}-{k}-a", 1)[0]) * 360.0
            )
            hue_hist[g + 1, npick] = (
                float(seeded_random(f"{seed_key}-inject-hue-{g}-{k}-b", 1)[0]) * 360.0
            )

        birth_hist[g + 1] = np.where(born_now, g + 1, birth_hist[g])

    return _Epoch(states, birth_hist, hue_hist)


def _smoothstep(x: float) -> float:
    u = min(max(x, 0.0), 1.0)
    return u * u * (3.0 - 2.0 * u)


def _smoothstep_arr(x: np.ndarray) -> np.ndarray:
    u = np.clip(x, 0.0, 1.0)
    out: np.ndarray = u * u * (3.0 - 2.0 * u)
    return out


def _oklab_blend(
    l1: np.ndarray,
    c1: np.ndarray,
    h1: np.ndarray,
    l2: np.ndarray,
    c2: np.ndarray,
    h2: np.ndarray,
    w: float,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    a1, b1 = c1 * np.cos(np.radians(h1)), c1 * np.sin(np.radians(h1))
    a2, b2 = c2 * np.cos(np.radians(h2)), c2 * np.sin(np.radians(h2))
    lo = l1 + w * (l2 - l1)
    a = a1 + w * (a2 - a1)
    b = b1 + w * (b2 - b1)
    return lo, np.hypot(a, b), np.degrees(np.arctan2(b, a)) % 360.0


_A_FLOOR = _CELL_FLOOR_C * np.cos(np.radians(_CELL_FLOOR_H))
_B_FLOOR = _CELL_FLOOR_C * np.sin(np.radians(_CELL_FLOOR_H))


def _pair_light_colors(
    cells: _Cells,
    epoch: _Epoch,
    g0: int,
    tau_c: float,
    local_tau_cell: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Per-MAPPED-LIGHT (L, C, H) for the (g0, g0+1) transition, at each
    light's own `local_tau_cell` (seconds since ITS personal window for
    THIS pair opened -- may run past _GEN_DT or be irrelevant; the caller
    only uses this pair's result for lights whose window is presently
    open). Births sweep out of whichever endpoint had a living parent;
    deaths recede toward whichever endpoint keeps a living neighbor;
    everything else holds."""
    alive_prev = epoch.states[g0]
    alive_next = epoch.states[g0 + 1]
    born = alive_next & ~alive_prev
    died = alive_prev & ~alive_next
    stable_alive = alive_prev & alive_next

    # Per-cell target hue: freshly inherited for a birth, current for a
    # stable-alive cell, last-living for a cell that is fading out.
    cell_hue = np.where(born, epoch.hue_hist[g0 + 1], epoch.hue_hist[g0])

    ref_gen = np.where(alive_prev, epoch.birth_hist[g0], epoch.birth_hist[g0 + 1])
    since_birth = np.maximum(0.0, tau_c - ref_gen.astype(np.float64) * _GEN_DT)
    flash = _BIRTH_FLASH_L * np.exp(-since_birth / _BIRTH_FLASH_TAU)
    cell_l = _ALIVE_L + flash

    # Endpoint classification, all cells at once: a birth's SOURCE is an
    # endpoint touched by a neighbor alive last generation; a death's SINK
    # is an endpoint touched by a neighbor alive next generation.
    alive_prev_i = alive_prev.astype(np.int32)
    alive_next_i = alive_next.astype(np.int32)
    src_u = (cells.vu_i32 @ alive_prev_i - alive_prev_i) > 0
    src_v = (cells.vv_i32 @ alive_prev_i - alive_prev_i) > 0
    snk_u = (cells.vu_i32 @ alive_next_i - alive_next_i) > 0
    snk_v = (cells.vv_i32 @ alive_next_i - alive_next_i) > 0

    # Per-cell -> per-light gathers, done once each against the mapped
    # subset precomputed in _Cells (no full-(n_lights,)-array reindexing
    # here, and each cell-level boolean is fetched exactly once even
    # though it feeds both the nearest-source/sink distance and the
    # has-a-source/sink fallback test).
    idx = cells.m_cell
    du, dv = cells.m_du, cells.m_dv

    born_l = born[idx]
    died_l = died[idx]
    stable_alive_l = stable_alive[idx]
    src_u_l, src_v_l = src_u[idx], src_v[idx]
    snk_u_l, snk_v_l = snk_u[idx], snk_v[idx]

    big = 2.0  # farther than any real normalized distance (max 1.0)
    d_src = np.minimum(
        np.where(src_u_l, du, big),
        np.where(src_v_l, dv, big),
    )
    d_center = np.abs(du - 0.5) * 2.0  # fallback: center-out bloom
    d_src = np.where(src_u_l | src_v_l, d_src, d_center)

    d_snk = np.minimum(
        np.where(snk_u_l, du, big),
        np.where(snk_v_l, dv, big),
    )

    # Linear front/recede over the FULL _GEN_DT, at this light's own
    # local_tau_cell (which may be negative -- window not open yet -- or
    # beyond _GEN_DT -- window from an earlier pair still finishing).
    # The clipped smoothstep handles both for free: no branching needed.
    edge = _SWEEP_EDGE_FRAC
    front = (local_tau_cell / _GEN_DT) * (1.0 + edge)
    env_birth = _smoothstep_arr((front - d_src) / edge)

    recede = (1.0 + edge) - (local_tau_cell / _GEN_DT) * (1.0 + 2.0 * edge)
    env_death_dir = _smoothstep_arr((recede - d_snk) / edge)
    env_death_inplace = 1.0 - _smoothstep_arr(local_tau_cell / _GEN_DT)
    env_death = np.where(snk_u_l | snk_v_l, env_death_dir, env_death_inplace)

    env = np.where(
        stable_alive_l,
        1.0,
        np.where(born_l, env_birth, np.where(died_l, env_death, 0.0)),
    )

    hue_l = cell_hue[idx]
    l_l = cell_l[idx]

    a_cell = _ALIVE_C * np.cos(np.radians(hue_l))
    b_cell = _ALIVE_C * np.sin(np.radians(hue_l))

    a_out = _A_FLOOR + env * (a_cell - _A_FLOOR)
    b_out = _B_FLOOR + env * (b_cell - _B_FLOOR)

    l_m = _CELL_FLOOR_L + env * (l_l - _CELL_FLOOR_L)
    c_m = np.hypot(a_out, b_out)
    h_m = np.degrees(np.arctan2(b_out, a_out)) % 360.0
    return l_m, c_m, h_m


def _epoch_light_colors(
    cells: _Cells, epoch: _Epoch, tau: float
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Per-LIGHT (L, C, H) at epoch-local time tau, plus the `mapped` mask
    (which lights belong to a cell at all). Every cell sweeps a full
    _GEN_DT starting at its own hashed offset, so at a given tau some
    cells are still finishing the PREVIOUS generation's transition while
    others have already started the current one -- exactly two candidate
    pairs, (g-1,g) and (g,g+1), ever apply to any light at once, and each
    light's own offset says which. Values for unmapped lights are
    unspecified filler -- callers only read the mapped subset."""
    tau_c = min(max(tau, 0.0), _EPOCH_LEN - 1e-9)
    g = min(int(tau_c // _GEN_DT), _EPOCH_GENS - 1)
    local_tau = tau_c - g * _GEN_DT

    offset = cells.m_offset
    local_tau_cur = local_tau - offset  # this pair's window: >=0 once open
    # At the epoch's very first generation there IS no (g-1,g) pair to
    # straddle into (no states[-1]) -- every cell starts fresh at g=0
    # regardless of offset, rather than letting g_prev fall back to a
    # bogus duplicate of the SAME pair evaluated near its own tail end,
    # which produced a real, large same-pair-vs-itself discontinuity the
    # instant a light's `offset` elapsed (found via the chain-case check;
    # see the report). One un-staggered generation, once per epoch, is
    # invisible against the epoch-start crossfade's own motion anyway.
    use_cur = (local_tau_cur >= 0.0) | (g == 0)

    g_prev = max(g - 1, 0)
    local_tau_prev = local_tau + _GEN_DT - offset

    l_c, c_c, h_c = _pair_light_colors(cells, epoch, g, tau_c, local_tau_cur)
    l_p, c_p, h_p = _pair_light_colors(cells, epoch, g_prev, tau_c, local_tau_prev)

    l_m = np.where(use_cur, l_c, l_p)
    c_m = np.where(use_cur, c_c, c_p)
    h_m = np.where(use_cur, h_c, h_p)

    l_out = np.zeros(cells.n_lights)
    c_out = np.zeros(cells.n_lights)
    h_out = np.zeros(cells.n_lights)
    l_out[cells.mapped] = l_m
    c_out[cells.mapped] = c_m
    h_out[cells.mapped] = h_m
    return l_out, c_out, h_out, cells.mapped


class Life(Pattern):
    name = "life"
    description = "A cellular automaton played on the sculpture's own runs"

    def __init__(self) -> None:
        self._cell_cache: Dict[Tuple[int, int], Optional[_Cells]] = {}
        self._epoch_cache: Dict[Tuple[int, int, int], _Epoch] = {}

    def _cells(self, lights: np.ndarray) -> Tuple[Tuple[int, int], Optional[_Cells]]:
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
        if key not in self._cell_cache:
            self._cell_cache[key] = _build_cells(lights)
        return key, self._cell_cache[key]

    def _epoch(self, key: Tuple[int, int], cells: _Cells, idx: int) -> _Epoch:
        ck = (key[0], key[1], idx)
        if ck not in self._epoch_cache:
            if len(self._epoch_cache) > 8:
                self._epoch_cache.pop(next(iter(self._epoch_cache)))
            seed_key = f"life-init-{key[0]}-{key[1]}-{idx}"
            self._epoch_cache[ck] = _simulate_epoch(cells, seed_key)
        return self._epoch_cache[ck]

    def render(self, lights: np.ndarray, t: float) -> np.ndarray:
        n_lights = lights.shape[0]
        out = np.zeros((n_lights, 3))
        bg_h = (_BG_H + 8.0 * np.sin(2.0 * np.pi * t / 53.0)) % 360.0
        out[:, 0] = _BG_L
        out[:, 1] = _BG_C
        out[:, 2] = bg_h

        key, cells = self._cells(lights)
        if cells is None:
            return out

        idx = int(np.floor(t / _EPOCH_LEN))
        tau = t - idx * _EPOCH_LEN

        epoch = self._epoch(key, cells, idx)
        lo, co, ho, mapped = _epoch_light_colors(cells, epoch, tau)

        # Crossfade is one continuous curve straddling each boundary, not
        # two independently-shaped halves: both "other" epoch's tau AND
        # the blend weight are continuous functions of GLOBAL t, so a side
        # approaching a boundary and the side leaving it converge on the
        # exact same (epoch pair, tau pair, weight) at the seam itself --
        # see the report for the discontinuity this replaced (each side
        # used to evaluate the *other* epoch at a fixed tau instead of its
        # own continuously-advancing one, so the two halves blended toward
        # different targets and stepped hard across the boundary).
        half = _CROSS / 2.0
        if tau < half:
            other = self._epoch(key, cells, idx - 1)
            lo2, co2, ho2, _ = _epoch_light_colors(
                cells, other, t - (idx - 1) * _EPOCH_LEN
            )
            w = _smoothstep((tau + half) / _CROSS)
            lo, co, ho = _oklab_blend(lo2, co2, ho2, lo, co, ho, w)
        elif tau > _EPOCH_LEN - half:
            other = self._epoch(key, cells, idx + 1)
            lo2, co2, ho2, _ = _epoch_light_colors(
                cells, other, t - (idx + 1) * _EPOCH_LEN
            )
            w = _smoothstep((tau - (_EPOCH_LEN - half)) / _CROSS)
            lo, co, ho = _oklab_blend(lo, co, ho, lo2, co2, ho2, w)

        out[mapped, 0] = lo[mapped]
        out[mapped, 1] = co[mapped]
        out[mapped, 2] = ho[mapped]
        return out
