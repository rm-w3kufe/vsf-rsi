#!/usr/bin/env python3
"""
RSI Scenario Bridge — connects scenario-memory ↔ RSI gap detector.

Bidirectional flow:
  scenario-memory failures → rsi_gap_detector → RSI improvements
  rsi_gap_detector gaps → scenario-memory matching → correction suggestions
"""

import sys
import json
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime, timezone

# scenario-memory is optional (may not be installed)
try:
    import scenario_memory as _sm
    _HAS_SCENARIO_MEMORY = True
except ImportError:
    _sm = None
    _HAS_SCENARIO_MEMORY = False


def _import_scenario_memory():
    """Import scenario_memory from vsf-rsi package."""
    try:
        from vsf_rsi import scenario_memory
        return scenario_memory
    except ImportError as e:
        raise ImportError(f"scenario_memory not available: {e}")


def _import_gap_detector():
    """Import RSIGapDetector from RSI modules."""
    try:
        from vsf_rsi.rsi_gap_detector import RSIGapDetector
        return RSIGapDetector()
    except ImportError as e:
        raise ImportError(f"RSIGapDetector not available: {e}")


def failures_to_gaps(predicate_name: Optional[str] = None) -> Dict:
    """Flow 1: scenario-memory failures → gap signals.

    Reads scenario-memory for quality='fail' scenarios and converts
    them into gap signals for rsi_gap_detector.

    Args:
        predicate_name: optional filter (matches fault_signature)

    Returns:
        Dict with failure-derived gaps
    """
    sm = _import_scenario_memory()
    scenarios = sm._load_all()

    # Filter to failures
    failures = [s for s in scenarios if s.get("outcome") == "failure"]

    if predicate_name:
        failures = [s for s in failures if predicate_name in s.get("fault_signature", "")]

    gaps = []
    for f in failures:
        gaps.append({
            "type": "scenario_failure",
            "severity": "high",
            "source": "scenario-memory",
            "scenario_id": f["id"],
            "fault_signature": f.get("fault_signature", ""),
            "decision": f.get("decision", ""),
            "outcome": f.get("outcome", ""),
            "correction_path": f.get("correction_path", ""),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "suggestion": f"Scenario {f['id']} failed. Apply correction: {f.get('correction_path', 'none')}"
        })

    return {
        "predicate": predicate_name or "all",
        "failure_gaps": gaps,
        "total_failures": len(gaps),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


def gaps_to_corrections(predicate_name: str) -> Dict:
    """Flow 2: rsi_gap_detector gaps → scenario-memory corrections.

    For each gap detected by rsi_gap_detector, check if scenario-memory
    has a known correction path.

    Args:
        predicate_name: predicate to check

    Returns:
        Dict with gap→correction mappings
    """
    detector = _import_gap_detector()
    sm = _import_scenario_memory()

    # Detect gaps from RSI
    rsi_gaps = detector.detect_gaps(predicate_name)

    # For each gap, try to match a scenario correction
    enriched_gaps = []
    for gap in rsi_gaps.get("gaps", []):
        # Build a fault signature from the gap
        fault_sig = f"{predicate_name}_{gap['type']}"

        # Try scenario-memory match
        match_result = sm.match(fault_sig, threshold=0.05)

        enriched_gap = {
            **gap,
            "has_scenario_correction": match_result is not None,
        }

        if match_result:
            # match() returns (id, correction_path) tuple
            sid, correction_path = match_result
            enriched_gap["scenario_correction"] = {
                "id": sid,
                "correction_path": correction_path,
            }

        enriched_gaps.append(enriched_gap)

    return {
        "predicate": predicate_name,
        "enriched_gaps": enriched_gaps,
        "total_gaps": len(enriched_gaps),
        "with_corrections": sum(1 for g in enriched_gaps if g["has_scenario_correction"]),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


def full_bridge(predicate_name: Optional[str] = None) -> Dict:
    """Full bidirectional bridge: failures→gaps + gaps→corrections.

    Args:
        predicate_name: optional filter

    Returns:
        Combined bridge result
    """
    # Flow 1: failures → gap signals
    failure_gaps = failures_to_gaps(predicate_name)

    # Flow 2: gaps → scenario corrections
    if predicate_name:
        gap_corrections = gaps_to_corrections(predicate_name)
    else:
        # Get all predicates from gap detector
        detector = _import_gap_detector()
        all_gaps = detector.detect_all_gaps()
        gap_corrections = {
            "predicates": {}
        }
        for pname in all_gaps.get("predicates", {}).keys():
            gap_corrections["predicates"][pname] = gaps_to_corrections(pname)

    return {
        "failures_to_gaps": failure_gaps,
        "gaps_to_corrections": gap_corrections,
        "bridge_timestamp": datetime.now(timezone.utc).isoformat()
    }
