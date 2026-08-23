# Pac-Man: smarter Pac, honest endgame, portals, maxed heroes (2026-08-23)

`patterns/pacman.py`. The Lady wanted Pac to stop looking dumb (leaving crumbs,
flinching at guarded food, chasing frightened ghosts into the desert), the
super-pac endgame cheat gone, the dynamic range actually used, the death and
victory seams to stop cutting hard, more fruit — and asked whether portals
could shorten the star's long corners. Planned as Witch, built as Doll.

## The endgame cheat, and why free-play windows replace it

The old round *had* to end in victory before the window closed, because
`round_len` is one constant and `floor(t / round_len)` is what makes an
arbitrary `t` O(1). It enforced that with `lag`: up to 2.2x Pac speed and a
35% ghost slowdown. That read as rigged, and it was a latent bug too — at 2.2x
his per-tick stride (0.22 x unit) outran his own eat diameter (0.20), so he
skipped dots mid-corridor. The cheat manufactured the very remains it existed
to clean up.

Resolution: keep the window fixed, stop fixing the *outcome*. Lives are real
(5, not 3 — see below); a cleared board re-dots a faster level; five spent
lives trigger a red anti-victory flash and the ghosts tour the empty board
(attract screen) until the window fades. O(1) indexing is preserved because
pricing an arbitrary `t` under variable round lengths would mean summing the
simulated outcomes of every game before it — unpayable. Convergence pressure
moved from Pac to the ghosts: Cruise Elroy (Blinky speeds up as dots deplete),
plus a capped 1.25x Pac catch-up with no ghost tiring.

## Portals — placed topologically, exact distances cheap

The build is a partial shell (planar topology even folded), so portals are
deliberate shortcuts, not fold-seam healing. Placement: join the two most
distant junctions, worst pair first, up to 4x, excluding existing mouths so
gates spread. They carry no dots and take real time to cross; hunting ghosts
labour through them at 0.55x — the arcade tunnel rule, which is Pac's escape
valve and a structural answer to region-camping.

Adding one unit edge means recomputing all-pairs distance. A full BFS refresh
per portal cost 236 ms of build (over the 150 ms budget). Replaced with the
incremental identity `new = min(old, old[:,u]+1+old[v,:], old[:,v]+1+old[u,:])`
— exact for unweighted graphs (a shortest path crosses one new edge at most
once), O(nv^2) vectorized. Verified bit-identical to full BFS on all four
geometries; build fell to 80 ms, below even the pre-portal number.

## Divergences from the plan, and what they taught

- **The plan predicted portals would shrink the dry run.** They can't: the dry
  run is a *covering* walk and Pac must still traverse every dotted corridor.
  Portals shorten escape-and-re-approach, which only pays with ghosts present.
  The win landed there — deaths dropped even before the AI work.
- **PacBrain deadlocked the unopposed sweep.** Targeting the *near* end of the
  nearest dotted corridor collapsed the tiebreak the moment he reached its
  mouth; he wandered off with it still full. Fix: target the *far* end, so
  "arrived" and "swept it" are the same event.
- **The blocked-counter could not see the oscillation.** Re-deciding "nearest
  dotted corridor" every junction let two corridors swap places as nearest and
  he rocked between them, each flip looking like progress toward a fresh
  target. Fix: commit to a corridor until it is empty (corridor-level
  hysteresis), not the plan's component-level `cur_comp`, which is inert while
  the whole board is one component.
- **A house-bound ghost emerges un-frightened mid-energizer** (correct arcade
  behaviour — the Lady caught this when a first fix wrongly made it emerge
  blue). The real defect was that Pac dropped his *entire* safety filter while
  powered, so that ghost walked through him. Fix: the safety filter (hunters
  only) runs while powered too — free during a clean fright, load-bearing
  against the house case.

## What held, measured (4A-37, harness in scratchpad)

Reversals/min 16 -> 7-13, desert-chasing gone (only catchable prey pursued).
Energizers behave as asked (12 rounds, 60 eats): saved, not grabbed — median
96% of the board is eaten before one goes, 0% eaten early; and taken under
pressure the rest of the time (17% with a hunter within 3 hops, 33% within 5).
Fruit 8.4/round (up from 6 gates). The lure — pulling campers off the last
dots — fires ~6x/round, all in the endgame after the energizers are spent;
not the rare event the plan guessed, but doing its job on a ghost-dense board.
But the load-bearing bet — that a smarter Pac would clear a 476-pellet board
within 3 lives — **failed**:
clearing needs ~115 s of sweeping (traversing every edge; dot density cannot
change that) and he loses lives faster than that. The Lady's call: lives to 5.
Result over 12 rounds: 4 clears, attract tail 16% of the window on 4A-37, 26%
on 4A-35. He loses most games, which is by design ("it's okay if Pac loses").
4A-35 (the likely install geometry) has the longer tail — the open follow-up.

## Render

Heroes driven to the wire ceiling: Pac/ghosts/fruit/energizer-at-peak now peak
0.96-0.975 (were 0.81-0.95), walls and plain dots untouched. Chroma is
ratio-invariant to the level scaling, so colours read at their intrinsic hue
at blob centre (Blinky H=28 C=0.19, verified) — brighter, not washed. Pac's
chomp moved from luminance to size so it survives saturation. Death ripple
widens as it travels and closes to true zero (was a hard cut at ~6%); it and
the agent corner-spill now wash down the thinned-away spokes too (new `_Dim`
carries their arclength + a live endpoint). Victory flourish and re-dot bloom
in/out; game-over is a red board-wide flash timed to start as the last ripple
ends. Last life slides the whole lattice blue -> red (266 -> 345 hop over 2 s).

Render steady-state 0.72 ms/frame; determinism bit-identical across
PYTHONHASHSEED (spec §9.1.3).

## Follow-up: portals, lives, and a tuning null-result (same day)

The Lady iterated on the two visible/balance choices after the first commit.

**Portals: one, at the arm tips.** Four gates read busy and lopsided on the
star's uneven arms; settled on a single portal joining the two most distant
tips. Getting "tip" right took three tries, each a real lesson:
- degree <= 3 alone: a strip split at a seam leaves a degree-2 vertex in the
  *middle* of a straight run — picked as a gate, looks arbitrary.
- largest-angular-gap >= 200: excludes straight pass-throughs, but a *sharp
  bend partway along an arm* also has a big gap, so it still chose non-tips
  (a vertex at 56% of max radius).
- what works: a tip is a **local maximum of distance-from-centroid** — farther
  out than every neighbour, i.e. the actual end of an arm. Kept the degree cap
  as a floor. `_portal_eligible`.

**Lives, not slower ghosts, tune the win rate.** Lives sweep on 4A-35 (1
portal, 50 seeds): 5 -> 0.44 clears / 50% game-over / 22s attract; 7 -> 0.64 /
12% / 2s; 8 -> 0.66 / 2% / 1s. Monotonic and fair-reading, unlike ghost-speed
(which was weak and non-monotonic: 0.82->0.74 helped, 0.70 hurt). Set to 7:
wins most rounds, still loses ~1 in 8 so the last-life red and anti-victory
flash still show, attract tail down to a couple of seconds.

**The brain constants do not move the win rate — proven, not assumed.** Built
a coordinate-descent tuner (`scratchpad/pac_tune.py`, 24-core multiprocessing;
Cython declined — parallelism is 24x, Cython ~2x, and the work is embarrassingly
parallel across sim evaluations). It found a config scoring +0.02 clears on its
40-seed training set that **reversed to -0.075 on 80 held-out seeds** — pure
overfitting — and degraded the other boards. Not applied. Defaults are best
out-of-sample. Pac already plays near-optimally within the brain; clearing 476
pellets means walking every edge against four ghosts, which is ~0.5 clears/round
regardless of the knobs. Promoted three hardcoded magics (`_ENER_PENALTY`,
`_FREE_ENER_TIME`, `_PREY_REACH`) to constants along the way so the tuner could
reach them; kept at their original values.

## Sharp edge for the next session

`tests/test_golden.py::test_js_decoder_conformance` needs node >= ~22.12:
`decoder.js` is ESM by extension with no `package.json`, so older node (v20 on
PATH here) rejects `export`. Passes under v24. Not a wire regression — the JS
decoder is bit-exact; the harness just depends on an unpinned node. Left for a
separate PR (a repo-wide `package.json` touches the three-decoder invariant's
harness and wants its own review).
