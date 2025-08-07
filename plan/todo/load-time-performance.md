# Load-Time Performance Optimizations

## Facet Beam Generation

### Per-Edge Constant Sharing
- `facet._generate_beams()` can be optimized by sharing variables that stay constant per-edge
- Current implementation recalculates edge vectors, beam width vectors, and geometric references for each beam
- These should be computed once per edge and reused

### Stride Arithmetic for Forward Extents
- Forward extent segments currently use full re-computation for each beam
- Can be optimized using stride arithmetic since beam positions follow regular intervals
- Calculate base positions and increments once, then use arithmetic progression

### Lazy Beam Generation
- Beams are currently generated at facet init time
- Could implement lazy generation to defer computation until beams are actually accessed
- Would improve initial load time for applications that don't always need beam subdivision
- Trade-off: complexity vs. load-time performance