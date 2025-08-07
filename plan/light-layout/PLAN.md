# Light Layout Implementation Plan

## Branch Structure and Dependencies

```
foundation/light-layout/_
├── foundation/light-layout/update-schema/_
├── foundation/light-layout/beam-geometry/_  
├── foundation/light-layout/support-extended-svg/_
├── foundation/light-layout/support-layout-overrides/_
└── foundation/light-layout/cleanup/_
```

### Dependency Chain
1. **update-schema** → Independent (foundation work)
2. **beam-geometry** → Depends on update-schema 
3. **support-extended-svg** → Depends on beam-geometry
4. **support-layout-overrides** → Depends on beam-geometry
5. **cleanup** → Depends on all previous branches

## Phase 1: Schema Updates (`foundation/light-layout/update-schema/_`)

### Objectives
- Rename "kite" → "facet" throughout codebase
- Extend JSON schema to support beam configuration
- Maintain backwards compatibility

### Implementation Steps

#### 1.1 Terminology Migration
- [ ] Update `luminary/geometry/kite.py` → `luminary/geometry/facet.py`
- [ ] Rename `Kite` class → `Facet` class
- [ ] Update all imports and references throughout codebase
- [ ] Update variable names: `kite` → `facet`, `kites` → `facets`
- [ ] Update comments and documentation strings

#### 1.2 Schema Extensions  
- [ ] Add `default_beam_counts` field to main config schema
- [ ] Define canonical edge ordering enum in `Facet` class
- [ ] Create `.layout.json` schema specification
- [ ] Update existing config files with default beam counts

#### 1.3 Class Structure Updates
- [ ] Add edge ordering enum to `Facet` class:
  ```python
  class EdgeType(IntEnum):
      MAJOR_STARBOARD = 0
      MINOR_STARBOARD = 1  
      MINOR_PORT = 2
      MAJOR_PORT = 3
  ```

### Testing
- [ ] Update all existing unit tests for terminology changes
- [ ] Verify backwards compatibility with existing configs
- [ ] Test schema validation for new fields

### Deliverables
- Complete "kite" → "facet" migration
- Extended schema supporting beam configuration
- Updated configuration files

---

## Phase 2: Beam Geometry (`foundation/light-layout/beam-geometry/_`)

### Objectives
- Implement `Beam` class with geometric subdivision
- Create beam generation algorithms
- Handle complex 5-sided beam cases

### Implementation Steps

#### 2.1 Beam Class Creation
- [ ] Create `luminary/geometry/beam.py`
- [ ] Implement `Beam` class with properties:
  ```python
  class Beam:
      parent_facet: Facet
      edge_index: int
      beam_index: int
      vertices: List[Point]
      color: str
  ```

#### 2.2 Geometric Algorithms
- [ ] Implement beam boundary calculation:
  - Equal width subdivision along parent edge
  - Perpendicular side boundaries  
  - Top boundary from axis/angle-bisector intersection
- [ ] Handle 5-sided polygons when both boundaries intersect
- [ ] Implement color calculation (parent ±20% based on parity)

#### 2.3 Facet Integration
- [ ] Add beam generation methods to `Facet` class
- [ ] Integrate beam creation into load-time computation
- [ ] Add beam storage and access methods

#### 2.4 Mathematical Utilities
- [ ] Line-line intersection algorithms
- [ ] Point-in-polygon testing for complex cases
- [ ] Color mixing functions (towards white/black)

### Testing
- [ ] Unit tests for beam geometric calculations
- [ ] Edge cases: axis/angle-bisector intersections
- [ ] Color calculation validation
- [ ] Visual verification of beam boundaries

### Deliverables  
- Complete `Beam` class implementation
- Geometric subdivision algorithms
- Integration with existing `Facet` class

---

## Phase 3: Extended SVG Support (`foundation/light-layout/support-extended-svg/_`)

### Objectives
- Implement beam-based SVG rendering
- Add `--extended` CLI flag
- Generate `config_name.extended.svg` output

### Implementation Steps

#### 3.1 SVG Writer Enhancements
- [ ] Extend `luminary/writers/svg/` to support beam rendering
- [ ] Implement beam polygon generation (fills only, no strokes)
- [ ] Preserve existing facet rendering for regular mode

#### 3.2 CLI Integration
- [ ] Add `--extended` flag to `main.py svg` command
- [ ] Update argument parsing and help text
- [ ] Implement extended filename generation logic

#### 3.3 Rendering Pipeline
- [ ] Create beam-specific rendering methods
- [ ] Ensure proper color application
- [ ] Handle complex 5-sided beam polygons  

#### 3.4 Index Generation Updates
- [ ] Modify index command to detect extended SVGs
- [ ] Implement side-by-side display in HTML index
- [ ] Update CSS for dual-display layout

### Testing
- [ ] Extended SVG output validation
- [ ] CLI flag functionality
- [ ] Visual comparison with regular SVG output
- [ ] Index generation with both formats

### Deliverables
- Extended SVG rendering capability
- Enhanced CLI interface
- Updated index generation

---

## Phase 4: Layout Overrides (`foundation/light-layout/support-layout-overrides/_`)

### Objectives  
- Implement `.layout.json` companion file support
- Add facet ID generation system
- Enable per-facet beam count overrides

### Implementation Steps

#### 4.1 Facet ID System
- [ ] Implement facet ID generation: `[series][triangle_index][facet_letter]`
- [ ] Handle DEF → ABC synonym mapping
- [ ] Add ID assignment during net construction

#### 4.2 Layout Override Loading
- [ ] Create layout JSON parsing logic
- [ ] Implement override application to facets
- [ ] Handle missing override files gracefully

#### 4.3 Configuration Integration
- [ ] Integrate override loading into main pipeline
- [ ] Ensure override precedence over defaults
- [ ] Add validation for override format

#### 4.4 Example Configurations
- [ ] Create example `.layout.json` files for existing configs
- [ ] Document override format and capabilities

### Testing
- [ ] Override loading and application
- [ ] Facet ID generation accuracy  
- [ ] Edge cases: missing files, invalid overrides
- [ ] Integration with existing configurations

### Deliverables
- Complete layout override system
- Facet identification framework
- Example override configurations

---

## Phase 5: Cleanup and Integration (`foundation/light-layout/cleanup/_`)

### Objectives
- Ensure complete integration across all systems
- Update documentation and examples
- Performance optimization and final testing

### Implementation Steps

#### 5.1 Integration Testing
- [ ] End-to-end pipeline validation
- [ ] Performance profiling with beam generation
- [ ] Memory usage optimization

#### 5.2 Documentation Updates
- [ ] Update README with new terminology and features
- [ ] Create usage examples for extended SVG
- [ ] Document layout override system

#### 5.3 Example Updates  
- [ ] Update all existing configurations with beam counts
- [ ] Create demonstration layout override files
- [ ] Generate example extended SVGs

#### 5.4 Code Quality
- [ ] Complete type checking with MyPy
- [ ] Run full test suite
- [ ] Code formatting and linting

### Testing
- [ ] Comprehensive regression testing
- [ ] Performance benchmarking
- [ ] User acceptance testing with all features

### Deliverables
- Complete, integrated light layout feature
- Updated documentation and examples  
- Performance-optimized implementation

---

## Success Criteria

### Functional Requirements
- [x] Complete "kite" → "facet" terminology migration
- [ ] Beam subdivision with configurable counts per edge
- [ ] Extended SVG rendering with individual beam visualization
- [ ] Layout override system with companion JSON files
- [ ] Backwards compatibility with existing configurations

### Technical Requirements  
- [ ] All existing tests pass
- [ ] New features have comprehensive test coverage
- [ ] Performance impact < 50% increase in generation time
- [ ] Memory usage remains reasonable for large configurations

### Documentation Requirements
- [ ] Complete API documentation for new classes
- [ ] User guide for extended SVG and layout overrides
- [ ] Migration guide for terminology changes

## Risk Mitigation

### Geometric Complexity
- **Risk**: 5-sided beam calculations may be complex
- **Mitigation**: Implement step-by-step with extensive unit testing

### Performance Impact  
- **Risk**: Beam generation may slow down rendering significantly
- **Mitigation**: Profile early, optimize algorithms, consider caching

### Backwards Compatibility
- **Risk**: Terminology changes may break existing tooling
- **Mitigation**: Maintain alias support where possible, provide migration guide

## Timeline Estimate
- **Phase 1**: 2-3 days (schema and terminology)
- **Phase 2**: 4-5 days (beam geometry - most complex)  
- **Phase 3**: 2-3 days (SVG rendering)
- **Phase 4**: 2-3 days (layout overrides)
- **Phase 5**: 2-3 days (cleanup and integration)

**Total**: 12-17 days estimated development time