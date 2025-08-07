# Luminary Patterns: Animated Geometric Patterns via SDF

## Overview

The Luminary Patterns feature introduces an abstract pattern system that uses Signed Distance Functions (SDFs) to create animated geometric patterns. These patterns control OKLCH color values over time, creating dynamic lighting effects that can be cast onto pentagon Net geometries.

## Core Concept

### Pattern-Based Color Control
- **LuminaryPattern**: Abstract base class for implementing animated patterns
- **SDF-Driven**: Patterns use signed distance functions to compute OKLCH (l, c, h) values
- **Time-Based Animation**: Patterns evolve over time parameter `t`
- **Beam-Level Control**: Each Beam in a Net gets individual color values based on its spatial position

### Beam Basis Points
Each Beam has a **basis point** - a representative 2D coordinate used for SDF evaluation:
- Located at the geometric center of the beam polygon
- Provides consistent spatial reference for pattern calculations
- Enables smooth color transitions across adjacent beams

## Data Architecture

### Numpy Array Structure
All Beams in a Net are represented as a single numpy array with columns:

**Spatial Coordinates:**
- `x`, `y`: Basis point coordinates in 2D space
- `r`, `theta`: Polar coordinates relative to pattern origin

**Geometric Hierarchy:**
- `face`: Triangle index (0-based)
- `facet`: Facet letter within triangle (A, B, C or D, E, F) 
- `edge`: Edge index within facet (0-3: MAJOR_STARBOARD, MINOR_STARBOARD, MINOR_PORT, MAJOR_PORT)
- `position_index`: Beam position within edge (0-based)

**Output Protocol Preparation:**
- `node`: Hardware node ID (0-63, derived from geometric position)
- `strip`: LED strip ID within node (0-7)
- `strip_idx`: LED index within strip (0-511)

The node/strip/strip_idx columns prepare for production deployment where:
- Output is sharded by hardware node
- Data within each node is sorted by strip, then strip_idx
- Enables efficient streaming to distributed LED hardware

### SDF Pattern Evaluation
Patterns implement SDFs that operate on the entire beam array using **vectorized numpy operations only**:

```python
def evaluate_sdf(self, beam_array: np.ndarray, t: float) -> np.ndarray:
    """
    Evaluate pattern at time t for all beams.
    
    Args:
        beam_array: Array with columns [node, strip, strip_idx, x, y, r, theta, face, facet, edge, position_index]
        t: Time parameter for animation
    
    Returns:
        Array with columns [l, c, h] representing OKLCH values for each beam
    """
```

## Pattern Development

### Pattern Storage
All patterns live in `luminary/patterns/` as individual Python files:
- `luminary/patterns/ripple.py`
- `luminary/patterns/spiral.py`
- `luminary/patterns/wave.py`
- `luminary/patterns/breathing.py`

### Example Patterns
The system provides reference implementations for developers:
1. **Ripple**: Expanding circular waves from center
2. **Spiral**: Rotating geometric forms with color rotation
3. **Wave**: Linear traveling waves across the Net
4. **Breathing**: Gentle pulsing luminance variations

### Pattern Discovery
Patterns are automatically discovered by filename in `luminary/patterns/`:
- Each `.py` file should contain a class inheriting from `LuminaryPattern`
- The class name should match the filename (e.g., `RipplePattern` in `ripple.py`)
- Patterns are invoked by filename: `main.py pattern sample ripple`

## Command Line Interface

### New `pattern` Subcommand
```bash
# Pattern operations
main.py pattern sample <pattern_name> [-c config.json] [-t time] [-o output.svg]
main.py pattern preview <pattern_name> [-c config.json] [--port 8080]
main.py pattern run <pattern_name> [-c config.json]  # Future: hardware output

# Interactive pattern selection (when pattern_name omitted)
main.py pattern sample  # Shows multiple choice menu
main.py pattern preview  # Shows multiple choice menu
```

### Subcommand Details

**`sample`**: Generate static SVG with pattern applied
- **Required**: Pattern name (or interactive selection)
- **Optional**: `-t <time>` (default: 0.0), `-c <config>`, `-o <output>`
- **Output**: `config_name.<pattern>.svg` (e.g., `5A-35.ripple.svg`)

**`preview`**: Run WebSocket server for real-time animation
- **Required**: Pattern name (or interactive selection)
- **Optional**: `-c <config>`, `--port <port>` (default: 8080)
- **Output**: WebSocket server + HTML page for animation viewing

**`run`**: Stream to hardware (not implemented in initial release)
- **Required**: Pattern name (or interactive selection)
- **Optional**: `-c <config>`, hardware-specific flags
- **Output**: Direct hardware control (future implementation)

### Interactive Pattern Selection
When no pattern name is provided, show multiple-choice menu:
```
Available patterns:
[1] ripple - Expanding circular waves
[2] spiral - Rotating geometric forms  
[3] wave - Linear traveling waves
[4] breathing - Gentle pulsing variations

Select pattern (1-4): 
```

## Mathematical Foundation

### Signed Distance Functions
SDFs return the signed distance from a point to a geometric boundary:
- **Negative values**: Inside the shape
- **Zero**: On the boundary
- **Positive values**: Outside the shape

### OKLCH Color Space
- **L (Lightness)**: 0.0 (black) to 1.0 (white)
- **C (Chroma)**: 0.0 (gray) to ~0.4 (saturated)
- **H (Hue)**: 0° to 360° (color wheel position)

### Pattern-to-Color Mapping
SDFs can control any combination of L, C, H values:
- **Distance-based lightness**: Closer to pattern features = brighter
- **Time-based hue rotation**: H = (base_hue + t * rotation_speed) % 360
- **Chroma modulation**: Vary saturation based on pattern intensity

## Implementation Architecture

```
LuminaryPattern (ABC)
├── RipplePattern (ripple.py)
├── SpiralPattern (spiral.py)  
├── WavePattern (wave.py)
└── BreathingPattern (breathing.py)

BeamArray
├── Array construction from Net geometry
├── Basis point calculation
├── Hardware mapping (node/strip/strip_idx)
└── SDF evaluation interface

PatternRenderer  
├── Static SVG output (sample command)
├── WebSocket streaming (preview command)
└── Hardware output (run command - future)

PatternDiscovery
├── Auto-discovery from luminary/patterns/
├── Interactive selection menu
└── Pattern metadata extraction
```

## Rendering Pipeline

### Static SVG Output (`sample`)
1. **Pattern Loading**: Import pattern class from `luminary/patterns/<name>.py`
2. **Beam Array Construction**: Build numpy array from Net geometry
3. **Pattern Evaluation**: Compute OKLCH values at specified time `t`
4. **Color Application**: Apply computed OKLCH to each beam
5. **SVG Generation**: Render Net with pattern-derived colors
6. **File Output**: Save as `config_name.<pattern>.svg`

### Real-time Animation (`preview`)
1. **WebSocket Server**: Stream OKLCH updates at configurable frame rate
2. **Web Client**: HTML page with SVG that receives real-time updates
3. **Time Synchronization**: Start from `t=0` when client connects
4. **Animation Loop**: Continuously evaluate pattern and stream updates

## Use Cases

### Pattern Development
- **Rapid Prototyping**: Create new pattern file, test with `sample` command
- **Parameter Tuning**: Adjust pattern parameters and see immediate feedback
- **Animation Testing**: Use `preview` to see real-time pattern behavior

### Design and Visualization
- **Static Previews**: Generate SVGs for documentation and design review
- **Animation Demos**: Show pattern behavior to stakeholders via web preview
- **Color Scheme Validation**: Verify pattern appearance on actual Net geometry

### Production Preparation
- **Hardware Mapping**: Pre-calculated node/strip/strip_idx for LED addressing
- **Performance Testing**: Verify pattern computation speed with large Nets
- **Pattern Library**: Build collection of proven patterns for deployment

## Future Extensions

### Pattern Library Growth
- **Community Contributions**: Easy pattern development encourages sharing
- **Pattern Metadata**: Description, author, parameters for better discovery
- **Version Management**: Pattern versioning for reproducible results

### Advanced Features
- **Pattern Parameters**: Runtime configuration via command-line flags
- **Pattern Composition**: Layer multiple patterns with blend modes
- **Audio Reactivity**: Modulate patterns based on audio input (in `run` mode)

### Production Integration
- **Hardware Protocols**: Support for various LED strip controllers
- **Performance Optimization**: GPU acceleration for complex patterns
- **Distributed Deployment**: Multi-node hardware synchronization

## References

- **SDF Resources**: Inigo Quilez's distance function articles and shader examples
- **OKLCH Color Space**: CSS Color Module Level 4 specification
- **NumPy Vectorization**: Best practices for high-performance array computation
- **WebSocket Streaming**: Real-time web communication patterns
- **LED Hardware**: WS2812B, APA102 protocols and timing requirements