# Legacy mypy debt (2.0 modules)

The 2.1 modules (`geometry/{coords,lights,scaffold,capture,pentagon}`,
`color/`, `comms/`, `engine/`, `patterns/{base,registry,util}`, `render/`,
`server/`, `drivers/`, `cli.py`) pass strict mypy:

    python -m mypy <those paths> --explicit-package-bases --follow-imports=silent

The pre-2.1 modules do not (they predate mypy being runnable in this repo —
the old `colour` dependency was never installed here): `geometry/{point,
primitives,triangle,facet,beam,net}.py`, `config/schema.py`,
`writers/svg/*`, `validation/validate.py`, `main.py`. Known error classes:
missing annotations, implicit-Optional defaults, `get_svg` override
signature drift in `beam.py`, tuple-vs-list literals in `facet.py`.

Cleanup is mechanical but noisy; do it as its own branch so it doesn't
pollute feature diffs. Until then, type-check new code with
`--follow-imports=silent` as above.
