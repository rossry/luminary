# Developer Guidelines

## Version Control with Graphite

### Branch Organization
- Use graphite (`gt`) for all version control operations
- All changes must be made in stacks, one branch per modular feature
- Branch names must follow hierarchical naming convention

### Branch Naming Convention
```
parent-feature/child-feature/sub-feature/specific-implementation
```

**Examples:**
- `user-auth/validation/tests/unit` (parent: `user-auth/validation/tests`)
- `user-auth/validation/tests` (parent: `user-auth/validation`) 
- `user-auth/validation` (parent: `user-auth`)
- `user-auth` (parent: `main`)

### Branch Hierarchy Rules
- Root feature branches have `main` as their parent
- Each sub-branch must have a clear parent-child relationship
- Branch names should be descriptive and modular
- Use kebab-case for all branch names
- Organize features logically from general to specific

### Stack Management
- Each branch should represent one cohesive, modular feature
- Features should build upon each other in logical sequence
- Maintain clean, linear history within each stack
- Test each branch independently when possible

## Implementation Notes
- As new important development rules are discovered, document them in appropriate files within `plan/guidelines/`
- Keep guidelines updated and accessible to all team members