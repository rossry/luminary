# Version Control Guidelines

## Graphite Workflow Requirements

**MUST use Graphite to commit small units of work to their own branches in a stack.**

### Branch Naming Convention

**CRITICAL**: Branches MUST be named based on their hierarchy, showing feature dependencies.

#### Correct Branch Naming Examples
- Base feature: `foundation`
- Stacked feature: `foundation/geometry` (geometry depends on foundation)  
- Further stacked: `foundation/geometry/triangles` (triangles depend on geometry)

#### Incorrect Branch Naming
- ❌ `feat/foundation` (do NOT prefix with `feat/`)
- ❌ `feature/geometry` (do NOT prefix with `feature/`)
- ❌ `geometry` (does NOT show dependency on foundation)

### Stack Structure Philosophy

Each branch represents a complete, coherent unit of work that can be:
- Reviewed independently
- Tested independently  
- Merged when ready

The hierarchical naming (`/` separator) shows the dependency relationship in the stack.

### Workflow Steps

1. **Complete a logical unit of work**
2. **Create appropriately named branch** following hierarchy
3. **Commit the work** to that branch
4. **Create next branch** stacked on the previous one
5. **Continue development** on the new branch

### Example Stack for SVG Pentagon Project

```
foundation                    # Point class, SVG utilities, base classes
└── foundation/geometry       # Triangle calculations, orientation detection  
    └── foundation/geometry/assembly    # Net class, final SVG generation
```

## When to Create a New Branch

Consider creating a new branch when:
- You've completed a logical, testable unit of work
- The next work represents a different aspect/layer of functionality
- The current work provides a stable foundation for subsequent features

This ensures clean, reviewable commits and maintains clear feature boundaries.