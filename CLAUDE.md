# Claude Code Instructions

Luminary 2.1 drives an LED art installation: lights geometries + stateless
patterns + a bit-efficient wire codec, streamed identically to Scorpio
hardware and to the browser demo. Humans start at `README.md` (install +
quick start). Agents start here.

## Documentation map — read before working

| Document | What it is |
|---|---|
| `plan/spec/luminary-2.1-spec.md` | **The authoritative design.** Paragraph-numbered; code references it as `spec §…`. §3 is the keep/refactor/rewrite ledger for 2.0 components; §19 records the design-review resolutions. |
| `plan/spec/implementation-notes.md` | **How the design is realized here.** Component map (module → spec §), the invariants you must not break, the wire-protocol conformance workflow, verified performance numbers, deferred work, sharp edges. Read this before touching engine/codec/geometry code. |
| `README.md` | Human-facing overview, install, quick start, API table, pattern how-to. |
| `plan/guidelines/collaboration.md` | **Especially important with human developers**: plan first, get approval, draft before writing, test, document in the same commit. |
| `plan/guidelines/code-quality.md` | Mandatory tooling: `black` immediately after writing; `pytest` + `mypy` together on every change. |
| `plan/guidelines/developer.md`, `plan/guidelines/version-control.md` | Graphite stacked-branch workflow and naming. |
| `plan/todo/` | Known debt (notably `legacy-mypy-debt.md`) and deferred optimizations. |
| `firmware/scorpio/README.md` | Firmware build/flash and host-side conformance tests. |

## Non-negotiable invariants (details in implementation-notes §2)

- **One engine**: all consumers get wire bytes from `Engine.frame(t)`; never
  add a parallel render/encode path.
- **Patterns are stateless, vectorized functions** of `(lights, t)` — no
  per-frame Python loops over lights, no mutable pattern state.
- **The wire protocol has three bit-identical decoders** (Python reference,
  JS, C++ firmware). Any protocol change follows the golden-vector workflow
  in `plan/spec/implementation-notes.md` §3 — spec first, all three decoders,
  regenerate `firmware/golden/`, `pytest tests/test_golden.py` green.
- **Canonical light order** is `(controller, channel, index)`; codec,
  SESSION maps, and firmware addressing all assume it.

## Quality gates

```bash
python -m pytest        # full suite incl. golden-vector + JS + C++ conformance
black <files you wrote>
python -m mypy <2.1 module paths> --explicit-package-bases --follow-imports=silent
```

The exact mypy invocation (and why `--follow-imports=silent`) is in
`plan/spec/implementation-notes.md` §4. Keep documentation in `plan/` and
`README.md` synchronized with code changes, in the same commit
(`plan/guidelines/collaboration.md` §7).
