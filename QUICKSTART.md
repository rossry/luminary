# Quick start

Patterns playing in three commands:

```bash
git clone https://github.com/rossry/luminary && cd luminary
pip install -r requirements.txt
python -m luminary.cli serve --port 8080 --seed-demo
```

Open <http://localhost:8080>, pick a geometry (`pentagon-4A-33` is the
production sphere) and a pattern (`aurora`, `tidepool`, `spiral`, …),
press Play. Everything you see went through the real wire codec — the
header's fps and bytes/light·frame readouts are live.

The hardware-free **mapping tutorial** is already mounted at
<http://localhost:8080/demo/mapping>: map a scrambled six-board sphere
with the arrow keys or WASD; `p` or space confirms.

## Mapping a real deployment

At the base station, with the boards on USB:

```bash
python -m luminary.cli map               # probe boards; TUI + mirror page
python -m luminary.cli map --web         # drive it from the browser instead
python -m luminary.cli map --continue    # resume a half-done mapping
```

Stage A locks each planned board to a controller (the matching cluster
breathes its color); stage B records channel, density, and winding per
panel (one enter each). Every step saves one YAML per board under
`store/mapping/`; when the last panel is recorded the sphere plays the
completion finale and settles into the show. The full design and visual
language: [`plan/mapping/DESCRIPTION.md`](plan/mapping/DESCRIPTION.md).

More: [`README.md`](README.md) (install details, API, firmware),
[`patterns/README.md`](patterns/README.md) (writing your own patterns).
