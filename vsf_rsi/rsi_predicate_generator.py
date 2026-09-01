#!/usr/bin/env python3
"""
RSI Predicate Generator — Generates new predicates
Creates Python predicates based on detected patterns.

RSI LEVEL 3: AUTO-GENERATION
- Generate new predicates
- Create edge case handlers
- Build optimized predicates
- Register in system
"""

import ast
import json
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional
from pathlib import Path

# ── Configuration ────────────────────────────────────────────────────
PREDICATES_DIR = Path(__file__).parent
GENERATED_DIR = PREDICATES_DIR / "generated"
MANIFEST_FILE = Path(__file__).parent.parent / "docs" / "rsi_generated_predicates.vsm"


class RSIPredicateGenerator:
    """Generates new predicates based on patterns."""
    
    def __init__(self):
        """Initialize predicate generator."""
        self.predicates_dir = PREDICATES_DIR
        self.generated_dir = GENERATED_DIR
        self.generated_dir.mkdir(parents=True, exist_ok=True)
        
    def generate_predicate(self, pattern: Dict, base_predicate: Optional[str] = None) -> str:
        """
        Generate a new predicate based on pattern.
        DEBT-006: Validates generated code before writing.
        
        Args:
            pattern: Detected pattern
            base_predicate: Optional base predicate to extend
        
        Returns:
            Path to generated predicate
        
        Raises:
            ValueError: If generated code is invalid
        """
        # Generate predicate content
        predicate_content = self._create_predicate_content(pattern, base_predicate)
        
        # DEBT-006: Validate generated code before writing
        validation_result = self._validate_code(predicate_content)
        if not validation_result["valid"]:
            raise ValueError(f"Generated code is invalid: {validation_result['error']}")
        
        # Generate filename
        predicate_name = pattern.get("name", "auto_generated")
        filename = f"{predicate_name}.py"
        filepath = self.generated_dir / filename
        
        # Write predicate
        with open(filepath, 'w') as f:
            f.write(predicate_content)
        
        # Register in manifest
        self._register_predicate(predicate_name, filepath, pattern)
        
        return str(filepath)
    
    def _validate_code(self, code: str) -> Dict:
        """
        DEBT-006: Validate generated Python code.
        
        Args:
            code: Python code to validate
        
        Returns:
            Dict with 'valid' bool and 'error' message if invalid
        """
        try:
            # Try to parse the code
            ast.parse(code)
            return {"valid": True, "error": None}
        except SyntaxError as e:
            return {"valid": False, "error": f"Syntax error: {e}"}
        except Exception as e:
            return {"valid": False, "error": f"Validation error: {e}"}
    
    def _create_predicate_content(self, pattern: Dict, base_predicate: Optional[str]) -> str:
        """Create predicate content based on pattern."""
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        predicate_name = pattern.get("name", "auto_generated")
        purpose = pattern.get("purpose", "Auto-generated predicate")

        # Use context-aware template when pattern has historical data
        avg_threshold = pattern.get("avg_threshold")
        avg_input = pattern.get("avg_input")
        error_class = pattern.get("error_class", "unknown")

        if avg_threshold is not None and avg_input is not None:
            return self._create_context_aware_predicate(
                predicate_name, purpose, timestamp,
                avg_threshold=float(avg_threshold),
                avg_input=float(avg_input),
                error_class=error_class,
                base_predicate=base_predicate or "",
            )

        # Fallback to static templates
        if pattern.get("template") == "edge_case_predicate":
            return self._create_edge_case_predicate(predicate_name, purpose, timestamp)
        elif pattern.get("template") == "fast_predicate":
            return self._create_fast_predicate(predicate_name, purpose, timestamp)
        else:
            return self._create_generic_predicate(predicate_name, purpose, timestamp)
    
    def _create_edge_case_predicate(self, name: str, purpose: str, timestamp: str) -> str:
        """Create edge case predicate."""
        return f'''#!/usr/bin/env python3
"""
{name} — Edge case predicate
Generated: {timestamp}
Purpose: {purpose}
"""

from typing import Dict, Any


def {name}(ctx: Dict[str, Any]) -> bool:
    """
    Edge case predicate for handling misclassifications.
    
    Args:
        ctx: Context dictionary
    
    Returns:
        True if edge case detected
    """
    # Edge case 1: Very high values
    if ctx.get("value", 0) > 0.95:
        return True
    
    # Edge case 2: Very low values
    if ctx.get("value", 0) < 0.05:
        return True
    
    # Edge case 3: Borderline values
    if 0.45 <= ctx.get("value", 0) <= 0.55:
        return True
    
    # Edge case 4: Rapid changes
    if ctx.get("rate_of_change", 0) > 0.1:
        return True
    
    return False


# Register predicate
PREDICATE = {{
    "name": "{name}",
    "function": {name},
    "type": "edge_case",
    "generated": "{timestamp}",
    "purpose": "{purpose}"
}}
'''

    def _create_context_aware_predicate(self, name: str, purpose: str, timestamp: str,
                                         avg_threshold: float = 0.5,
                                         avg_input: float = 0.5,
                                         error_class: str = "unknown",
                                         base_predicate: str = "") -> str:
        """Create a context-aware predicate using pattern data.

        Uses avg_threshold and avg_input from historical errors to set
        dynamic thresholds instead of hardcoded values.

        Args:
            name: Predicate function name
            purpose: What this predicate does
            timestamp: Generation timestamp
            avg_threshold: Average threshold from past errors (for calibration)
            avg_input: Average input value from past errors (for calibration)
            error_class: Classification of the error pattern
            base_predicate: Original predicate that was failing
        """
        # Derive thresholds from observed data with safety margins
        # If avg_input was near avg_threshold, the predicate was borderline
        margin = 0.1  # 10% safety margin
        low_bound = max(0.0, avg_threshold - margin)
        high_bound = min(1.0, avg_threshold + margin)

        # Determine detection strategy based on error class
        if error_class == "false_positive":
            # Predicate was too aggressive — detect when input is safely above threshold
            strategy = f"""
    # Strategy: false_positive recovery — only flag when input clearly exceeds threshold
    # Historical avg_input={avg_input:.3f}, avg_threshold={avg_threshold:.3f}
    value = ctx.get("value", 0)
    if value > {high_bound:.3f}:
        return True  # Clearly above threshold
    return False"""
        elif error_class == "false_negative":
            # Predicate was too conservative — detect when input is near or below threshold
            strategy = f"""
    # Strategy: false_negative recovery — flag borderline and below-threshold inputs
    # Historical avg_input={avg_input:.3f}, avg_threshold={avg_threshold:.3f}
    value = ctx.get("value", 0)
    if value < {low_bound:.3f}:
        return True  # Clearly below threshold
    if {low_bound:.3f} <= value <= {high_bound:.3f}:
        return True  # Borderline zone — was causing misses
    return False"""
        else:
            # Unknown error class — use generic boundary detection
            strategy = f"""
    # Strategy: generic boundary detection
    # Historical avg_input={avg_input:.3f}, avg_threshold={avg_threshold:.3f}
    value = ctx.get("value", 0)
    if value < {low_bound:.3f} or value > {high_bound:.3f}:
        return True  # Outside safe zone
    return False"""

        return f'''#!/usr/bin/env python3
"""
{name} — Context-aware predicate
Generated: {timestamp}
Purpose: {purpose}
Error class: {error_class}
Base predicate: {base_predicate}
Calibrated from: avg_threshold={avg_threshold:.3f}, avg_input={avg_input:.3f}
"""

from typing import Dict, Any


def {name}(ctx: Dict[str, Any]) -> bool:
    """
    Context-aware predicate calibrated from historical error patterns.

    Args:
        ctx: Context dictionary with 'value' key

    Returns:
        True if the pattern indicates this predicate should trigger
    """
    if "value" not in ctx:
        return False  # No data to evaluate

    {strategy}


# Register predicate
PREDICATE = {{
    "name": "{name}",
    "function": {name},
    "type": "context_aware",
    "generated": "{timestamp}",
    "purpose": "{purpose}",
    "error_class": "{error_class}",
    "avg_threshold": {avg_threshold},
    "avg_input": {avg_input},
    "base_predicate": "{base_predicate}",
}}
'''
    
    def _create_fast_predicate(self, name: str, purpose: str, timestamp: str) -> str:
        """Create fast predicate."""
        return f'''#!/usr/bin/env python3
"""
{name} — Fast execution predicate
Generated: {timestamp}
Purpose: {purpose}
"""

from typing import Dict, Any


def {name}(ctx: Dict[str, Any]) -> bool:
    """
    Fast execution predicate with minimal overhead.
    
    Args:
        ctx: Context dictionary
    
    Returns:
        True if condition met
    """
    # Optimized: single comparison
    return ctx.get("value", 0) > 0.7


# Register predicate
PREDICATE = {{
    "name": "{name}",
    "function": {name},
    "type": "fast",
    "generated": "{timestamp}",
    "purpose": "{purpose}"
}}
'''
    
    def _create_generic_predicate(self, name: str, purpose: str, timestamp: str) -> str:
        """Create generic predicate."""
        return f'''#!/usr/bin/env python3
"""
{name} — Auto-generated predicate
Generated: {timestamp}
Purpose: {purpose}
"""

from typing import Dict, Any


def {name}(ctx: Dict[str, Any]) -> bool:
    """
    Auto-generated predicate.
    
    Args:
        ctx: Context dictionary
    
    Returns:
        True if condition met
    """
    # Default implementation
    return ctx.get("active", False)


# Register predicate
PREDICATE = {{
    "name": "{name}",
    "function": {name},
    "type": "generic",
    "generated": "{timestamp}",
    "purpose": "{purpose}"
}}
'''
    
    def _register_predicate(self, name: str, filepath: Path, pattern: Dict) -> None:
        """Register predicate in manifest."""
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        
        # Load existing manifest
        manifest = self._load_manifest()
        
        # Add new entry
        manifest["predicates"].append({
            "name": name,
            "path": str(filepath),
            "generated": timestamp,
            "pattern_type": pattern.get("type", "unknown"),
            "purpose": pattern.get("purpose", ""),
            "status": "active"
        })
        
        # Save manifest
        self._save_manifest(manifest)
    
    def _load_manifest(self) -> Dict:
        """Load manifest from file."""
        from vsf_rsi.rsi_manifest_parser import load_manifest
        if MANIFEST_FILE.exists():
            return load_manifest(MANIFEST_FILE)
        return {"predicates": []}
    
    def _save_manifest(self, manifest: Dict) -> None:
        """Save manifest to file."""
        # Skip if manifest directory doesn't exist (package mode)
        if not MANIFEST_FILE.parent.exists():
            return
        from vsf_rsi.rsi_manifest_parser import save_manifest
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        save_manifest(MANIFEST_FILE, "predicates", manifest["predicates"],
                      "rsi_generated_predicates", timestamp)
    
    def get_generated_predicates(self) -> List[Dict]:
        """Get list of generated predicates."""
        manifest = self._load_manifest()
        return manifest.get("predicates", [])


# ── CLI Interface ────────────────────────────────────────────────────
def main():
    """CLI interface for RSI predicate generator."""
    import argparse
    
    parser = argparse.ArgumentParser(description="RSI Predicate Generator")
    subparsers = parser.add_subparsers(dest="command")
    
    # Generate command
    generate_parser = subparsers.add_parser("generate", help="Generate predicate")
    generate_parser.add_argument("name", help="Predicate name")
    generate_parser.add_argument("--purpose", default="Auto-generated predicate", help="Purpose")
    generate_parser.add_argument("--template", choices=["edge_case", "fast", "generic"], default="generic", help="Template")
    
    # List command
    subparsers.add_parser("list", help="List generated predicates")
    
    args = parser.parse_args()
    generator = RSIPredicateGenerator()
    
    if args.command == "generate":
        pattern = {
            "name": args.name,
            "purpose": args.purpose,
            "template": f"{args.template}_predicate"
        }
        filepath = generator.generate_predicate(pattern)
        print(f"Generated predicate: {filepath}")
    elif args.command == "list":
        predicates = generator.get_generated_predicates()
        print(f"Generated predicates: {len(predicates)}")
        for predicate in predicates:
            print(f"  {predicate['name']}: {predicate['path']}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
