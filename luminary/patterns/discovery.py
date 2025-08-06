"""Pattern discovery and selection system."""

import importlib.util
import inspect
from pathlib import Path
from typing import Dict, List, Tuple, Type, Optional

from .base import LuminaryPattern


def discover_patterns(patterns_dir: str = "patterns") -> Dict[str, Type[LuminaryPattern]]:
    """Auto-discover patterns from pattern files.
    
    Args:
        patterns_dir: Directory containing pattern files (relative to project root)
    
    Returns:
        Dictionary mapping pattern filename to pattern class
        e.g., {"ripple": RipplePattern, "spiral": SpiralPattern}
    """
    patterns = {}
    patterns_path = Path(patterns_dir)
    
    if not patterns_path.exists():
        return patterns
    
    # Find all Python files in patterns directory
    for pattern_file in patterns_path.glob("*.py"):
        if pattern_file.name.startswith("_"):
            continue  # Skip private/internal files
            
        pattern_name = pattern_file.stem
        
        try:
            # Load the module
            spec = importlib.util.spec_from_file_location(pattern_name, pattern_file)
            if spec is None or spec.loader is None:
                continue
                
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # Find LuminaryPattern subclasses in the module
            for name, obj in inspect.getmembers(module, inspect.isclass):
                if (issubclass(obj, LuminaryPattern) and 
                    obj is not LuminaryPattern and
                    obj.__module__ == module.__name__):
                    patterns[pattern_name] = obj
                    break
                    
        except Exception as e:
            # Skip patterns that fail to load
            print(f"Warning: Failed to load pattern '{pattern_name}': {e}")
            continue
    
    return patterns


def get_pattern_choices() -> List[Tuple[str, str, str]]:
    """Get available patterns for interactive selection.
    
    Returns:
        List of tuples (filename, name, description) for each pattern
    """
    patterns = discover_patterns()
    choices = []
    
    for filename, pattern_class in patterns.items():
        try:
            # Instantiate to get name and description
            instance = pattern_class()
            choices.append((filename, instance.name, instance.description))
        except Exception as e:
            # Handle patterns that can't be instantiated
            choices.append((filename, filename.title(), f"Error: {e}"))
    
    return sorted(choices, key=lambda x: x[0])  # Sort by filename


def interactive_pattern_selection() -> str:
    """Show multiple choice menu for pattern selection.
    
    Returns:
        Selected pattern filename
        
    Raises:
        KeyboardInterrupt: If user cancels selection
        ValueError: If no patterns are available
    """
    choices = get_pattern_choices()
    
    if not choices:
        raise ValueError("No patterns found in patterns/ directory")
    
    print("\nAvailable patterns:")
    for i, (filename, name, description) in enumerate(choices, 1):
        print(f"[{i}] {name} - {description}")
    
    while True:
        try:
            selection = input(f"\nSelect pattern (1-{len(choices)}): ").strip()
            
            if not selection:
                continue
                
            choice_num = int(selection)
            if 1 <= choice_num <= len(choices):
                selected_filename = choices[choice_num - 1][0]
                print(f"Selected: {choices[choice_num - 1][1]}")
                return selected_filename
            else:
                print(f"Please enter a number between 1 and {len(choices)}")
                
        except ValueError:
            print("Please enter a valid number")
        except KeyboardInterrupt:
            print("\nSelection cancelled")
            raise


def load_pattern(pattern_name: str) -> LuminaryPattern:
    """Load a specific pattern by filename.
    
    Args:
        pattern_name: Pattern filename (without .py extension)
        
    Returns:
        Instantiated pattern object
        
    Raises:
        ValueError: If pattern not found or cannot be loaded
    """
    patterns = discover_patterns()
    
    if pattern_name not in patterns:
        available = list(patterns.keys())
        raise ValueError(f"Pattern '{pattern_name}' not found. Available patterns: {available}")
    
    try:
        return patterns[pattern_name]()
    except Exception as e:
        raise ValueError(f"Failed to instantiate pattern '{pattern_name}': {e}")


def get_pattern_or_select(pattern_name: Optional[str]) -> LuminaryPattern:
    """Load specified pattern or show interactive selection.
    
    Args:
        pattern_name: Pattern filename, or None for interactive selection
        
    Returns:
        Instantiated pattern object
    """
    if pattern_name:
        return load_pattern(pattern_name)
    else:
        selected_name = interactive_pattern_selection()
        return load_pattern(selected_name)