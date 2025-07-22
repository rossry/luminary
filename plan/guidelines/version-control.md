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

## Creating New Branches

When creating new branches with Graphite, always use the `--no-interactive` flag to avoid interactive prompts:

```bash
# Correct - non-interactive branch creation
gt create foundation/new-feature/_ --no-interactive

# Avoid - will trigger interactive prompts for staging decisions
gt create foundation/new-feature/_
```

This prevents interruption of automated workflows and scripted operations.

## How to "Release into Parent"

**"Release into parent"** means integrating a completed subbranch into its parent branch with a squash merge.

### Step-by-Step Process

1. **Ensure you're on the subbranch** that needs to be released
2. **Use Graphite fold command**: `gt fold`
3. **Check commit message immediately**: `git log -1`
4. **Fix commit message if needed** (see section below)
5. **Verify the integration** is complete

### Example Release Process
```bash
# 1. On subbranch foundation/initial-configs/fix-mypy/_
gt fold

# 2. Check the commit message
git log -1

# 3. Fix if needed (see format requirements below)
git commit --amend -m "foundation/initial-configs/fix-mypy/_: description"

# 4. Verify - should now be on parent branch with changes integrated
```

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

### Important: gt fold Commit Message Fix

**CRITICAL**: When using `gt fold`, the automatic commit message often does NOT follow the required format above. 

**Required Post-Fold Process:**
1. After `gt fold` completes, immediately check the commit message: `git log -1`
2. If the message doesn't follow the `{subbranch-name}: {description}` format, **immediately amend it**:
   ```bash
   git commit --amend -m "{subbranch-name}: {description}
   
   {detailed description of integrated functionality}"
   ```
3. Verify the corrected message: `git log -1`

**Example of fixing incorrect fold message:**
```bash
# After gt fold, if you see:
# "feat: create branch to fix mypy module path issues"
# 
# Fix it immediately:
git commit --amend -m "foundation/initial-configs/fix-mypy/_: fix mypy module path resolution issues

Remove problematic module conflicts, add pyproject.toml configuration, 
enable proper module resolution, and fix test expectations."
```

## Squashing Commits Before Folding

**CRITICAL**: When you have multiple commits on a subbranch that should be combined into a single logical unit, you MUST squash them BEFORE folding into the parent branch.

### When to Squash Before Folding

Squash commits when:
- Multiple commits represent a single feature or fix (incremental development)
- Commit messages are work-in-progress or don't follow proper format
- You want a clean, single commit representing the entire subbranch work
- The subbranch contains "checkpoint" commits that aren't meaningful individually

### How to Squash Before Folding

**Method 1: Interactive Rebase (Safest)**
```bash
# 1. Find the commit BEFORE your first commit to squash
git log --oneline -10
# Example: want to squash from bb40616 onwards, so rebase from 6e5a1da

# 2. Start interactive rebase 
git rebase -i 6e5a1da

# 3. In the editor, change 'pick' to 'squash' (or 's') for all commits except the first:
# pick bb40616 feat: implement 5A-35 net with triangle edge rendering
# squash 0fb8824 refactor: rewrite 5A-35 generation using programmatic layers  
# squash b64c0ce feat: complete 5A-35 with layer4 outer triangles
# squash 4e71e10 foundation/initial-configs/fix-mypy/_: fix mypy module path
# squash b272048 feat: add asymmetric pentagon configurations 4A-31 and 4A-35
# squash e0e8037 refactor: optimize viewBox dimensions for all pentagon configurations

# 4. Save and exit, then write proper commit message in next editor
```

**Method 2: Git Reset (When Interactive Rebase is Risky)**
```bash
# 1. Find the commit BEFORE your first commit to squash
git log --oneline -10

# 2. Soft reset to that commit (keeps changes staged)
git reset --soft 6e5a1da

# 3. Create single new commit with proper message
git commit -m "foundation/initial-configs/_: add complete pentagon configuration system

Implements comprehensive pentagon star pattern generation with asymmetric extensions...

🤖 Generated with [Claude Code](https://claude.ai/code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

### Complete Squash-Then-Fold Workflow

```bash
# 1. On your subbranch, squash commits (using either method above)
git rebase -i <base-commit>  # or git reset --soft <base-commit>

# 2. Verify the squashed commit looks good
git log -1

# 3. Now fold into parent branch
gt fold

# 4. Check and fix fold commit message if needed
git log -1
git commit --amend -m "..." # if needed
```

### Why This Order Matters

- **Cleaner history**: Parent branch gets one meaningful commit per subbranch
- **Better commit messages**: You control the final message instead of relying on fold's automatic behavior
- **Easier to review**: Single commit shows complete feature/fix scope
- **Safer recovery**: If fold goes wrong, you have a clean commit to work with

**NEVER fold first then try to fix history** - it's much more complex and error-prone.