#!/usr/bin/env python3
"""
RSI Metrics — Performance tracking for auto-optimization
Tracks accuracy, latency, coverage for predicate thresholds.

RSI LEVEL 1: AUTO-OPTIMIZATION
- Track metrics per predicate/threshold
- Store historical performance
- Enable feedback loop for adjustment
"""

import json
import os
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from pathlib import Path

# ── Configuration ────────────────────────────────────────────────────
# RSI_METRICS_DIR env var overrides default location
_default_metrics_dir = Path(__file__).parent.parent.parent / "state" / "monitoring"
METRICS_DIR = Path(os.environ.get("RSI_METRICS_DIR", str(_default_metrics_dir)))
METRICS_FILE = METRICS_DIR / "rsi_metrics.json"
HISTORY_FILE = METRICS_DIR / "rsi_metrics_history.jsonl"


class RSIMetrics:
    """Performance metrics for RSI auto-optimization."""
    
    def __init__(self):
        """Initialize metrics tracker."""
        self.metrics_dir = METRICS_DIR
        self.metrics_dir.mkdir(parents=True, exist_ok=True)
        
    def track_classification(
        self,
        predicate_name: str,
        threshold: float,
        input_value: float,
        expected: bool,
        actual: bool,
        latency_ms: float
    ) -> None:
        """
        Track a classification result.
        DEBT-003: Simplified - only store latency at threshold level.
        
        Args:
            predicate_name: Name of predicate (e.g., 'ac_stasis_critical')
            threshold: Current threshold value
            input_value: Input value to predicate
            expected: Expected classification
            actual: Actual classification
            latency_ms: Latency in milliseconds
        """
        # Load current metrics
        metrics = self._load_metrics()
        
        # Initialize predicate metrics if not exists
        if predicate_name not in metrics:
            metrics[predicate_name] = {
                "thresholds": {},
                "total_classifications": 0,
                "correct_classifications": 0,
                # DEBT-003: Removed predicate-level latencies (redundant)
            }
        
        # Initialize threshold metrics if not exists
        threshold_key = str(round(threshold, 6))
        if threshold_key not in metrics[predicate_name]["thresholds"]:
            metrics[predicate_name]["thresholds"][threshold_key] = {
                "total": 0,
                "correct": 0,
                "latencies": []
            }
        
        # Update metrics
        pm = metrics[predicate_name]
        tm = pm["thresholds"][threshold_key]
        
        pm["total_classifications"] += 1
        tm["total"] += 1
        
        if expected == actual:
            pm["correct_classifications"] += 1
            tm["correct"] += 1
        
        # DEBT-003: Only track latency at threshold level
        tm["latencies"].append(latency_ms)
        if len(tm["latencies"]) > 100:
            tm["latencies"] = tm["latencies"][-100:]
        
        # Save metrics
        self._save_metrics(metrics)
        
        # Append to history
        self._append_history({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "predicate": predicate_name,
            "threshold": threshold,
            "input_value": input_value,
            "expected": expected,
            "actual": actual,
            "correct": expected == actual,
            "latency_ms": latency_ms
        })
    
    def get_accuracy(self, predicate_name: str, threshold: Optional[float] = None) -> float:
        """
        Get accuracy for predicate/threshold.
        
        Args:
            predicate_name: Name of predicate
            threshold: Specific threshold (None for all)
        
        Returns:
            Accuracy as float (0.0 to 1.0)
        """
        metrics = self._load_metrics()
        
        if predicate_name not in metrics:
            return 0.0
        
        pm = metrics[predicate_name]
        
        if threshold is not None:
            # Get accuracy for specific threshold
            # BUG-004: Round threshold to avoid float precision mismatch in str()
            threshold_key = str(round(threshold, 6))
            if threshold_key not in pm["thresholds"]:
                return 0.0
            tm = pm["thresholds"][threshold_key]
            if tm["total"] == 0:
                return 0.0
            return tm["correct"] / tm["total"]
        else:
            # Get overall accuracy
            if pm["total_classifications"] == 0:
                return 0.0
            return pm["correct_classifications"] / pm["total_classifications"]
    
    def get_latency(self, predicate_name: str, threshold: Optional[float] = None) -> float:
        """
        Get average latency for predicate/threshold.
        DEBT-003: Predicate-level latency computed from threshold-level data.
        
        Args:
            predicate_name: Name of predicate
            threshold: Specific threshold (None for all)
        
        Returns:
            Average latency in milliseconds
        """
        metrics = self._load_metrics()
        
        if predicate_name not in metrics:
            return 0.0
        
        pm = metrics[predicate_name]
        
        if threshold is not None:
            # Get latency for specific threshold
            threshold_key = str(round(threshold, 6))
            if threshold_key not in pm["thresholds"]:
                return 0.0
            tm = pm["thresholds"][threshold_key]
            if not tm["latencies"]:
                return 0.0
            return sum(tm["latencies"]) / len(tm["latencies"])
        else:
            # DEBT-003: Compute overall latency from all thresholds
            all_latencies = []
            for tm in pm["thresholds"].values():
                all_latencies.extend(tm.get("latencies", []))
            
            if not all_latencies:
                return 0.0
            return sum(all_latencies) / len(all_latencies)
    
    def get_coverage(self, predicate_name: str) -> float:
        """
        Get coverage for predicate (how often it's used).
        
        Args:
            predicate_name: Name of predicate
        
        Returns:
            Coverage as float (0.0 to 1.0)
        """
        metrics = self._load_metrics()
        
        if predicate_name not in metrics:
            return 0.0
        
        # Coverage = total classifications / total evaluations
        # This is a simplified metric
        return min(1.0, metrics[predicate_name]["total_classifications"] / 1000)
    
    def get_recommendation(self, predicate_name: str) -> Dict:
        """
        Get recommendation for threshold adjustment.
        
        Args:
            predicate_name: Name of predicate
        
        Returns:
            Recommendation dict with suggested threshold and reasoning
        """
        metrics = self._load_metrics()
        
        if predicate_name not in metrics:
            return {
                "action": "collect_data",
                "reason": "No metrics available",
                "suggested_threshold": None
            }
        
        pm = metrics[predicate_name]
        
        # Find best threshold
        best_threshold = None
        best_accuracy = 0.0
        
        for threshold_str, tm in pm["thresholds"].items():
            if tm["total"] == 0:
                continue
            
            accuracy = tm["correct"] / tm["total"]
            
            if accuracy > best_accuracy:
                best_accuracy = accuracy
                best_threshold = float(threshold_str)
        
        if best_threshold is None:
            return {
                "action": "collect_data",
                "reason": "No threshold data available",
                "suggested_threshold": None
            }
        
        # Check if current threshold is optimal
        current_threshold = self._get_current_threshold(predicate_name)
        
        if current_threshold == best_threshold:
            return {
                "action": "keep",
                "reason": f"Current threshold {current_threshold} is optimal (accuracy: {best_accuracy:.2%})",
                "suggested_threshold": current_threshold
            }
        else:
            return {
                "action": "adjust",
                "reason": f"Adjust from {current_threshold} to {best_threshold} (accuracy: {best_accuracy:.2%})",
                "suggested_threshold": best_threshold
            }
    
    def _get_current_threshold(self, predicate_name: str) -> float:
        """Get current threshold for predicate.
        Reads from rsi_thresholds.json if available, else defaults."""
        defaults = {
            "ac_stasis_critical": 0.70,
            "ac_stasis_warning": 0.80,
            "ac_viable_false": 0.50
        }
        thresholds_file = METRICS_DIR / "rsi_thresholds.json"
        if thresholds_file.exists():
            try:
                with open(thresholds_file, 'r') as f:
                    thresholds = json.load(f)
                return thresholds.get(predicate_name, defaults.get(predicate_name, 0.50))
            except (json.JSONDecodeError, OSError):
                pass
        return defaults.get(predicate_name, 0.50)
    
    @property
    def _metrics_file(self) -> Path:
        """Resolve metrics file from instance metrics_dir."""
        return self.metrics_dir / "rsi_metrics.json"

    def _load_metrics(self) -> Dict:
        """Load metrics from file."""
        mf = self._metrics_file
        if mf.exists():
            try:
                with open(mf, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                return {}
        return {}
    
    def _save_metrics(self, metrics: Dict) -> None:
        """Save metrics to file."""
        self.metrics_dir.mkdir(parents=True, exist_ok=True)
        with open(self._metrics_file, 'w') as f:
            json.dump(metrics, f, indent=2)
    
    def rebuild_from_history(self) -> Dict:
        """Rebuild rsi_metrics.json from rsi_metrics_history.jsonl.
        DEBT-003: Simplified - only store latency at threshold level.
        
        This closes the feedback loop: history (raw) → metrics (aggregated)
        → GA fitness evaluation. Call when rsi_metrics.json is missing or stale.
        
        Returns:
            Rebuilt metrics dict
        """
        metrics = {}
        
        history_file = self.metrics_dir / "rsi_metrics_history.jsonl"
        if not history_file.exists():
            return metrics
        
        with open(history_file, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                
                predicate = entry.get("predicate", "unknown")
                threshold = entry.get("threshold", 0.7)
                correct = entry.get("correct", False)
                latency_ms = entry.get("latency_ms", 0.0)
                
                # Initialize predicate if not exists
                if predicate not in metrics:
                    metrics[predicate] = {
                        "thresholds": {},
                        "total_classifications": 0,
                        "correct_classifications": 0,
                        # DEBT-003: No predicate-level latencies
                    }
                
                pm = metrics[predicate]
                
                # Initialize threshold if not exists
                threshold_key = str(round(threshold, 6))
                if threshold_key not in pm["thresholds"]:
                    pm["thresholds"][threshold_key] = {
                        "total": 0,
                        "correct": 0,
                        "latencies": []
                    }
                
                tm = pm["thresholds"][threshold_key]
                
                # Update counts
                pm["total_classifications"] += 1
                tm["total"] += 1
                if correct:
                    pm["correct_classifications"] += 1
                    tm["correct"] += 1
                
                # DEBT-003: Only track latency at threshold level
                tm["latencies"].append(latency_ms)
                if len(tm["latencies"]) > 100:
                    tm["latencies"] = tm["latencies"][-100:]
        
        # Save rebuilt metrics
        self._save_metrics(metrics)
        
        # Log rebuild
        total_entries = sum(pm["total_classifications"] for pm in metrics.values())
        print(f"Rebuilt metrics from {history_file.name}: {len(metrics)} predicates, {total_entries} classifications")
        
        return metrics
    
    def _append_history(self, entry: Dict) -> None:
        """Append entry to history file."""
        self.metrics_dir.mkdir(parents=True, exist_ok=True)
        with open(self.metrics_dir / "rsi_metrics_history.jsonl", 'a') as f:
            f.write(json.dumps(entry) + "\n")
    
    def get_summary(self) -> Dict:
        """Get summary of all metrics."""
        metrics = self._load_metrics()
        
        summary = {
            "total_predicates": len(metrics),
            "total_classifications": sum(pm["total_classifications"] for pm in metrics.values()),
            "overall_accuracy": 0.0,
            "predicates": {}
        }
        
        total_correct = sum(pm["correct_classifications"] for pm in metrics.values())
        total_classifications = summary["total_classifications"]
        
        if total_classifications > 0:
            summary["overall_accuracy"] = total_correct / total_classifications
        
        for predicate_name, pm in metrics.items():
            # DEBT-003: Collect latencies from threshold-level data
            all_latencies = []
            for tm in pm["thresholds"].values():
                all_latencies.extend(tm.get("latencies", []))

            summary["predicates"][predicate_name] = {
                "total": pm["total_classifications"],
                "correct": pm["correct_classifications"],
                "accuracy": pm["correct_classifications"] / pm["total_classifications"] if pm["total_classifications"] > 0 else 0.0,
                "avg_latency": sum(all_latencies) / len(all_latencies) if all_latencies else 0.0,
                "thresholds": len(pm["thresholds"])
            }
        
        return summary


# ── CLI Interface ────────────────────────────────────────────────────
def main():
    """CLI interface for RSI metrics."""
    import argparse
    
    parser = argparse.ArgumentParser(description="RSI Metrics")
    subparsers = parser.add_subparsers(dest="command")
    
    # Track command
    track_parser = subparsers.add_parser("track", help="Track classification")
    track_parser.add_argument("predicate", help="Predicate name")
    track_parser.add_argument("threshold", type=float, help="Threshold value")
    track_parser.add_argument("input_value", type=float, help="Input value")
    track_parser.add_argument("expected", type=lambda x: x.lower() == "true", help="Expected (true/false)")
    track_parser.add_argument("actual", type=lambda x: x.lower() == "true", help="Actual (true/false)")
    track_parser.add_argument("latency", type=float, help="Latency in ms")
    
    # Accuracy command
    accuracy_parser = subparsers.add_parser("accuracy", help="Get accuracy")
    accuracy_parser.add_argument("predicate", help="Predicate name")
    accuracy_parser.add_argument("--threshold", type=float, help="Specific threshold")
    
    # Recommend command
    recommend_parser = subparsers.add_parser("recommend", help="Get recommendation")
    recommend_parser.add_argument("predicate", help="Predicate name")
    
    # Summary command
    subparsers.add_parser("summary", help="Get summary")
    
    args = parser.parse_args()
    metrics = RSIMetrics()
    
    if args.command == "track":
        metrics.track_classification(
            args.predicate,
            args.threshold,
            args.input_value,
            args.expected,
            args.actual,
            args.latency
        )
        print(f"Tracked: {args.predicate} @ {args.threshold}")
    elif args.command == "accuracy":
        accuracy = metrics.get_accuracy(args.predicate, args.threshold)
        print(f"Accuracy: {accuracy:.2%}")
    elif args.command == "recommend":
        rec = metrics.get_recommendation(args.predicate)
        print(f"Recommendation: {rec['action']}")
        print(f"Reason: {rec['reason']}")
        if rec['suggested_threshold'] is not None:
            print(f"Suggested threshold: {rec['suggested_threshold']}")
    elif args.command == "summary":
        summary = metrics.get_summary()
        print(f"Total predicates: {summary['total_predicates']}")
        print(f"Total classifications: {summary['total_classifications']}")
        print(f"Overall accuracy: {summary['overall_accuracy']:.2%}")
        print("\nPer predicate:")
        for name, stats in summary['predicates'].items():
            print(f"  {name}: {stats['accuracy']:.2%} (n={stats['total']})")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
