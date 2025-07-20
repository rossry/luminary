# Collaboration Guidelines

## Claude Code & Human Developer Workflow

When Claude Code is working with a human developer on a feature, follow these steps systematically:

### 1. Understand the Codebase
- Read the entire codebase around the target region
- Ensure complete understanding of the existing implementation
- Ask questions to confirm understanding before proceeding

### 2. Form and Present Plan
- Think about what you're trying to accomplish
- Form a comprehensive plan for implementation
- **Do not begin writing code**
- Describe your plan to the human developer
- Only proceed after the human developer has read and approved the plan

### 3. Consider Feature Decomposition
- Evaluate whether the feature should be broken into sub-features
- Stacking with Graphite makes feature decomposition easy
- Ask the human developer if you are unsure about decomposition
- If decomposition is needed:
  - Create a child branch according to the guidelines
  - Enter that branch
  - Proceed with the planning process for the sub-feature

### 4. Draft Code for Review
- Once you have an approved plan and appropriate branch:
  - Begin drafting the code
  - **Do not write directly to files**
  - Present your drafts to the human developer for discussion and suggestions
  - Only write changes to files after human developer approval

### 5. Test and Validate Changes
- After making changes (or completing a functional block):
  - Re-run tests and carefully consider the output
  - Remember: Code doesn't always need to change to make tests pass
  - Tests may need to be updated to reflect intentional behavior changes
  - Consult the human developer when uncertain about test outcomes

### 6. Add Test Coverage
- Immediately after writing code, consider adding tests
- We use pytest for testing
- Identify what tests should be added to cover new code
- Look for any gaps in test coverage discovered during development
- Confirm test plans with the human developer before implementation
- Add approved tests and re-run the test suite
- Ensure tests pass deterministically

### 7. Update Documentation
- Once feature and tests are completed:
  - Update documentation in `plan/` to reflect changes
  - Reflect on any new tasks uncovered during development
  - Add new tasks to `plan/` as appropriate
  - Complete documentation updates before committing (same commit)

### 8. Submit and Review
- Confirm with human developer that they want to submit the branch/stack
- When approved, use Graphite to submit
- Ask whether to submit as draft or ready to merge
- Consider branch consolidation:
  - Can completed branches be folded into their parent?
  - Can branches parented to `main` be merged?
  - Ask human developer when unsure

## Key Principles
- Never proceed without human approval at each major step
- Prioritize understanding over speed
- Maintain clear communication throughout the process
- Use Graphite's stacking capabilities for complex features
- Keep documentation synchronized with code changes

## Recording Important Instructions
When a human developer emphasizes that an instruction is "very important":
- Consider whether the instruction should be recorded in these guidelines
- Important instructions that apply to all future Claude Code assistants should be documented
- Add such instructions to the appropriate guideline file in `plan/guidelines/`
- This ensures reliable retention and consistent application across all future collaborations