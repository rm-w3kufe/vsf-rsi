#!/usr/bin/env python3
"""
_rsi_gen_failing_pred — Context-aware predicate
Generated: 2026-09-01T19:19:41Z
Purpose: Auto-generated from 4 errors on failing_pred
Error class: BLOCKING
Base predicate: failing_pred
Calibrated from: avg_threshold=0.700, avg_input=0.300
"""

from typing import Dict, Any


def _rsi_gen_failing_pred(ctx: Dict[str, Any]) -> bool:
    """
    Context-aware predicate calibrated from historical error patterns.

    Args:
        ctx: Context dictionary with 'value' key

    Returns:
        True if the pattern indicates this predicate should trigger
    """
    if "value" not in ctx:
        return False  # No data to evaluate

    
    # Strategy: generic boundary detection
    # Historical avg_input=0.300, avg_threshold=0.700
    value = ctx.get("value", 0)
    if value < 0.600 or value > 0.800:
        return True  # Outside safe zone
    return False


# Register predicate
PREDICATE = {
    "name": "_rsi_gen_failing_pred",
    "function": _rsi_gen_failing_pred,
    "type": "context_aware",
    "generated": "2026-09-01T19:19:41Z",
    "purpose": "Auto-generated from 4 errors on failing_pred",
    "error_class": "BLOCKING",
    "avg_threshold": 0.7,
    "avg_input": 0.3,
    "base_predicate": "failing_pred",
}
