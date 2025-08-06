# Luminary 2.0

A project for Next Year on Luna 2025. Luminary 1.0 was a previous, deprecated version; 2.0 is under development and 2.1 will mark the first production release.

Core development is managed with [Graphite](https://graphite.dev) for the core developer's convenience, but contributors can make PRs on merged branches with whatever git tooling you want. Watch this space for further guidance on contributing.

## Pattern Development

Luminary supports real-time animated geometric patterns using signed distance functions (SDFs). Patterns are written in Python and can be previewed in a web browser with WebSocket streaming.

### Creating a New Pattern

1. **Create a pattern file** in the `patterns/` directory (e.g., `patterns/my_pattern.py`)

2. **Implement the LuminaryPattern interface:**

```python
import numpy as np
from luminary.patterns.base import LuminaryPattern
from luminary.patterns.schema import BeamArrayColumns

class MyPattern(LuminaryPattern):
    @property
    def name(self) -> str:
        return "My Amazing Pattern"
    
    @property
    def description(self) -> str:
        return "Description of what the pattern looks like"
    
    def evaluate(self, beam_array: np.ndarray, t: float) -> np.ndarray:
        """Generate OKLCH color values for each beam at time t.
        
        Args:
            beam_array: Array with shape (n_beams, 11) containing beam data
            t: Time parameter for animation (seconds)
        
        Returns:
            Array with shape (n_beams, 3) containing [L, C, H] values where:
            - L (lightness): 0.0 (black) to 1.0 (white)
            - C (chroma): 0.0 (gray) to ~0.4 (saturated)
            - H (hue): 0° to 360° (color wheel)
        """
        n_beams = beam_array.shape[0]
        oklch_output = np.zeros((n_beams, 3))
        
        # Extract spatial coordinates
        x = beam_array[:, BeamArrayColumns.X]
        y = beam_array[:, BeamArrayColumns.Y] 
        r = beam_array[:, BeamArrayColumns.R]        # Distance from center
        theta = beam_array[:, BeamArrayColumns.THETA] # Polar angle
        
        # Example: Rotating spiral pattern
        oklch_output[:, 0] = 0.6  # Constant lightness
        oklch_output[:, 1] = 0.3  # Constant chroma
        
        # Hue varies with position and time
        spiral_hue = (theta * 180.0/np.pi + r * 2.0 + t * 60.0) % 360.0
        oklch_output[:, 2] = spiral_hue
        
        return oklch_output
```

### Available Beam Data

Each beam in the `beam_array` contains 11 columns accessed via `BeamArrayColumns`:

- **Hardware mapping**: `NODE`, `STRIP`, `STRIP_IDX` - LED hardware addresses
- **Spatial coordinates**: `X`, `Y` - Cartesian position in net space
- **Polar coordinates**: `R`, `THETA` - Distance and angle from net center  
- **Geometry hierarchy**: `FACE`, `FACET`, `EDGE`, `POSITION_INDEX` - Geometric structure

### Pattern Development Tips

- **Use vectorized numpy operations** - Avoid Python loops for performance
- **Keep values in range** - L: 0-1, C: 0-0.4, H: 0-360
- **Test with time variation** - Use the `t` parameter for animation
- **Start simple** - Basic color gradients, then add complexity

### Testing Your Pattern

#### Static Preview (SVG)
```bash
python main.py pattern sample my_pattern -c configs/4A-35.json -t 2.5
```

#### Real-time Animation (WebSocket Server)
```bash
# Install dependencies first
pip install fastapi uvicorn

# Start animation server
python main.py pattern preview my_pattern -c configs/4A-35.json --fps 30

# Open browser to http://localhost:8080
```

#### Interactive Pattern Selection
```bash
# Omit pattern name for interactive menu
python main.py pattern preview -c configs/4A-35.json
```

### Server Options

- `--host` - Server hostname (default: localhost)
- `--port` - Server port (default: 8080) 
- `--fps` - Animation frame rate (default: 30)

Example for external access:
```bash
python main.py pattern preview test -c configs/4A-35.json --host 0.0.0.0 --port 8080
```

### Example Patterns

See `patterns/test.py` for a complete working example that demonstrates:
- Time-based hue rotation
- Theta-based color mapping  
- Proper numpy vectorization
