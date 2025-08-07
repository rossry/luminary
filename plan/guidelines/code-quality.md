# Code Quality Guidelines

## Mandatory Code Quality Tools

These tools MUST be used for all code in this repository:

### Black Code Formatting
- **MUST use black to format all Python code**
- **MUST call black on a file immediately after writing to it**
- Run: `black <filename.py>`

### MyPy Type Checking
- **MUST use mypy to check code for type errors**
- **MUST call mypy at the same time as running tests**
- Run: `python -m mypy <filename.py> --explicit-package-bases`

### Testing with PyTest
- **MUST run pytest to validate functionality**
- **MUST run mypy alongside pytest for complete validation**
- Run: `python -m pytest <test_file.py> -v && python -m mypy <source_file.py> --explicit-package-bases`

## Workflow for Every Code Change

1. **Write/edit code** in the appropriate file
2. **Format with black** immediately after writing
3. **Run tests with pytest** to verify functionality 
4. **Run mypy** at the same time as tests for type checking
5. **Mark todo as completed** only after all checks pass

## Example Commands

```bash
# After writing code
black luminary/geometry/point.py

# Validation
python -m pytest tests/geometry/test_point.py -v && python -m mypy luminary/geometry/point.py --explicit-package-bases
```

This ensures code quality and type safety throughout the implementation.