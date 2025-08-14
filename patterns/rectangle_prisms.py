"""Rectangle prisms pattern with 3D moving boxes through the sphere."""

import numpy as np
from typing import List, Tuple
from dataclasses import dataclass
from luminary.patterns.base import LuminaryPattern
from luminary.patterns.schema import BeamArrayColumns


@dataclass
class Rectangle:
    """A 3D rectangular prism moving through space."""
    id: int
    # 3D position (center of rectangle)
    x: float
    y: float
    z: float
    # 3D velocity
    vx: float
    vy: float
    vz: float
    # Size (width, height, depth)
    width: float
    height: float
    depth: float
    # Color in OKLCH
    l: float  # lightness
    c: float  # chroma
    h: float  # hue


class DriftingParameter:
    """A parameter that drifts over time with random walk behavior."""

    def __init__(self, initial_value: float, min_val: float, max_val: float,
                 drift_rate: float = 0.1):
        self.value = initial_value
        self.min_val = min_val
        self.max_val = max_val
        self.drift_rate = drift_rate

    def update(self, dt: float, rng: np.random.Generator) -> None:
        """Update parameter with random walk."""
        # Random walk with mean reversion toward center
        center = (self.min_val + self.max_val) / 2
        drift = rng.normal(0, self.drift_rate * dt)

        # Add slight pull toward center to prevent extreme values
        center_pull = (center - self.value) * 0.1 * dt

        self.value += drift + center_pull
        self.value = np.clip(self.value, self.min_val, self.max_val)


class RectanglePrismsPattern(LuminaryPattern):
    """Moving rectangular prisms pattern through 3D space."""

    @property
    def name(self) -> str:
        return "Rectangle Prisms"

    @property
    def description(self) -> str:
        return "3D rectangular prisms moving through space with drifting parameters"

    def __init__(self):
        # === TUNABLE PARAMETERS SECTION ===
        # Easy to find and modify for experimentation

        # Movement parameters
        self.speed = DriftingParameter(120.0, 90.0, 240.0, 10.0)  # units/sec (faster transit)

        # Size parameters (quadrupled from original)
        self.avg_size = DriftingParameter(100.0, 40.0, 200.0, 8.0)  # average dimension (doubled again)
        self.size_spread = DriftingParameter(2.0, 0.4, 12.0, 0.8)  # variance multiplier (doubled again)

        # Color parameters - 2 base colors that drift
        self.color1_h = DriftingParameter(0.0, 0.0, 360.0, 5.0)    # red-ish
        self.color2_h = DriftingParameter(240.0, 0.0, 360.0, 5.0)  # blue-ish
        self.color_variance = DriftingParameter(10.0, 5.0, 20.0, 1.0)  # hue variance (reduced)

        # DENSITY CONTROL - Main parameter to adjust! (20x increase from original)
        self.base_spawn_rate = 60.0  # rectangles per second at base size (doubled again to 20x original)
        
        # MOVEMENT BIAS - Bias toward vertical (pole) movement
        self.pole_bias_strength = 0.4  # 0.0 = no bias, 1.0 = extreme pole bias
        
        # COLOR RANDOMIZATION - Randomly jump one color every 8-20 seconds
        self.color_jump_interval = DriftingParameter(14.0, 8.0, 20.0, 2.0)  # seconds between jumps
        self.last_color_jump = 0.0

        # === END TUNABLE PARAMETERS ===

        # Rectangle management
        self.rectangles: List[Rectangle] = []
        self.next_rect_id = 0
        self.last_spawn_time = 0.0

        # RNG for reproducible randomness
        self.rng = np.random.default_rng(42)

        # Coordinate system bounds - expand beyond LED positions for spawning
        self.bounds = {
            'x_min': -250, 'x_max': 250,
            'y_min': -170, 'y_max': 120,
            'z_min': -150, 'z_max': 150  # Assume sphere is roughly in this Z range
        }

        # Initialize with some rectangles already on/near the sphere
        self._spawn_initial_rectangles()
        
        # Hot start - simulate 10 seconds of pattern evolution
        self._simulate_hot_start(10.0)

    def _update_parameters(self, t: float) -> None:
        """Update all drifting parameters."""
        # Use a fixed dt for consistency
        dt = 0.033  # ~30 FPS

        self.speed.update(dt, self.rng)
        self.avg_size.update(dt, self.rng)
        self.size_spread.update(dt, self.rng)
        self.color1_h.update(dt, self.rng)
        self.color2_h.update(dt, self.rng)
        self.color_variance.update(dt, self.rng)
        self.color_jump_interval.update(dt, self.rng)
    
    def _cubic_pole_warp(self, vx: float, vy: float, vz: float) -> Tuple[float, float, float]:
        """Apply cubic warping to bias velocity toward vertical (Y-axis) movement."""
        total = np.sqrt(vx**2 + vy**2 + vz**2)
        if total == 0:
            return 0.0, 0.0, 0.0
            
        # Calculate Y component fraction
        y_fraction = abs(vy) / total
        
        # Apply cubic warping - higher bias_strength = more extreme Y values
        warp_power = 1.0 - self.pole_bias_strength  # 0.6 with bias_strength=0.4
        new_y_fraction = y_fraction**warp_power
        
        # Calculate scaling factor
        if y_fraction > 0:
            scale = new_y_fraction / y_fraction
        else:
            scale = 1.0
            
        # Apply scaling - Y gets amplified, X/Z get compressed
        return vx / scale, vy * scale, vz / scale
    
    def _check_color_jump(self, t: float) -> None:
        """Check if it's time to randomly jump one of the colors."""
        if t - self.last_color_jump >= self.color_jump_interval.value:
            # Pick which color to randomize (0 or 1)
            color_to_jump = self.rng.integers(0, 2)
            
            # Jump to completely random hue (0-360 degrees)
            new_hue = self.rng.uniform(0.0, 360.0)
            
            if color_to_jump == 0:
                self.color1_h.value = new_hue
                print(f"🎨 Color jump! Color 1 jumped to {new_hue:.1f}°")
            else:
                self.color2_h.value = new_hue
                print(f"🎨 Color jump! Color 2 jumped to {new_hue:.1f}°")
            
            self.last_color_jump = t
    
    def _simulate_hot_start(self, hot_start_time: float) -> None:
        """Simulate the pattern evolution for hot_start_time seconds without lag."""
        dt = 0.1  # Larger timesteps for efficiency
        current_time = 0.0
        
        while current_time < hot_start_time:
            # Update drifting parameters (evolve the pattern style)
            self._update_parameters(current_time)
            
            # Spawn new rectangles if needed  
            if self._should_spawn_rectangle(current_time):
                self._spawn_rectangle(current_time)
            
            # Update existing rectangles (move them, remove old ones)
            self._update_rectangles(dt)
            
            current_time += dt
        
        # Update the spawn timer to match our hot start time
        self.last_spawn_time = hot_start_time

    def _spawn_initial_rectangles(self) -> None:
        """Spawn initial rectangles overlapping the sphere for immediate visual effect."""
        # Create 8-12 rectangles positioned to overlap the sphere
        initial_count = self.rng.integers(8, 13)

        for _ in range(initial_count):
            # Position rectangles close to or overlapping the LED area
            x = self.rng.uniform(-150, 150)  # Within LED bounds
            y = self.rng.uniform(-100, 50)   # Within LED bounds
            z = self.rng.uniform(-100, 100)  # Near sphere surface

            # Give them random velocities in all directions, then apply pole bias
            vx = self.rng.uniform(-self.speed.value, self.speed.value)
            vy = self.rng.uniform(-self.speed.value, self.speed.value)
            vz = self.rng.uniform(-self.speed.value, self.speed.value)
            
            # Apply cubic pole warping for vertical bias
            vx, vy, vz = self._cubic_pole_warp(vx, vy, vz)

            # Generate sizes using current parameters
            size_variance = 1.0 + self.rng.normal(0, self.size_spread.value)
            size_variance = np.clip(size_variance, 0.3, 3.0)

            base_size = self.avg_size.value * size_variance
            width = base_size * self.rng.uniform(0.8, 1.2)
            depth = base_size * self.rng.uniform(0.8, 1.2)
            height = base_size * 0.5 * self.rng.uniform(0.8, 1.2)

            # Pick random colors from the two base colors
            color_choice = self.rng.integers(0, 2)
            if color_choice == 0:
                base_hue = self.color1_h.value
            else:
                base_hue = self.color2_h.value

            # Add variance to hue
            hue = base_hue + self.rng.uniform(-self.color_variance.value, self.color_variance.value)
            hue = hue % 360.0

            # Set lightness and chroma with some variance
            lightness = np.clip(self.rng.normal(0.6, 0.1), 0.2, 0.9)
            chroma = np.clip(self.rng.normal(0.3, 0.05), 0.1, 0.4)

            rect = Rectangle(
                id=self.next_rect_id,
                x=x, y=y, z=z,
                vx=vx, vy=vy, vz=vz,
                width=width, height=height, depth=depth,
                l=lightness, c=chroma, h=hue
            )

            self.rectangles.append(rect)
            self.next_rect_id += 1

    def _should_spawn_rectangle(self, t: float) -> bool:
        """Determine if we should spawn a new rectangle based on density logic."""
        # Adjust spawn rate based on size - smaller rectangles spawn more frequently
        base_volume = 40.0 ** 3  # Volume at base avg_size
        current_volume = self.avg_size.value ** 3
        volume_ratio = base_volume / current_volume

        # Clamp ratio to reasonable bounds
        volume_ratio = np.clip(volume_ratio, 0.1, 10.0)

        adjusted_spawn_rate = self.base_spawn_rate * volume_ratio

        # Time since last spawn
        time_since_spawn = t - self.last_spawn_time
        spawn_interval = 1.0 / adjusted_spawn_rate

        return time_since_spawn >= spawn_interval

    def _spawn_rectangle(self, t: float) -> None:
        """Spawn a new rectangle from outside the bounds."""
        # Pick a random face of the bounding box to spawn from
        face = self.rng.integers(0, 6)

        if face == 0:  # -X face
            x = self.bounds['x_min'] - 50
            y = self.rng.uniform(self.bounds['y_min'], self.bounds['y_max'])
            z = self.rng.uniform(self.bounds['z_min'], self.bounds['z_max'])
            vx = self.rng.uniform(0.5, 1.0)  # Always move inward
        elif face == 1:  # +X face
            x = self.bounds['x_max'] + 50
            y = self.rng.uniform(self.bounds['y_min'], self.bounds['y_max'])
            z = self.rng.uniform(self.bounds['z_min'], self.bounds['z_max'])
            vx = self.rng.uniform(-1.0, -0.5)  # Always move inward
        elif face == 2:  # -Y face
            x = self.rng.uniform(self.bounds['x_min'], self.bounds['x_max'])
            y = self.bounds['y_min'] - 50
            z = self.rng.uniform(self.bounds['z_min'], self.bounds['z_max'])
            vy = self.rng.uniform(0.5, 1.0)  # Always move inward
        elif face == 3:  # +Y face
            x = self.rng.uniform(self.bounds['x_min'], self.bounds['x_max'])
            y = self.bounds['y_max'] + 50
            z = self.rng.uniform(self.bounds['z_min'], self.bounds['z_max'])
            vy = self.rng.uniform(-1.0, -0.5)  # Always move inward
        elif face == 4:  # -Z face
            x = self.rng.uniform(self.bounds['x_min'], self.bounds['x_max'])
            y = self.rng.uniform(self.bounds['y_min'], self.bounds['y_max'])
            z = self.bounds['z_min'] - 50
            vz = self.rng.uniform(0.5, 1.0)  # Always move inward
        else:  # +Z face
            x = self.rng.uniform(self.bounds['x_min'], self.bounds['x_max'])
            y = self.rng.uniform(self.bounds['y_min'], self.bounds['y_max'])
            z = self.bounds['z_max'] + 50
            vz = self.rng.uniform(-1.0, -0.5)  # Always move inward

        # Ensure we have velocity components for all axes (random direction)
        if face < 2:  # X faces already set vx
            vy = self.rng.uniform(-0.5, 0.5)
            vz = self.rng.uniform(-0.5, 0.5)
        elif face < 4:  # Y faces already set vy
            vx = self.rng.uniform(-0.5, 0.5)
            vz = self.rng.uniform(-0.5, 0.5)
        else:  # Z faces already set vz
            vx = self.rng.uniform(-0.5, 0.5)
            vy = self.rng.uniform(-0.5, 0.5)

        # Scale velocity by current speed parameter
        speed_multiplier = self.speed.value
        vx *= speed_multiplier
        vy *= speed_multiplier
        vz *= speed_multiplier
        
        # Apply cubic pole warping for vertical bias
        vx, vy, vz = self._cubic_pole_warp(vx, vy, vz)

        # Generate size with variance
        size_variance = 1.0 + self.rng.normal(0, self.size_spread.value)
        size_variance = np.clip(size_variance, 0.3, 3.0)

        base_size = self.avg_size.value * size_variance
        width = base_size * self.rng.uniform(0.8, 1.2)
        depth = base_size * self.rng.uniform(0.8, 1.2)
        height = base_size * 0.5 * self.rng.uniform(0.8, 1.2)  # Height is ~half of width/depth

        # Pick one of the two base colors with variance
        color_choice = self.rng.integers(0, 2)
        if color_choice == 0:
            base_hue = self.color1_h.value
        else:
            base_hue = self.color2_h.value

        # Add variance to hue
        hue = base_hue + self.rng.uniform(-self.color_variance.value, self.color_variance.value)
        hue = hue % 360.0

        # Set lightness and chroma with some variance
        lightness = np.clip(self.rng.normal(0.6, 0.1), 0.2, 0.9)
        chroma = np.clip(self.rng.normal(0.3, 0.05), 0.1, 0.4)

        rect = Rectangle(
            id=self.next_rect_id,
            x=x, y=y, z=z,
            vx=vx, vy=vy, vz=vz,
            width=width, height=height, depth=depth,
            l=lightness, c=chroma, h=hue
        )

        self.rectangles.append(rect)
        self.next_rect_id += 1
        self.last_spawn_time = t

    def _update_rectangles(self, dt: float) -> None:
        """Update rectangle positions and remove those that have left bounds."""
        rectangles_to_remove = []

        for rect in self.rectangles:
            # Update position
            rect.x += rect.vx * dt
            rect.y += rect.vy * dt
            rect.z += rect.vz * dt

            # Check if rectangle is completely outside bounds (with margin)
            margin = 100  # Remove when this far outside
            if (rect.x < self.bounds['x_min'] - margin or
                rect.x > self.bounds['x_max'] + margin or
                rect.y < self.bounds['y_min'] - margin or
                rect.y > self.bounds['y_max'] + margin or
                rect.z < self.bounds['z_min'] - margin or
                rect.z > self.bounds['z_max'] + margin):
                rectangles_to_remove.append(rect)

        # Remove rectangles that have left the area
        for rect in rectangles_to_remove:
            self.rectangles.remove(rect)

    def _point_in_rectangle(self, px: float, py: float, pz: float, rect: Rectangle) -> bool:
        """Test if a 3D point is inside a rectangle (axis-aligned box)."""
        half_width = rect.width / 2
        half_height = rect.height / 2
        half_depth = rect.depth / 2

        return (abs(px - rect.x) <= half_width and
                abs(py - rect.y) <= half_height and
                abs(pz - rect.z) <= half_depth)

    def evaluate(self, beam_array: np.ndarray, t: float) -> np.ndarray:
        """Generate rectangle prism pattern."""
        n_beams = beam_array.shape[0]
        oklch_output = np.zeros((n_beams, 3), dtype=np.float32)

        # Update drifting parameters
        self._update_parameters(t)
        
        # Check for color jumps
        self._check_color_jump(t)

        # Spawn new rectangles if needed
        if self._should_spawn_rectangle(t):
            self._spawn_rectangle(t)

        # Update existing rectangles
        dt = 0.033  # Assume ~30 FPS for physics updates
        self._update_rectangles(dt)

        # Extract LED positions (assuming Z=0 for now - LEDs on sphere surface)
        led_x = beam_array[:, BeamArrayColumns.X]
        led_y = beam_array[:, BeamArrayColumns.Y]
        # For 3D, we need to estimate Z coordinates - assume they're on a sphere
        # For simplicity, let's use the radial distance to estimate Z
        led_r = beam_array[:, BeamArrayColumns.R]
        # Sphere radius should encompass the actual LED distribution
        sphere_radius = 250.0  # Large enough for X range -205 to 205
        # Z coordinate based on assumption that X,Y are projected onto plane
        # and actual 3D position is on sphere surface
        r_2d_sq = led_x**2 + led_y**2
        led_z = np.sqrt(np.maximum(0, sphere_radius**2 - r_2d_sq))

        # Default to black
        oklch_output[:, 0] = 0.05  # Very dim
        oklch_output[:, 1] = 0.0   # No chroma (gray)
        oklch_output[:, 2] = 0.0   # Hue doesn't matter when chroma=0

        # Vectorized collision detection - O(n_rectangles) instead of O(n_beams × n_rectangles)
        # Sort rectangles by ID to maintain precedence (lowest ID wins)
        sorted_rectangles = sorted(self.rectangles, key=lambda r: r.id)
        
        for rect in sorted_rectangles:
            # Check ALL LEDs against this rectangle at once using numpy broadcasting
            half_width = rect.width / 2
            half_height = rect.height / 2  
            half_depth = rect.depth / 2
            
            # Vectorized collision test - returns boolean array of shape (n_beams,)
            inside_x = np.abs(led_x - rect.x) <= half_width
            inside_y = np.abs(led_y - rect.y) <= half_height
            inside_z = np.abs(led_z - rect.z) <= half_depth
            
            # LEDs that are inside this rectangle
            inside_rect = inside_x & inside_y & inside_z
            
            # Apply color only where no previous rectangle has claimed the LED (precedence by processing order)
            # Only update LEDs that are currently black (haven't been claimed yet)
            unclaimed = (oklch_output[:, 1] == 0.0)  # Check chroma = 0 (our "black" marker)
            winners = inside_rect & unclaimed
            
            # Set colors for winning LEDs
            oklch_output[winners, 0] = rect.l
            oklch_output[winners, 1] = rect.c
            oklch_output[winners, 2] = rect.h

        return oklch_output
