"""Cellular automaton that evolves based on the geometric structure of the luminary net."""

import numpy as np
from scipy.spatial import cKDTree
from scipy.sparse import lil_matrix, csr_matrix
from luminary.patterns.base import LuminaryPattern
from luminary.patterns.schema import BeamArrayColumns

class CellularNet(LuminaryPattern):
    """Cellular automaton evolving along the geometric structure of the net."""

    def __init__(self):
        super().__init__()
        self.state_grid = None
        self.last_update_time = -1
        self.update_interval = 0.15  # Slightly faster updates
        self.initialized = False
        self.generation = 0

        # Precomputed spatial structures
        self.neighbor_matrix = None  # Sparse adjacency matrix
        self.kdtree = None
        self.positions = None
        self.neighbor_radius = 35.0

        # Species dynamics parameters
        self.species_count = 4
        self.max_age = 60  # Shorter lifespan for more turnover
        self.migration_prob = 0.15  # Chance cells try to move
        self.competition_strength = 0.8  # How aggressive species competition is

    @property
    def name(self) -> str:
        return "Cellular Net"

    @property
    def description(self) -> str:
        return "Cellular automaton with species competition and migration along the net structure."

    def _build_neighbor_matrix(self, beam_array: np.ndarray):
        """Build precomputed neighbor adjacency matrix using KDTree."""
        n_beams = beam_array.shape[0]

        # Extract positions
        self.positions = beam_array[:, [BeamArrayColumns.X, BeamArrayColumns.Y]]

        # Build KDTree for efficient spatial queries
        self.kdtree = cKDTree(self.positions)

        # Build sparse adjacency matrix
        self.neighbor_matrix = lil_matrix((n_beams, n_beams), dtype=np.bool_)

        # Query all neighbors within radius for each beam
        neighbor_lists = self.kdtree.query_ball_tree(self.kdtree, self.neighbor_radius)

        for i, neighbors in enumerate(neighbor_lists):
            for j in neighbors:
                if i != j:  # Exclude self
                    self.neighbor_matrix[i, j] = True

        # Convert to CSR format for efficient row slicing
        self.neighbor_matrix = self.neighbor_matrix.tocsr()

        print(f"Built neighbor matrix: {n_beams} beams, "
              f"{self.neighbor_matrix.nnz} neighbor relationships")

    def initialize_state(self, beam_array: np.ndarray):
        """Initialize with simple state and precompute neighbors."""
        n_beams = beam_array.shape[0]

        # Build neighbor matrix first time
        if self.neighbor_matrix is None:
            self._build_neighbor_matrix(beam_array)

        # State: [alive, age, species, energy]
        self.state_grid = np.zeros((n_beams, 4), dtype=np.float32)

        # Random seed about 8% of beams with different species clusters
        n_seeds = max(8, n_beams // 12)
        seed_indices = np.random.choice(n_beams, n_seeds, replace=False)

        self.state_grid[seed_indices, 0] = 1
        self.state_grid[seed_indices, 1] = np.random.randint(0, 10, n_seeds)  # Random starting age
        self.state_grid[seed_indices, 2] = np.random.randint(0, self.species_count, n_seeds)
        self.state_grid[seed_indices, 3] = np.random.uniform(0.5, 1.0, n_seeds)  # Starting energy

        self.initialized = True

    def _apply_ca_rules_vectorized(self, beam_array: np.ndarray):
        """Enhanced CA rules with species competition and migration."""
        n_beams = self.state_grid.shape[0]
        new_state = self.state_grid.copy()

        alive = self.state_grid[:, 0] > 0.5
        age = self.state_grid[:, 1]
        species = self.state_grid[:, 2].astype(int)
        energy = self.state_grid[:, 3]

        # Age all living cells and consume energy
        new_state[alive, 1] = age[alive] + 1
        new_state[alive, 3] = np.maximum(0, energy[alive] - 0.02)  # Energy decay

        # Kill old or low-energy cells
        death_mask = alive & ((age > self.max_age) | (energy < 0.1))
        new_state[death_mask, 0] = 0
        new_state[death_mask, 1] = 0
        new_state[death_mask, 3] = 0

        # Get neighbor information for all species
        alive_by_species = np.zeros((n_beams, self.species_count), dtype=np.float32)
        for s in range(self.species_count):
            species_mask = alive & (species == s)
            alive_by_species[:, s] = self.neighbor_matrix.dot(species_mask.astype(np.float32))

        total_neighbors = np.sum(alive_by_species, axis=1)

        # Species competition - cells with many different-species neighbors get stressed
        for i in range(n_beams):
            if alive[i]:
                my_species = species[i]
                enemy_neighbors = total_neighbors[i] - alive_by_species[i, my_species]

                if enemy_neighbors > alive_by_species[i, my_species]:  # Outnumbered
                    stress = enemy_neighbors * self.competition_strength
                    death_prob = np.minimum(0.4, stress * 0.1)

                    if np.random.random() < death_prob:
                        new_state[i, 0] = 0  # Dies from competition
                        new_state[i, 1] = 0
                        new_state[i, 3] = 0

        # Migration - living cells try to move to better positions
        migration_candidates = alive & (np.random.random(n_beams) < self.migration_prob)

        for i in np.where(migration_candidates)[0]:
            # Find neighboring empty spots
            neighbors = np.array(self.neighbor_matrix[i].nonzero()[1])
            empty_neighbors = neighbors[~alive[neighbors]]

            if len(empty_neighbors) > 0:
                # Choose best empty spot (least competition)
                best_spot = None
                min_enemies = float('inf')

                for spot in empty_neighbors:
                    my_species = species[i]
                    enemy_count = total_neighbors[spot] - alive_by_species[spot, my_species]

                    if enemy_count < min_enemies:
                        min_enemies = enemy_count
                        best_spot = spot

                # Move if we found a better spot
                if best_spot is not None and min_enemies < total_neighbors[i] - alive_by_species[i, species[i]]:
                    # Move to new position
                    new_state[best_spot, :] = new_state[i, :]
                    new_state[best_spot, 3] *= 0.9  # Migration costs energy

                    # Clear old position
                    new_state[i, 0] = 0
                    new_state[i, 1] = 0
                    new_state[i, 3] = 0

        # Birth rule - empty spots with friendly neighbors
        dead = new_state[:, 0] < 0.5

        for i in np.where(dead)[0]:
            if total_neighbors[i] >= 2:
                # Find dominant species among neighbors
                dominant_species = np.argmax(alive_by_species[i])
                dominant_count = alive_by_species[i, dominant_species]

                if dominant_count >= 2:  # Need at least 2 of same species
                    # Birth probability based on species concentration
                    concentration = dominant_count / max(1, total_neighbors[i])
                    birth_prob = concentration * 0.3

                    if np.random.random() < birth_prob:
                        new_state[i, 0] = 1
                        new_state[i, 1] = 0
                        new_state[i, 2] = dominant_species
                        new_state[i, 3] = 0.8  # Born with good energy

        # Environmental waves - occasional mass extinctions/births
        if self.generation % 200 == 0 and np.random.random() < 0.3:
            # Environmental catastrophe
            disaster_prob = 0.4
            disaster_mask = alive & (np.random.random(n_beams) < disaster_prob)
            new_state[disaster_mask, 0] = 0
            new_state[disaster_mask, 1] = 0
            new_state[disaster_mask, 3] = 0

        elif self.generation % 150 == 0 and np.random.random() < 0.2:
            # Resource boom - energy boost for survivors
            new_state[alive, 3] = np.minimum(1.0, new_state[alive, 3] + 0.3)

        self.state_grid = new_state
        self.generation += 1

    def evaluate(self, beam_array: np.ndarray, t: float) -> np.ndarray:
        """Fast evaluation with precomputed structures."""
        n_beams = beam_array.shape[0]
        oklch_output = np.zeros((n_beams, 3), dtype=np.float32)

        if not self.initialized:
            self.initialize_state(beam_array)

        # Update automaton
        if t - self.last_update_time >= self.update_interval:
            self._apply_ca_rules_vectorized(beam_array)
            self.last_update_time = t

        alive = self.state_grid[:, 0] > 0.5
        age = self.state_grid[:, 1]
        species = self.state_grid[:, 2].astype(int)
        energy = self.state_grid[:, 3]

        # Species colors with more distinct hues
        species_hues = np.array([15, 120, 200, 280])  # Red, Green, Blue, Purple

        # Dead cells - very dim with slight color variation
        oklch_output[:, 0] = 0.05 + 0.02 * np.sin(t * 2 + beam_array[:, BeamArrayColumns.THETA])
        oklch_output[:, 1] = 0.02
        oklch_output[:, 2] = 30 + 60 * np.sin(t * 0.5)  # Slow color drift for background

        # Living cells - brightness based on energy, pulse based on age
        age_pulse = 0.8 + 0.3 * np.sin(age[alive] * 0.5 + t * 3)
        energy_brightness = 0.4 + 0.5 * energy[alive]

        oklch_output[alive, 0] = age_pulse * energy_brightness
        oklch_output[alive, 1] = 0.35 + 0.1 * energy[alive]  # More saturated with higher energy
        oklch_output[alive, 2] = species_hues[species[alive]]

        # Add subtle competitive stress indicators
        if hasattr(self, 'neighbor_matrix') and self.neighbor_matrix is not None:
            # Cells under stress flicker slightly
            stress_flicker = 1 + 0.1 * np.sin(t * 8)
            oklch_output[alive, 0] *= stress_flicker

        return oklch_output