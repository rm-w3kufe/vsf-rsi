#!/usr/bin/env python3
"""
RSI Pattern Detector — Detects recurring patterns
Identifies patterns that can be used to generate new components.

RSI LEVEL 3: AUTO-GENERATION
- Detect recurring misclassifications
- Identify common error patterns
- Find threshold patterns
- Suggest new predicates/trees
"""

import json
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from collections import Counter
from vsf_rsi.rsi_metrics import RSIMetrics

# ── Configuration ────────────────────────────────────────────────────
PATTERNS_DIR = Path(__file__).parent.parent.parent / "state" / "monitoring"
PATTERNS_FILE = PATTERNS_DIR / "rsi_patterns.json"

# DEBT-005: Pattern decay configuration
PATTERN_DECAY_RATE: float = 0.1  # Decay per day (10% per day)
PATTERN_MIN_STRENGTH: float = 0.1  # Minimum strength before removal


class RSIPatternDetector:
    """Detects patterns in classification data."""
    
    def __init__(self):
        """Initialize pattern detector."""
        self.metrics = RSIMetrics()
        self.patterns_dir = PATTERNS_DIR
        self.patterns_dir.mkdir(parents=True, exist_ok=True)
        
    def detect_patterns(self, predicate_name: str) -> Dict:
        """
        Detect patterns for a predicate.
        
        Args:
            predicate_name: Name of predicate
        
        Returns:
            Dictionary with detected patterns
        """
        # Load metrics
        metrics = self.metrics._load_metrics()
        
        if predicate_name not in metrics:
            return {
                "predicate": predicate_name,
                "patterns": [],
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        
        pm = metrics[predicate_name]
        
        patterns = {
            "predicate": predicate_name,
            "patterns": [],
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        # Pattern 1: Recurring misclassifications
        misclassification_pattern = self._detect_misclassification_pattern(pm)
        if misclassification_pattern:
            patterns["patterns"].append(misclassification_pattern)
        
        # Pattern 2: Threshold clustering
        threshold_pattern = self._detect_threshold_pattern(pm)
        if threshold_pattern:
            patterns["patterns"].append(threshold_pattern)
        
        # Pattern 3: Latency spikes
        latency_pattern = self._detect_latency_pattern(pm)
        if latency_pattern:
            patterns["patterns"].append(latency_pattern)
        
        # Pattern 4: Accuracy degradation
        degradation_pattern = self._detect_degradation_pattern(pm)
        if degradation_pattern:
            patterns["patterns"].append(degradation_pattern)
        
        # Pattern 5: Coverage gaps
        coverage_pattern = self._detect_coverage_pattern(pm)
        if coverage_pattern:
            patterns["patterns"].append(coverage_pattern)
        
        # Save patterns
        self._save_patterns(patterns)
        
        return patterns
    
    def _detect_misclassification_pattern(self, pm: Dict) -> Optional[Dict]:
        """Detect recurring misclassifications."""
        if pm["total_classifications"] == 0:
            return None
        
        accuracy = pm["correct_classifications"] / pm["total_classifications"]
        
        if accuracy < 0.8:  # Less than 80% accuracy
            return {
                "type": "recurring_misclassification",
                "severity": "high",
                "accuracy": accuracy,
                "misclassification_rate": 1 - accuracy,
                "suggestion": "Generate new predicate for edge cases"
            }
        
        return None
    
    def _detect_threshold_pattern(self, pm: Dict) -> Optional[Dict]:
        """Detect threshold clustering."""
        if len(pm["thresholds"]) < 3:
            return None
        
        # Find best threshold
        best_threshold = None
        best_accuracy = 0
        
        for threshold_str, tm in pm["thresholds"].items():
            if tm["total"] > 0:
                accuracy = tm["correct"] / tm["total"]
                if accuracy > best_accuracy:
                    best_accuracy = accuracy
                    best_threshold = float(threshold_str)
        
        if best_threshold is None:
            return None
        
        # Check if best threshold is far from current
        current_threshold = 0.7  # Default
        if abs(best_threshold - current_threshold) > 0.1:
            return {
                "type": "threshold_clustering",
                "severity": "medium",
                "best_threshold": best_threshold,
                "best_accuracy": best_accuracy,
                "current_threshold": current_threshold,
                "suggestion": "Generate tree optimized for best threshold"
            }
        
        return None
    
    def _detect_latency_pattern(self, pm: Dict) -> Optional[Dict]:
        """Detect latency spikes."""
        if not pm["latencies"]:
            return None
        
        avg_latency = sum(pm["latencies"]) / len(pm["latencies"])
        max_latency = max(pm["latencies"])
        
        if avg_latency > 10 or max_latency > 50:
            return {
                "type": "latency_spike",
                "severity": "medium",
                "avg_latency": avg_latency,
                "max_latency": max_latency,
                "suggestion": "Generate optimized predicate"
            }
        
        return None
    
    def _detect_degradation_pattern(self, pm: Dict) -> Optional[Dict]:
        """Detect accuracy degradation over time."""
        # This would require time-series data
        # For now, return None
        return None
    
    def _detect_coverage_pattern(self, pm: Dict) -> Optional[Dict]:
        """Detect coverage gaps."""
        if len(pm["thresholds"]) < 5:
            return {
                "type": "coverage_gap",
                "severity": "low",
                "tested_thresholds": len(pm["thresholds"]),
                "suggestion": "Generate predicate for untested thresholds"
            }
        
        return None
    
    def suggest_generation(self, pattern: Dict) -> Optional[Dict]:
        """
        Suggest component generation for a pattern.
        
        Args:
            pattern: Detected pattern
        
        Returns:
            Suggested generation or None
        """
        if pattern["type"] == "recurring_misclassification":
            return {
                "type": "predicate",
                "name": f"{pattern.get('predicate', 'unknown')}_edge_cases",
                "purpose": "Handle edge cases that cause misclassifications",
                "template": "edge_case_predicate"
            }
        
        elif pattern["type"] == "threshold_clustering":
            return {
                "type": "tree",
                "name": f"{pattern.get('predicate', 'unknown')}_optimized",
                "purpose": f"Optimized for threshold {pattern['best_threshold']}",
                "template": "threshold_optimized_tree"
            }
        
        elif pattern["type"] == "latency_spike":
            return {
                "type": "predicate",
                "name": f"{pattern.get('predicate', 'unknown')}_fast",
                "purpose": "Fast execution predicate",
                "template": "fast_predicate"
            }
        
        elif pattern["type"] == "coverage_gap":
            return {
                "type": "tree",
                "name": f"{pattern.get('predicate', 'unknown')}_coverage",
                "purpose": "Coverage for untested thresholds",
                "template": "coverage_tree"
            }
        
        return None
    
    def _save_patterns(self, patterns: Dict) -> None:
        """Save patterns to file with timestamps for decay tracking."""
        # Load existing patterns
        existing_patterns = self._load_patterns()
        
        # DEBT-005: Add last_seen timestamp and strength to new patterns
        now = datetime.now(timezone.utc).isoformat()
        for pattern in patterns.get("patterns", []):
            if "last_seen" not in pattern:
                pattern["last_seen"] = now
            if "strength" not in pattern:
                pattern["strength"] = 1.0
        
        # Update with new patterns
        existing_patterns[patterns["predicate"]] = patterns
        
        # DEBT-005: Apply decay to all patterns
        existing_patterns = self._apply_decay(existing_patterns)
        
        # Save
        with open(PATTERNS_FILE, 'w') as f:
            json.dump(existing_patterns, f, indent=2)
    
    def _apply_decay(self, patterns: Dict) -> Dict:
        """
        DEBT-005: Apply time-based decay to pattern strength.
        Remove patterns with strength below threshold.
        """
        now = datetime.now(timezone.utc)
        decayed_patterns = {}
        
        for predicate_name, predicate_patterns in patterns.items():
            decayed_list = []
            
            for pattern in predicate_patterns.get("patterns", []):
                # Calculate time since last_seen
                last_seen_str = pattern.get("last_seen")
                if last_seen_str:
                    try:
                        last_seen = datetime.fromisoformat(last_seen_str.replace('Z', '+00:00'))
                        days_since = (now - last_seen).total_seconds() / 86400
                    except (ValueError, TypeError):
                        days_since = 0
                else:
                    days_since = 0
                
                # Apply exponential decay
                current_strength = pattern.get("strength", 1.0)
                new_strength = current_strength * (1 - PATTERN_DECAY_RATE) ** days_since
                
                # Update pattern
                pattern["strength"] = new_strength
                pattern["last_seen"] = now.isoformat()
                
                # Keep pattern if strength is above threshold
                if new_strength >= PATTERN_MIN_STRENGTH:
                    decayed_list.append(pattern)
            
            # Only keep predicate if it has patterns
            if decayed_list:
                predicate_patterns["patterns"] = decayed_list
                decayed_patterns[predicate_name] = predicate_patterns
        
        return decayed_patterns
    
    def _load_patterns(self) -> Dict:
        """Load patterns from file."""
        if PATTERNS_FILE.exists():
            with open(PATTERNS_FILE, 'r') as f:
                return json.load(f)
        return {}
    
    def get_patterns_summary(self) -> Dict:
        """Get summary of all patterns."""
        all_patterns = self._load_patterns()
        
        summary = {
            "total_predicates": len(all_patterns),
            "total_patterns": 0,
            "by_type": {},
            "predicates": {}
        }
        
        for predicate_name, patterns in all_patterns.items():
            pattern_count = len(patterns["patterns"])
            summary["total_patterns"] += pattern_count
            
            for pattern in patterns["patterns"]:
                pattern_type = pattern["type"]
                if pattern_type not in summary["by_type"]:
                    summary["by_type"][pattern_type] = 0
                summary["by_type"][pattern_type] += 1
            
            summary["predicates"][predicate_name] = {
                "patterns": pattern_count,
                "types": [p["type"] for p in patterns["patterns"]]
            }
        
        return summary


# ── CLI Interface ────────────────────────────────────────────────────
def main():
    """CLI interface for RSI pattern detector."""
    import argparse
    
    parser = argparse.ArgumentParser(description="RSI Pattern Detector")
    subparsers = parser.add_subparsers(dest="command")
    
    # Detect command
    detect_parser = subparsers.add_parser("detect", help="Detect patterns")
    detect_parser.add_argument("--predicate", help="Predicate name")
    
    # Summary command
    subparsers.add_parser("summary", help="Get patterns summary")
    
    args = parser.parse_args()
    detector = RSIPatternDetector()
    
    if args.command == "detect":
        if args.predicate:
            patterns = detector.detect_patterns(args.predicate)
            print(f"Patterns for {args.predicate}: {len(patterns['patterns'])}")
            for pattern in patterns["patterns"]:
                print(f"  {pattern['type']}: {pattern['severity']}")
        else:
            print("Please specify --predicate")
    elif args.command == "summary":
        summary = detector.get_patterns_summary()
        print(f"Total patterns: {summary['total_patterns']}")
        print(f"By type: {summary['by_type']}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
