"""Beam array construction from Net geometry."""

import numpy as np
from typing import List
import math

from luminary.geometry.net import Net
from .schema import BEAM_ARRAY_COLUMNS, BeamArrayColumns


class BeamArrayBuilder:
    """Builds numpy arrays from Net geometry for pattern evaluation."""
    
    def __init__(self, net: Net):
        """Initialize builder with Net geometry.
        
        Args:
            net: Net containing triangles, facets, and beams
        """
        self.net = net
        
    def build_array(self) -> np.ndarray:
        """Construct beam array with all required columns.
        
        Returns:
            Numpy array with shape (n_beams, n_columns) where columns are:
            [node, strip, strip_idx, x, y, r, theta, face, facet, edge, position_index]
        """
        # Collect all beams with metadata
        beams_data = []
        
        for face_idx, triangle in enumerate(self.net.triangles):
            for facet_idx, facet in enumerate(triangle.facets):
                beam_groups = facet.get_beams()
                
                for edge_idx, edge_beams in enumerate(beam_groups):
                    for position_idx, beam in enumerate(edge_beams):
                        beams_data.append({
                            'beam': beam,
                            'face': face_idx,
                            'facet': facet_idx,
                            'edge': edge_idx,
                            'position_index': position_idx
                        })
        
        print(f"  Total beams collected: {len(beams_data)}")
        
        if not beams_data:
            return np.zeros((0, len(BEAM_ARRAY_COLUMNS)), dtype=np.float32)
        
        # Build array
        n_beams = len(beams_data)
        beam_array = np.zeros((n_beams, len(BEAM_ARRAY_COLUMNS)), dtype=np.float32)
        
        for i, data in enumerate(beams_data):
            beam = data['beam']
            
            # Get basis point from beam (computed in Beam.__init__)
            basis_point = beam.get_basis_point()
            
            # Fill spatial coordinates
            beam_array[i, BeamArrayColumns.X] = basis_point.x
            beam_array[i, BeamArrayColumns.Y] = basis_point.y
            beam_array[i, BeamArrayColumns.R] = math.sqrt(basis_point.x**2 + basis_point.y**2)
            beam_array[i, BeamArrayColumns.THETA] = math.atan2(basis_point.y, basis_point.x)
            
            # Fill geometric hierarchy
            beam_array[i, BeamArrayColumns.FACE] = data['face']
            beam_array[i, BeamArrayColumns.FACET] = data['facet']
            beam_array[i, BeamArrayColumns.EDGE] = data['edge']
            beam_array[i, BeamArrayColumns.POSITION_INDEX] = data['position_index']
            
            # Fill hardware mapping
            node, strip, strip_idx = self._calculate_hardware_mapping(data)
            beam_array[i, BeamArrayColumns.NODE] = node
            beam_array[i, BeamArrayColumns.STRIP] = strip
            beam_array[i, BeamArrayColumns.STRIP_IDX] = strip_idx
        
        return beam_array
    
    def _calculate_hardware_mapping(self, beam_data: dict) -> tuple[int, int, int]:
        """Calculate hardware mapping for a beam.
        
        Args:
            beam_data: Dictionary with face, facet, edge, position_index
            
        Returns:
            Tuple of (node, strip, strip_idx)
        """
        # Simple placeholder mapping - replace with actual deployment formula
        face = beam_data['face']
        facet = beam_data['facet']
        edge = beam_data['edge']
        position = beam_data['position_index']
        
        node = (face * 3 + facet) % 64  # 0-63 nodes
        strip = edge  # 0-3 -> maps to 0-7 via node distribution
        strip_idx = position % 512  # 0-511 indices per strip
        
        return node, strip, strip_idx
    
    def create_beam_colors_dict(self, oklch_values: np.ndarray) -> dict:
        """Create beam colors dictionary from OKLCH values.
        
        Args:
            oklch_values: Numpy array with shape (n_beams, 3) containing [L, C, H] values
            
        Returns:
            Dictionary mapping beam_id tuples to Color objects
        """
        from luminary.color import Color
        
        beam_colors = {}
        beam_idx = 0
        
        # Traverse beams in same order as array construction
        for face_idx, triangle in enumerate(self.net.triangles):
            actual_face_idx = triangle.triangle_id
            for facet_idx, facet in enumerate(triangle.facets):
                beam_groups = facet.get_beams()
                
                for edge_idx, edge_beams in enumerate(beam_groups):
                    for position_idx, beam in enumerate(edge_beams):
                        if beam_idx < len(oklch_values):
                            l, c, h = oklch_values[beam_idx]
                            beam_id = (actual_face_idx, facet_idx, edge_idx, position_idx)
                            beam_colors[beam_id] = Color(l, c, h)
                            beam_idx += 1
        
        return beam_colors