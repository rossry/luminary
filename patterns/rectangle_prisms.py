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
        self.speed = DriftingParameter(30.0, 10.0, 80.0, 0.5)  # units/sec

        # Size parameters
        self.avg_size = DriftingParameter(40.0, 15.0, 200.0, 10.0)  # average dimension
        self.size_spread = DriftingParameter(0.5, 0.1, 3.0, 0.2)  # variance multiplier

        # Color parameters - 2 base colors that drift
        self.color1_h = DriftingParameter(0.0, 0.0, 360.0, 5.0)    # red-ish
        self.color2_h = DriftingParameter(240.0, 0.0, 360.0, 5.0)  # blue-ish
        self.color_variance = DriftingParameter(10.0, 5.0, 20.0, 1.0)  # hue variance (reduced)

        # DENSITY CONTROL - Main parameter to adjust!
        self.base_spawn_rate = 20.0  # rectangles per second at base size

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
    
    def _spawn_initial_rectangles(self) -> None:
        """Spawn initial rectangles overlapping the sphere for immediate visual effect."""
        # Create 8-12 rectangles positioned to overlap the sphere
        initial_count = self.rng.integers(8, 13)
        
        for _ in range(initial_count):
            # Position rectangles close to or overlapping the LED area
            x = self.rng.uniform(-150, 150)  # Within LED bounds
            y = self.rng.uniform(-100, 50)   # Within LED bounds
            z = self.rng.uniform(-100, 100)  # Near sphere surface
            
            # Give them random velocities in all directions
            vx = self.rng.uniform(-self.speed.value, self.speed.value)
            vy = self.rng.uniform(-self.speed.value, self.speed.value)
            vz = self.rng.uniform(-self.speed.value, self.speed.value)
            
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
        # Assume sphere of radius ~150, LEDs are on surface
        sphere_radius = 150.0
        # Z coordinate based on assumption that X,Y are projected onto plane
        # and actual 3D position is on sphere surface
        r_2d_sq = led_x**2 + led_y**2
        led_z = np.sqrt(np.maximum(0, sphere_radius**2 - r_2d_sq))

        # Default to black
        oklch_output[:, 0] = 0.05  # Very dim
        oklch_output[:, 1] = 0.0   # No chroma (gray)
        oklch_output[:, 2] = 0.0   # Hue doesn't matter when chroma=0

        # Check each LED against each rectangle
        for i in range(n_beams):
            px, py, pz = led_x[i], led_y[i], led_z[i]

            # Find rectangles that contain this LED (lowest ID wins)
            containing_rects = []
            for rect in self.rectangles:
                if self._point_in_rectangle(px, py, pz, rect):
                    containing_rects.append(rect)

            # Apply precedence rule - lowest ID wins
            if containing_rects:
                winning_rect = min(containing_rects, key=lambda r: r.id)
                oklch_output[i, 0] = winning_rect.l
                oklch_output[i, 1] = winning_rect.c
                oklch_output[i, 2] = winning_rect.h

        return oklch_output
