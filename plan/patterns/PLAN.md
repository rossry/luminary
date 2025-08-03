# Luminary Patterns Implementation Plan

## Branch Structure and Dependencies

```
foundation/patterns/_
├── foundation/patterns/base-infrastructure/_
├── foundation/patterns/beam-array/_  
├── foundation/patterns/example-patterns/_
├── foundation/patterns/cli-integration/_
├── foundation/patterns/static-rendering/_
└── foundation/patterns/animation/_
    └── foundation/patterns/animation/websocket-server/_
```

### Dependency Chain
1. **base-infrastructure** → Independent (abstract base class, pattern discovery)
2. **beam-array** → Depends on base-infrastructure (numpy array construction)
3. **example-patterns** → Depends on base-infrastructure (reference implementations)
4. **cli-integration** → Depends on base-infrastructure (command parsing, pattern selection)
5. **static-rendering** → Depends on beam-array, example-patterns, cli-integration (SVG output)
6. **animation** → Depends on static-rendering (real-time updates)
7. **websocket-server** → Depends on animation (web streaming)

## Phase 1: Base Infrastructure (`foundation/patterns/base-infrastructure/_`)

### Objectives
- Create abstract `LuminaryPattern` base class
- Implement pattern discovery system from `luminary/patterns/`
- Define numpy array column schema
- Set up basic CLI argument parsing

### Implementation Steps

#### 1.1 Abstract Base Class
```python
# luminary/patterns/base.py
from abc import ABC, abstractmethod
import numpy as np

class LuminaryPattern(ABC):
    @abstractmethod
    def evaluate_sdf(self, beam_array: np.ndarray, t: float) -> np.ndarray:
        """Return OKLCH values [l, c, h] for each beam at time t."""
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable pattern name."""
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """Pattern description for selection menu."""
        pass
```

#### 1.2 Pattern Discovery System
```python
# luminary/patterns/discovery.py
def discover_patterns() -> Dict[str, Type[LuminaryPattern]]:
    """Auto-discover patterns from luminary/patterns/*.py files."""
    
def get_pattern_choices() -> List[Tuple[str, str, str]]:
    """Return [(filename, name, description)] for interactive selection."""
    
def interactive_pattern_selection() -> str:
    """Show multiple choice menu, return selected pattern filename."""
```

#### 1.3 Array Schema Definition
```python
# luminary/patterns/schema.py
BEAM_ARRAY_COLUMNS = [
    'node', 'strip', 'strip_idx',  # Hardware mapping
    'x', 'y', 'r', 'theta',       # Spatial coordinates
    'face', 'facet', 'edge', 'position_index'  # Geometric hierarchy
]

OKLCH_COLUMNS = ['l', 'c', 'h']
```

#### 1.4 CLI Infrastructure
```python
# Add to main.py
def cmd_pattern(args):
    """Handle pattern subcommand with sample/preview/run."""
    if args.subcommand == 'sample':
        # Delegate to static rendering
    elif args.subcommand == 'preview':
        # Delegate to animation system
    elif args.subcommand == 'run':
        # Future: hardware output
```

### Testing
- [ ] Pattern discovery finds all files in `luminary/patterns/`
- [ ] Interactive selection menu works correctly
- [ ] Base class interface is properly defined
- [ ] CLI argument parsing handles all subcommands

### Deliverables
- Abstract `LuminaryPattern` base class
- Pattern discovery and selection system
- Array schema definitions
- Basic CLI infrastructure for `pattern` subcommand

---

## Phase 2: Beam Array Construction (`foundation/patterns/beam-array/_`)

### Objectives
- Build numpy array from Net geometry
- Calculate basis points for each beam
- Implement hardware mapping formulas
- Optimize for vectorized operations

### Implementation Steps

#### 2.1 Beam Array Builder
```python
# luminary/patterns/beam_array.py
class BeamArrayBuilder:
    def __init__(self, net: Net):
        self.net = net
    
    def build_array(self) -> np.ndarray:
        """Construct beam array with all required columns."""
        
    def _calculate_basis_points(self, beams: List[Beam]) -> np.ndarray:
        """Calculate geometric center of each beam polygon."""
        
    def _map_to_hardware(self, beam_data: np.ndarray) -> np.ndarray:
        """Calculate node/strip/strip_idx from geometric position."""
```

#### 2.2 Hardware Mapping Algorithm
- **Node Calculation**: Based on spatial position within Net bounds
- **Strip Calculation**: Derived from triangle/facet/edge combination
- **Strip Index**: Sequential position within calculated strip
- **Formula Documentation**: Clear mapping rules for reproducibility

#### 2.3 Coordinate Systems
- **Cartesian (x, y)**: Beam basis point in Net coordinate space
- **Polar (r, theta)**: Distance and angle from Net center
- **Geometric Hierarchy**: Triangle, facet, edge, position indices

#### 2.4 Performance Optimization
- **Memory Layout**: Contiguous arrays for cache efficiency
- **Vectorized Operations**: All calculations use numpy array operations
- **Data Types**: Appropriate dtypes to minimize memory usage

### Testing
- [ ] Array construction from various Net configurations
- [ ] Basis point calculations are geometrically accurate
- [ ] Hardware mapping produces valid node/strip/strip_idx ranges
- [ ] Performance benchmarks for large Net sizes

### Deliverables
- Complete beam array construction system
- Hardware mapping algorithms
- Optimized numpy array operations
- Performance benchmarking results

---

## Phase 3: Example Patterns (`foundation/patterns/example-patterns/_`)

### Objectives
- Implement 4 reference patterns for developer guidance
- Demonstrate different SDF techniques
- Validate pattern base class interface
- Provide comprehensive pattern examples

### Implementation Steps

#### 3.1 Ripple Pattern
```python
# luminary/patterns/ripple.py
class RipplePattern(LuminaryPattern):
    def evaluate_sdf(self, beam_array: np.ndarray, t: float) -> np.ndarray:
        # Expanding circular waves from center
        # L varies with distance from expanding ring
        # C constant or distance-modulated
        # H rotates with time
```

#### 3.2 Spiral Pattern  
```python
# luminary/patterns/spiral.py
class SpiralPattern(LuminaryPattern):
    def evaluate_sdf(self, beam_array: np.ndarray, t: float) -> np.ndarray:
        # Rotating spiral arms with color gradient
        # Uses polar coordinates (r, theta)
        # H rotates with spiral arms
        # L varies with arm proximity
```

#### 3.3 Wave Pattern
```python
# luminary/patterns/wave.py
class WavePattern(LuminaryPattern):
    def evaluate_sdf(self, beam_array: np.ndarray, t: float) -> np.ndarray:
        # Linear traveling waves
        # Direction configurable via class parameters
        # L varies with wave amplitude
        # H can shift with wave phase
```

#### 3.4 Breathing Pattern
```python
# luminary/patterns/breathing.py  
class BreathingPattern(LuminaryPattern):
    def evaluate_sdf(self, beam_array: np.ndarray, t: float) -> np.ndarray:
        # Gentle pulsing luminance
        # Smooth sinusoidal L variation
        # Subtle C modulation
        # H can shift slowly over time
```

#### 3.5 Pattern Documentation
Each pattern includes:
- **Docstring**: Mathematical description of the SDF
- **Parameters**: Configurable aspects (speed, amplitude, etc.)
- **Visual Description**: Expected appearance and behavior
- **Implementation Notes**: Key algorithmic details

### Testing
- [ ] Each pattern produces valid OKLCH outputs
- [ ] Patterns work with various Net sizes and configurations
- [ ] Animation appears smooth over time parameter
- [ ] SDF calculations are mathematically correct

### Deliverables
- Four complete reference patterns
- Pattern parameter documentation
- Visual validation of pattern outputs
- Developer guidance and examples

---

## Phase 4: CLI Integration (`foundation/patterns/cli-integration/_`)

### Objectives
- Complete `pattern` subcommand implementation
- Interactive pattern selection when name omitted
- Proper argument parsing for all subcommands
- Integration with existing CLI architecture

### Implementation Steps

#### 4.1 Argument Parser Extension
```python
# main.py updates
pattern_parser = subparsers.add_parser('pattern', help='Pattern operations')
pattern_subparsers = pattern_parser.add_subparsers(dest='pattern_subcommand')

sample_parser = pattern_subparsers.add_parser('sample', help='Generate static SVG')
sample_parser.add_argument('pattern_name', nargs='?', help='Pattern name (optional)')
sample_parser.add_argument('-t', '--time', type=float, default=0.0, help='Time parameter')
# ... additional arguments

preview_parser = pattern_subparsers.add_parser('preview', help='Real-time animation server')
# ... similar argument structure

run_parser = pattern_subparsers.add_parser('run', help='Hardware output (future)')
# ... hardware-specific arguments
```

#### 4.2 Interactive Selection Integration
- **Menu Display**: Show numbered list of available patterns
- **User Input**: Handle selection with validation
- **Error Handling**: Graceful fallback for invalid selections
- **Integration**: Seamless flow into pattern execution

#### 4.3 Pattern Loading System
```python
# luminary/patterns/loader.py
def load_pattern(pattern_name: str) -> LuminaryPattern:
    """Load pattern class from filename."""
    
def get_pattern_or_select(pattern_name: Optional[str]) -> LuminaryPattern:
    """Load specified pattern or show interactive selection."""
```

#### 4.4 Error Handling
- **Missing Patterns**: Clear error messages for non-existent patterns
- **Import Errors**: Helpful debugging for pattern implementation issues
- **Argument Validation**: Proper validation of time parameters, file paths
- **User Experience**: Consistent error reporting across all subcommands

### Testing
- [ ] All pattern subcommands parse arguments correctly
- [ ] Interactive selection works with various input scenarios
- [ ] Error handling provides helpful user feedback
- [ ] Integration with existing CLI doesn't break other commands

### Deliverables
- Complete CLI integration for pattern subcommand
- Interactive pattern selection system
- Comprehensive error handling
- Seamless user experience

---

## Phase 5: Static Rendering (`foundation/patterns/static-rendering/_`)

### Objectives
- Implement `pattern sample` command functionality
- Apply pattern OKLCH values to beam colors
- Generate SVG output with pattern-derived colors
- Optimize rendering performance

### Implementation Steps

#### 5.1 Pattern Renderer
```python
# luminary/patterns/renderer.py
class PatternRenderer:
    def __init__(self, net: Net, pattern: LuminaryPattern):
        self.net = net
        self.pattern = pattern
        self.beam_array = BeamArrayBuilder(net).build_array()
    
    def render_static(self, t: float = 0.0) -> None:
        """Apply pattern at time t and update beam colors."""
        
    def save_pattern_svg(self, output_path: Path, t: float = 0.0) -> None:
        """Generate SVG with pattern-derived colors."""
```

#### 5.2 OKLCH to SVG Color Conversion
- **Color Space Conversion**: OKLCH → RGB for SVG compatibility
- **Gamma Correction**: Proper color reproduction
- **Clipping/Validation**: Handle out-of-gamut colors gracefully
- **CSS Color**: Format colors for SVG fill attributes

#### 5.3 Beam Color Application
- **Pattern Evaluation**: Compute OKLCH for entire beam array
- **Color Assignment**: Apply OKLCH values to individual beams
- **SVG Integration**: Update existing SVG generation pipeline
- **File Naming**: `config_name.<pattern>.svg` convention

#### 5.4 Performance Optimization
- **Vectorized Operations**: All color computations use numpy arrays
- **Memory Efficiency**: Minimize array copying and allocation
- **Caching**: Cache beam array construction for repeated renders
- **Profiling**: Benchmark rendering performance with large Nets

### Testing
- [ ] Pattern colors appear correctly in generated SVGs
- [ ] OKLCH to RGB conversion is mathematically accurate
- [ ] File naming conventions work correctly
- [ ] Performance is acceptable for large Net configurations

### Deliverables
- Complete static pattern rendering system
- OKLCH color space integration
- Optimized SVG generation pipeline
- Performance benchmarking results

---

## Phase 6: Animation Foundation (`foundation/patterns/animation/_`)

### Objectives
- Create animation loop infrastructure
- Time-based pattern evaluation
- Frame rate control and timing
- Foundation for WebSocket streaming

### Implementation Steps

#### 6.1 Animation Controller
```python
# luminary/patterns/animation.py
class AnimationController:
    def __init__(self, renderer: PatternRenderer, fps: float = 30.0):
        self.renderer = renderer
        self.fps = fps
        self.start_time = None
    
    def start_animation(self):
        """Begin animation loop from t=0."""
        
    def get_current_frame(self) -> np.ndarray:
        """Get OKLCH values for current time."""
```

#### 6.2 Time Management
- **Frame Timing**: Consistent frame rate with accurate timing
- **Start Time**: Track animation start for consistent t=0 reference
- **Time Calculation**: Smooth time progression for fluid animation
- **Performance Monitoring**: Track actual vs target frame rates

#### 6.3 Frame Generation
- **OKLCH Computation**: Generate color values for current time
- **Delta Detection**: Identify changed beams for efficient updates
- **Data Formatting**: Prepare frame data for transmission/rendering
- **Buffer Management**: Handle frame queuing and memory usage

#### 6.4 Animation Loop Structure
- **Non-blocking**: Animation runs without blocking other operations
- **Graceful Shutdown**: Clean animation termination
- **Error Recovery**: Handle pattern evaluation errors gracefully
- **Monitoring**: Frame rate and performance statistics

### Testing
- [ ] Animation timing is accurate and consistent
- [ ] Frame generation produces valid OKLCH outputs
- [ ] Animation can start, run, and stop cleanly
- [ ] Performance is adequate for target frame rates

### Deliverables
- Animation controller and timing system
- Frame generation and management
- Performance monitoring capabilities
- Foundation for real-time streaming

---

## Phase 7: WebSocket Server (`foundation/patterns/animation/websocket-server/_`)

### Objectives
- Implement `pattern preview` command
- WebSocket server for real-time streaming
- HTML client for animation display
- Synchronization and connection management

### Implementation Steps

#### 7.1 WebSocket Server
```python
# luminary/patterns/websocket_server.py
class PatternWebSocketServer:
    def __init__(self, renderer: PatternRenderer, port: int = 8080):
        self.renderer = renderer
        self.port = port
        self.animation_controller = AnimationController(renderer)
    
    async def handle_client(self, websocket):
        """Handle new client connection and streaming."""
        
    def start_server(self):
        """Start WebSocket server and animation."""
```

#### 7.2 HTML Client Interface
```html
<!-- luminary/patterns/static/viewer.html -->
<!DOCTYPE html>
<html>
<head>
    <title>Luminary Pattern Preview</title>
    <style>/* SVG styling and responsive layout */</style>
</head>
<body>
    <div id="pattern-viewer">
        <!-- SVG content loaded dynamically -->
    </div>
    <script>
        // WebSocket connection and SVG update logic
    </script>
</body>
</html>
```

#### 7.3 Streaming Protocol
- **Connection Protocol**: WebSocket handshake and initialization
- **Frame Format**: JSON format for OKLCH updates
- **Delta Updates**: Send only changed beam colors for efficiency
- **Time Synchronization**: Ensure consistent animation timing

#### 7.4 Client-Server Communication
```javascript
// Client-side JavaScript
const ws = new WebSocket('ws://localhost:8080');
ws.onmessage = function(event) {
    const frame = JSON.parse(event.data);
    updateBeamColors(frame.oklch_values);
};
```

#### 7.5 Connection Management
- **Multiple Clients**: Support concurrent viewers
- **Client Tracking**: Monitor connected clients and their state
- **Graceful Disconnection**: Handle client drops without affecting others
- **Resource Cleanup**: Proper cleanup when all clients disconnect

### Testing
- [ ] WebSocket server starts and accepts connections
- [ ] Animation streams correctly to connected clients
- [ ] Multiple clients can connect simultaneously
- [ ] Color updates appear smoothly in web browser
- [ ] Server handles client disconnections gracefully

### Deliverables
- Complete WebSocket streaming server
- HTML client for pattern visualization
- Real-time animation system
- Multi-client connection support

---

## Success Criteria

### Functional Requirements
- [ ] Pattern abstract base class with clear interface
- [ ] Automatic pattern discovery from `luminary/patterns/`
- [ ] Interactive pattern selection when name omitted
- [ ] Static SVG generation with pattern colors (`sample` command)
- [ ] Real-time animation streaming (`preview` command)
- [ ] Hardware mapping columns (node/strip/strip_idx) correctly calculated
- [ ] Four example patterns demonstrating different techniques

### Technical Requirements  
- [ ] All SDF operations use vectorized numpy computation
- [ ] OKLCH color space properly integrated
- [ ] Performance suitable for real-time animation (30 FPS target)
- [ ] Memory usage remains reasonable for large Net configurations
- [ ] WebSocket streaming works reliably with multiple clients

### Developer Experience
- [ ] Clear pattern development guidelines and examples
- [ ] Simple file-based pattern addition (create file, use command)
- [ ] Helpful error messages for common development issues
- [ ] Complete API documentation for pattern development

### Integration Requirements
- [ ] CLI integration doesn't interfere with existing commands
- [ ] Pattern system works with all existing Net configurations
- [ ] SVG output maintains quality and formatting standards
- [ ] Code follows existing project conventions and quality standards

## Risk Mitigation

### Performance Concerns
- **Risk**: SDF evaluation may be too slow for real-time animation
- **Mitigation**: Extensive profiling, optimize critical paths, consider numba/cython

### Memory Usage
- **Risk**: Large beam arrays may consume excessive memory
- **Mitigation**: Efficient data types, streaming evaluation, garbage collection

### Pattern Complexity
- **Risk**: Complex SDFs may be difficult to implement correctly
- **Mitigation**: Start with simple patterns, comprehensive examples, good documentation

### WebSocket Reliability
- **Risk**: Real-time streaming may be unstable or laggy
- **Mitigation**: Delta updates, connection monitoring, graceful degradation

## Timeline Estimate

- **Phase 1** (Base Infrastructure): 2-3 days
- **Phase 2** (Beam Array): 3-4 days (most complex geometric work)
- **Phase 3** (Example Patterns): 2-3 days
- **Phase 4** (CLI Integration): 1-2 days
- **Phase 5** (Static Rendering): 2-3 days
- **Phase 6** (Animation): 2-3 days
- **Phase 7** (WebSocket Server): 3-4 days

**Total**: 15-22 days estimated development time

## Future Extensions

### Advanced Patterns
- **GPU Acceleration**: CUDA/OpenCL for complex SDF evaluation
- **Pattern Parameters**: Runtime configuration via CLI flags
- **Pattern Composition**: Layer multiple patterns with blend modes

### Production Features
- **Hardware Output**: Implementation of `run` command for LED control
- **Distributed Rendering**: Multi-node pattern synchronization
- **Performance Monitoring**: Real-time performance metrics and optimization

### Developer Tools
- **Pattern Debugger**: Visual SDF debugging and parameter tuning
- **Pattern Library**: Curated collection of community patterns
- **Interactive Editor**: Web-based pattern development environment