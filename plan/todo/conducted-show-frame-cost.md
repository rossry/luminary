# Conducted shows exceed a 30 fps frame budget during crossfades

Found while giving the audio-matched shows internal arcs (2026-08-28).
**Pre-existing on `main`**, not introduced by that work — recorded here
because nothing else measures it and the shows are headed for a
deployment.

## The measurement

`Conductor.render` costs one child render outside a fade window and
**two inside one** (spec-documented, `test_one_render_outside_fades_two_inside`).
Two expensive scenes therefore land on the same frame at every seam.
Worst crossfade per show, 6,660 lights (4A-37), this box:

| show | before either change | now (both merged) | worst seam is |
|---|---|---|---|
| `koln` | 31.8 ms | **31.9 ms** | `coming-to-rest` (NoiseGlow + Motif) |
| `apollo` | 34.5 ms | **32.9 ms** | `matta` (AuroraVeils) |
| `promises` | 54.1 ms | **50.2 ms** | `answer` (AuroraVeils into AuroraVeils) |
| `nocturne` | 42–46 ms | **41.7 ms** | `deep-sea` (NoiseGlow + Starfield) |

Repeat runs vary by a few ms; the *ranking* of seams is stable, the
individual figures less so. Governor `performance`, 6,660 lights.

A 30 fps frame is 33.3 ms. Steady-state scenes are fine — the same
shows sit at 10–16 ms median — so this is a seam-only stall lasting as
long as the fade (10–30 s), during which the engine cannot hold
cadence.

`patterns/README.md` quotes a ~5 ms per-frame budget (spec §17.3). No
conducted show has met it for some time; the primitives that dominate
are the ones with per-entity pool matrices (`Candles` evaluates an
`n_lights x count` exp) and `NoiseGlow` (domain-warped fbm, three
octaves).

## What has already been done

**Option 3 is done** (PR #43). `Candles` no longer evaluates its whole
`n_lights x count` matrix: the light–flame pairs that carry any light
are found once, cached on a content fingerprint, and the render walks a
flat pair list. `Candles()` went 38.0 -> 3.7 ms, and nocturne's two
candle seams went from 33–46 ms to under 23 — they are no longer
anywhere near the worst thing in that show.

It did not solve the problem, and was never going to: `promises` has no
candles in it at all. What it did was remove one cause completely.

Two local mitigations in `koln` also stand: the ballad's candle `count`
is 52 rather than 72, and the house-lights floor under Part IIc's stars
runs at `octaves=2`.

## Where that leaves it

`koln` (31.9 ms) and `apollo` (32.9 ms) now fit inside a 30 fps frame,
`apollo` only barely. `promises` (50.2 ms) and `nocturne` (41.7 ms) do
not, and both are bounded by `AuroraVeils` and `NoiseGlow` seams that no
amount of candle work touches.

The remaining options are 1, 2 and 4 below. **Option 1 is the only one
that covers `promises`**, because the problem there is two expensive
scenes of the same kind blended together, not one primitive being
wasteful.

## Options, roughly in order of appeal

1. **Cache the outgoing movement across a fade.** During a crossfade the
   previous movement is re-rendered at a `t` it will never be asked for
   again. It cannot be skipped (the blend needs it), but a conductor
   could render the *outgoing* side at a reduced rate — every other
   frame, holding the previous result — since it is being multiplied by
   a weight heading to zero. Halves the seam cost; needs care to stay
   inside the statelessness contract (a cache keyed by `(id, t)` is
   fine; a cache that depends on call order is not).
2. **Budget-aware fades.** Let a `Movement` declare that its fade is
   cheap (both sides light) or expensive, and keep expensive-to-
   expensive seams short. Manual, but it is what the `koln` ballad now
   does by hand.
3. ~~**Make `Candles` cheaper.**~~ Done, PR #43 — see above. The
   approach (neighbour list memoized on a content fingerprint, like
   `SmallPlanet`'s statics) transfers directly to any other primitive
   with per-entity pools, should one turn up.
4. **Accept it and drop frames at seams.** The playout queue on the
   board absorbs a few late frames; a 10–30 s stretch at ~20 fps is
   not nothing, but it is a crossfade, and it is where the eye is
   least likely to catch it.

## What is NOT known

None of this has been measured on the deployment box under load, only
on the pattern render in isolation — no codec, no serial, no viewers.
The real question is what `luminary play` does at a seam with six
boards attached, and that has not been run. Until it has, even the two
shows that now fit a 30 fps frame fit it *with nothing else running*,
which is not the condition they will be played in.
