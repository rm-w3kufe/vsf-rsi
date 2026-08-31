#!/usr/bin/env python3
"""
_rsi_gen_failing_pred — Edge case predicate
Generated: 2026-08-31T01:45:52Z
Purpose: Auto-generated from 4 errors on failing_pred
"""

from typing import Dict, Any


def _rsi_gen_failing_pred(ctx: Dict[str, Any]) -> bool:
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
PREDICATE = {
    "name": "_rsi_gen_failing_pred",
    "function": _rsi_gen_failing_pred,
    "type": "edge_case",
    "generated": "2026-08-31T01:45:52Z",
    "purpose": "Auto-generated from 4 errors on failing_pred"
}
