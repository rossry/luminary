# Version Control Guidelines

## Graphite Workflow Requirements

**MUST use Graphite to commit small units of work to their own branches in a stack.**

### Branch Naming Convention

**CRITICAL**: Branches MUST be named based on their hierarchy, showing feature dependencies.
**REQUIRED**: All branch names MUST end with `/_` to avoid Git filesystem conflicts.

#### Correct Branch Naming Examples
- Base feature: `foundation/_`
- Stacked feature: `foundation/geometry/_` (geometry depends on foundation)  
- Further stacked: `foundation/geometry/triangles/_` (triangles depend on geometry)

#### Incorrect Branch Naming
- ❌ `feat/foundation` (do NOT prefix with `feat/`)
- ❌ `feature/geometry` (do NOT prefix with `feature/`)
- ❌ `geometry` (does NOT show dependency on foundation)
- ❌ `foundation` (missing required `/_` suffix)
- ❌ `foundation/geometry` (missing required `/_` suffix)

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
foundation/_                         # Point class, SVG utilities, base classes
└── foundation/geometry/_            # Triangle calculations, orientation detection  
    └── foundation/geometry/assembly/_   # Net class, final SVG generation
```

## When to Create a New Branch

Consider creating a new branch when:
- You've completed a logical, testable unit of work
- The next work represents a different aspect/layer of functionality
- The current work provides a stable foundation for subsequent features

This ensures clean, reviewable commits and maintains clear feature boundaries.

## Branch Folding and Release Guidelines

When "releasing" a subbranch into its parent (non-trunk) branch, follow these guidelines:

### Squash vs Keep Commits

- **Use `gt fold --squash`** when integrating a completed subbranch
- **Use `gt fold --keep`** only when preserving detailed development history is important

### Squash Commit Message Format

When squashing a subbranch, use this commit message format:

```
{subbranch-name}: {one-line description of the complete feature}

{Optional detailed description of the integrated functionality}
```

**Examples:**
```
foundation/geometry/_: implement complete geometric processing and SVG generation

Adds Triangle, Kite, and Net classes with JSON parsing, geometric calculations,
and SVG output capabilities. Includes comprehensive validation system and
CLI interface for generating SVG diagrams from JSON configurations.
```

**Do NOT use conventional commit prefixes** (feat:, fix:, etc.) for squashed subbranch integration. The subbranch name provides the context and scope.