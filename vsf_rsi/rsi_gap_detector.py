#!/usr/bin/env python3
"""
RSI Gap Detector — Detects classification gaps
Identifies where current trees fail and need modification.

RSI LEVEL 2: AUTO-MODIFICATION
- Detect misclassifications
- Identify missing predicates
- Find coverage gaps
- Suggest tree modifications
"""

import json
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from rsi_metrics import RSIMetrics

# ── Configuration ────────────────────────────────────────────────────
GAPS_DIR = Path(__file__).parent.parent.parent / "state" / "monitoring"
GAPS_FILE = GAPS_DIR / "rsi_gaps.json"
MODIFICATIONS_FILE = GAPS_DIR / "rsi_modifications.jsonl"


class RSIGapDetector:
    """Detects gaps in classification trees."""
    
    def __init__(self):
        """Initialize gap detector."""
        self.metrics = RSIMetrics()
        self.gaps_dir = GAPS_DIR
        self.gaps_dir.mkdir(parents=True, exist_ok=True)
        
    def detect_gaps(self, predicate_name: str) -> Dict:
        """
        Detect gaps for a predicate.
        
        Args:
            predicate_name: Name of predicate
        
        Returns:
            Dictionary with detected gaps
        """
        # Load metrics
        metrics = self.metrics._load_metrics()
        
        if predicate_name not in metrics:
            return {
                "predicate": predicate_name,
                "gaps": [],
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        
        pm = metrics[predicate_name]
        
        gaps = {
            "predicate": predicate_name,
            "gaps": [],
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        # Check for misclassifications
        if pm["total_classifications"] > 0:
            accuracy = pm["correct_classifications"] / pm["total_classifications"]
            
            if accuracy < 0.8:  # Less than 80% accuracy
                gaps["gaps"].append({
                    "type": "low_accuracy",
                    "severity": "high",
                    "accuracy": accuracy,
                    "threshold": "current",
                    "suggestion": "Adjust threshold or add new branches"
                })
        
        # Check for missing thresholds
        if len(pm["thresholds"]) < 3:
            gaps["gaps"].append({
                "type": "insufficient_thresholds",
                "severity": "medium",
                "tested": len(pm["thresholds"]),
                "suggestion": "Test more thresholds"
            })
        
        # Check for threshold accuracy
        for threshold_str, tm in pm["thresholds"].items():
            if tm["total"] > 0:
                threshold_accuracy = tm["correct"] / tm["total"]
                
                if threshold_accuracy < 0.7:  # Less than 70% accuracy
                    gaps["gaps"].append({
                        "type": "threshold_low_accuracy",
                        "severity": "high",
                        "threshold": float(threshold_str),
                        "accuracy": threshold_accuracy,
                        "suggestion": "Adjust threshold or add specific branch"
                    })
        
        # Check for latency issues
        if pm["latencies"]:
            avg_latency = sum(pm["latencies"]) / len(pm["latencies"])
            
            if avg_latency > 10:  # More than 10ms average
                gaps["gaps"].append({
                    "type": "high_latency",
                    "severity": "medium",
                    "avg_latency_ms": avg_latency,
                    "suggestion": "Optimize predicate logic"
                })
        
        # Save gaps
        self._save_gaps(gaps)
        
        return gaps
    
    def detect_all_gaps(self) -> Dict:
        """Detect gaps for all predicates."""
        metrics = self.metrics._load_metrics()
        
        all_gaps = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "predicates": {}
        }
        
        for predicate_name in metrics.keys():
            all_gaps["predicates"][predicate_name] = self.detect_gaps(predicate_name)
        
        return all_gaps
    
    def suggest_modification(self, gap: Dict) -> Optional[Dict]:
        """
        Suggest modification for a gap.
        
        Args:
            gap: Detected gap
        
        Returns:
            Suggested modification or None
        """
        if gap["type"] == "low_accuracy":
            return {
                "type": "adjust_threshold",
                "predicate": gap.get("predicate", "unknown"),
                "current_threshold": "current",
                "suggested_action": "increase_threshold",
                "reason": f"Accuracy {gap['accuracy']:.2%} is below 80%"
            }
        
        elif gap["type"] == "threshold_low_accuracy":
            return {
                "type": "add_branch",
                "predicate": gap.get("predicate", "unknown"),
                "threshold": gap["threshold"],
                "suggested_action": "add_specific_branch",
                "reason": f"Threshold {gap['threshold']} has accuracy {gap['accuracy']:.2%}"
            }
        
        elif gap["type"] == "insufficient_thresholds":
            return {
                "type": "test_thresholds",
                "predicate": gap.get("predicate", "unknown"),
                "suggested_action": "test_more_thresholds",
                "reason": f"Only {gap['tested']} thresholds tested"
            }
        
        elif gap["type"] == "high_latency":
            return {
                "type": "optimize",
                "predicate": gap.get("predicate", "unknown"),
                "suggested_action": "optimize_logic",
                "reason": f"Average latency {gap['avg_latency_ms']:.2f}ms is above 10ms"
            }
        
        return None
    
    def _save_gaps(self, gaps: Dict) -> None:
        """Save gaps to file."""
        # Load existing gaps
        existing_gaps = self._load_gaps()
        
        # Update with new gaps
        existing_gaps[gaps["predicate"]] = gaps
        
        # Save
        with open(GAPS_FILE, 'w') as f:
            json.dump(existing_gaps, f, indent=2)
    
    def _load_gaps(self) -> Dict:
        """Load gaps from file."""
        if GAPS_FILE.exists():
            with open(GAPS_FILE, 'r') as f:
                return json.load(f)
        return {}
    
    def get_gaps_summary(self) -> Dict:
        """Get summary of all gaps."""
        all_gaps = self.detect_all_gaps()
        
        summary = {
            "total_predicates": len(all_gaps["predicates"]),
            "total_gaps": 0,
            "high_severity": 0,
            "medium_severity": 0,
            "low_severity": 0,
            "predicates": {}
        }
        
        for predicate_name, gaps in all_gaps["predicates"].items():
            predicate_gaps = len(gaps["gaps"])
            summary["total_gaps"] += predicate_gaps
            
            for gap in gaps["gaps"]:
                if gap["severity"] == "high":
                    summary["high_severity"] += 1
                elif gap["severity"] == "medium":
                    summary["medium_severity"] += 1
                else:
                    summary["low_severity"] += 1
            
            summary["predicates"][predicate_name] = {
                "gaps": predicate_gaps,
                "details": gaps["gaps"]
            }
        
        return summary


# ── CLI Interface ────────────────────────────────────────────────────
def main():
    """CLI interface for RSI gap detector."""
    import argparse
    
    parser = argparse.ArgumentParser(description="RSI Gap Detector")
    subparsers = parser.add_subparsers(dest="command")
    
    # Detect command
    detect_parser = subparsers.add_parser("detect", help="Detect gaps")
    detect_parser.add_argument("--predicate", help="Predicate name")
    
    # Summary command
    subparsers.add_parser("summary", help="Get gaps summary")
    
    args = parser.parse_args()
    detector = RSIGapDetector()
    
    if args.command == "detect":
        if args.predicate:
            gaps = detector.detect_gaps(args.predicate)
            print(f"Gaps for {args.predicate}: {len(gaps['gaps'])}")
            for gap in gaps["gaps"]:
                print(f"  {gap['type']}: {gap['severity']} - {gap['suggestion']}")
        else:
            all_gaps = detector.detect_all_gaps()
            print(f"Total predicates: {len(all_gaps['predicates'])}")
            for predicate_name, gaps in all_gaps["predicates"].items():
                print(f"  {predicate_name}: {len(gaps['gaps'])} gaps")
    elif args.command == "summary":
        summary = detector.get_gaps_summary()
        print(f"Total gaps: {summary['total_gaps']}")
        print(f"High severity: {summary['high_severity']}")
        print(f"Medium severity: {summary['medium_severity']}")
        print(f"Low severity: {summary['low_severity']}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
