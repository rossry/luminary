# luminary
interactive cellular automata art

## quickstart demo

```
~/luminary $ make && bin/a.out
```

launches an ncurses-based simulator.

The full demo routine takes ~3.5 minutes, demonstrating a transition between patterns, a decay into a "hibernation" state, and a transition back to the same active pattern. Pressure-switch triggers for "spotlight" effects are simulated randomly across the grid. Pressure-switch triggers for the purpose of triggering a transition effect are injected at the bottom center.

## adapting for deployment (short term)

### addressing CRs

The comments tagged "CR rrheingans-yoo for ntarleton" (currently 4 in `main.c`; 3 in `display.c`) describe exactly what need to be addressed to drive a prototype floor with an interactive demo pattern.

* The CRs in `main.c` address interactivity integration.
* The CRs in `display.c` address integration with the grid lights.

### triaging interactivity

If triage requires abandoning pressure switches for this deployment, then a non-interactive shifting-rainbows pattern can be enabled by replacing the whole `switch (control_directive_0_next[xy])` block with the logic from the `case PATTERN_FULL_RAINBOW` branch, _i.e._:

```
display_color(xy, rainbow_0_next[xy]);
```

### varying parameters

Here are some parameters (set in `constants.h`) that would be useful to test on a real floor:

* `PRESSURE_RADIUS_TICKS` (controls the radius of the circle produced by a single point of pressure, in 17ths of a cell)
* `PRESSURE_DELAY_EPOCHS` (how long a cell should "remember" pressure after it's released -- note that it will take longer still for the produced circle to decay away)
* `BASE_HZ` (how many frames/sec the main rainbow patterns are driven at)
* `WILDFIRE_SPEEDUP` (how many times faster the "wildfire" patterns, like transitions and waves, are driven at)

## roadmap

### artistic

* pattern variants that emphasize only a subset of colors (or single color) at a time
* effects for driving sphere lights in synchrony with waves-based effects/transitions
* additional "building blocks" -- [Brian's Brain](https://en.wikipedia.org/wiki/Brian%27s_Brain), competing [turmites](https://en.wikipedia.org/wiki/Turmite)...
* additional interactivity rules to let interacters cause more complex effects than centered spotlights

### logistical

* determine a preliminary day-by-day schedule of display schemes
* form a plan for pairing display schemes with music

### technical

* `display`-based interface for controlling sphere lights
* control interface (extending `in_chr`-based input already implemented)
* stochastic variation in certain parameters over time (for unsupervised mode)
