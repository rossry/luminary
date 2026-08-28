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

| show | main | after the arcs work |
|---|---|---|
| `koln` | 46.8 ms | 40.0 ms |
| `apollo` | 32.8 ms | 31.4 ms |
| `promises` | 53.2 ms | 51.9 ms |
| `nocturne` | ~42–47 ms | unchanged (not edited) |

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

Nothing structural. Two local mitigations in `koln`, both cheap and
both visible in the table above: the ballad's candle `count` is 52
rather than 72 (cost is linear in `count`, and its three scenes are the
one place in the repertoire where two `Candles` render at once), and
the house-lights floor under Part IIc's stars runs at `octaves=2`.

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
3. **Make `Candles` cheaper.** The `(n, count)` pool matrix is the
   single largest term in the repertoire. Candles beyond ~25° of a
   light contribute nothing; a neighbour list computed once per
   geometry (memoized on a content fingerprint, like `SmallPlanet`'s
   statics) would turn it into a sparse gather.
4. **Accept it and drop frames at seams.** The playout queue on the
   board absorbs a few late frames; a 10–30 s stretch at ~20 fps is
   not nothing, but it is a crossfade, and it is where the eye is
   least likely to catch it.

## What is NOT known

None of this has been measured on the deployment box under load, only
on the pattern render in isolation — no codec, no serial, no viewers.
The real question is what `luminary play` does at a seam with six
boards attached, and that has not been run.
