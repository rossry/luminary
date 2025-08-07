"""Schema definitions for beam arrays and pattern data structures."""

from typing import List

# Beam array column definitions
BEAM_ARRAY_COLUMNS: List[str] = [
    # Hardware mapping columns (for production deployment)
    "node",          # Hardware node ID (0-63)
    "strip",         # LED strip ID within node (0-7)  
    "strip_idx",     # LED index within strip (0-511)
    
    # Spatial coordinate columns
    "x",             # Basis point X coordinate in Net space
    "y",             # Basis point Y coordinate in Net space
    "r",             # Polar radius from Net center
    "theta",         # Polar angle from positive X-axis (radians)
    
    # Geometric hierarchy columns
    "face",          # Triangle index (0-based)
    "facet",         # Facet letter within triangle (A, B, C or D, E, F)
    "edge",          # Edge index within facet (0-3: MAJOR_STARBOARD, MINOR_STARBOARD, MINOR_PORT, MAJOR_PORT)
    "position_index" # Beam position within edge (0-based)
]

# OKLCH color output columns
OKLCH_COLUMNS: List[str] = [
    "l",  # Lightness: 0.0 (black) to 1.0 (white)
    "c",  # Chroma: 0.0 (gray) to ~0.4 (saturated)
    "h"   # Hue: 0° to 360° (color wheel position)
]

# Column indices for efficient numpy access
class BeamArrayColumns:
    """Column indices for beam array access."""
    
    # Hardware mapping
    NODE = 0
    STRIP = 1
    STRIP_IDX = 2
    
    # Spatial coordinates
    X = 3
    Y = 4
    R = 5
    THETA = 6
    
    # Geometric hierarchy
    FACE = 7
    FACET = 8
    EDGE = 9
    POSITION_INDEX = 10


class OKLCHColumns:
    """Column indices for OKLCH color arrays."""
    
    L = 0  # Lightness
    C = 1  # Chroma
    H = 2  # Hue


# Data type specifications for memory efficiency
BEAM_ARRAY_DTYPE = [
    ("node", "u1"),          # uint8: 0-63
    ("strip", "u1"),         # uint8: 0-7
    ("strip_idx", "u2"),     # uint16: 0-511
    ("x", "f4"),             # float32: spatial coordinate
    ("y", "f4"),             # float32: spatial coordinate
    ("r", "f4"),             # float32: polar radius
    ("theta", "f4"),         # float32: polar angle
    ("face", "u2"),          # uint16: triangle index
    ("facet", "u1"),         # uint8: 0-5 (A-F encoded)
    ("edge", "u1"),          # uint8: 0-3
    ("position_index", "u2") # uint16: position within edge
]

OKLCH_ARRAY_DTYPE = [
    ("l", "f4"),  # float32: lightness 0-1
    ("c", "f4"),  # float32: chroma 0-0.4
    ("h", "f4")   # float32: hue 0-360
]