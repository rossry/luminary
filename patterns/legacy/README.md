# Legacy patterns (not loaded)

These 2.0 patterns keep mutable state across frames (physics simulations,
persistent RNG), which violates the 2.1 stateless-rendering contract
(spec §1.3.4 / §9.1.3): a frame must be recomputable from `t` alone, because
the wire codec recomputes ground truth per frame and keyframes must be
deterministic.

They are parked here — out of the registry's scan path — until someone
reworks each one into a pure function of `t` (see `plasma_storm.py` at the
repo `patterns/` root for a worked example of that conversion).

`claude_fireflies.py` and `lifely_game.py` (parked 2026-08) additionally
predate 2.1 entirely — they target the old `LuminaryPattern.evaluate`
API — and keep mutable state (a firefly swarm updated in place; a cellular
automaton grid), so each needs both the API port *and* the stateless
redesign. Their eight stateless siblings from the same batch were ported
and live at the `patterns/` root.
