#!/usr/bin/env python3
"""
RSI Feedback Loop — Auto-optimization of predicate thresholds
Uses metrics to adjust thresholds automatically.

RSI LEVEL 1: AUTO-OPTIMIZATION
- Collect performance metrics
- Analyze threshold effectiveness
- Adjust thresholds based on accuracy
- Validate adjustments against test set
"""

import json
import os
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from rsi_metrics import RSIMetrics

# ── Configuration ────────────────────────────────────────────────────
CONFIG_DIR = Path(__file__).parent.parent.parent / "state" / "monitoring"
THRESHOLDS_FILE = CONFIG_DIR / "rsi_thresholds.json"
ADJUSTMENTS_FILE = CONFIG_DIR / "rsi_adjustments.jsonl"

# Default thresholds
DEFAULT_THRESHOLDS = {
    "ac_stasis_critical": 0.70,
    "ac_stasis_warning": 0.80,
    "ac_viable_false": 0.50
}

# Adjustment parameters
MIN_SAMPLES = 10  # Minimum samples before adjustment
ACCURACY_THRESHOLD = 0.7  # Minimum accuracy to keep threshold
ADJUSTMENT_STEP = 0.05  # Maximum adjustment per cycle


class RSIFeedbackLoop:
    """Auto-optimization feedback loop for predicates."""
    
    def __init__(self):
        """Initialize feedback loop."""
        self.metrics = RSIMetrics()
        self.config_dir = CONFIG_DIR
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
    def adjust_thresholds(self) -> Dict:
        """
        Analyze metrics and adjust thresholds.
        
        Returns:
            Dictionary with adjustments made
        """
        # Load current thresholds
        thresholds = self._load_thresholds()
        
        adjustments = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "adjustments": []
        }
        
        for predicate_name, current_threshold in thresholds.items():
            # Get recommendation
            rec = self.metrics.get_recommendation(predicate_name)
            
            if rec["action"] == "adjust" and rec["suggested_threshold"] is not None:
                suggested = rec["suggested_threshold"]
                
                # Check if adjustment is significant
                diff = abs(suggested - current_threshold)
                if diff < ADJUSTMENT_STEP:
                    continue
                
                # Limit adjustment step
                if suggested > current_threshold:
                    new_threshold = min(suggested, current_threshold + ADJUSTMENT_STEP)
                else:
                    new_threshold = max(suggested, current_threshold - ADJUSTMENT_STEP)
                
                # Validate new threshold
                if self._validate_threshold(predicate_name, new_threshold):
                    # Apply adjustment
                    thresholds[predicate_name] = new_threshold
                    
                    adjustments["adjustments"].append({
                        "predicate": predicate_name,
                        "old": current_threshold,
                        "new": new_threshold,
                        "reason": rec["reason"]
                    })
        
        # Save new thresholds
        self._save_thresholds(thresholds)
        
        # Record adjustment
        self._record_adjustment(adjustments)
        
        return adjustments
    
    def _validate_threshold(self, predicate_name: str, threshold: float) -> bool:
        """
        Validate new threshold against test set.
        
        Args:
            predicate_name: Name of predicate
            threshold: New threshold value
        
        Returns:
            True if threshold is valid
        """
        # Get accuracy for new threshold
        accuracy = self.metrics.get_accuracy(predicate_name, threshold)
        
        # Check if accuracy is acceptable
        if accuracy < ACCURACY_THRESHOLD:
            return False
        
        # Check if we have enough samples
        metrics = self.metrics._load_metrics()
        if predicate_name not in metrics:
            return False
        
        pm = metrics[predicate_name]
        if str(threshold) not in pm["thresholds"]:
            return False
        
        tm = pm["thresholds"][str(threshold)]
        if tm["total"] < MIN_SAMPLES:
            return False
        
        return True
    
    def _load_thresholds(self) -> Dict:
        """Load thresholds from file."""
        if THRESHOLDS_FILE.exists():
            with open(THRESHOLDS_FILE, 'r') as f:
                return json.load(f)
        return DEFAULT_THRESHOLDS.copy()
    
    def _save_thresholds(self, thresholds: Dict) -> None:
        """Save thresholds to file."""
        with open(THRESHOLDS_FILE, 'w') as f:
            json.dump(thresholds, f, indent=2)
    
    def _record_adjustment(self, adjustment: Dict) -> None:
        """Record adjustment to history."""
        with open(ADJUSTMENTS_FILE, 'a') as f:
            f.write(json.dumps(adjustment) + "\n")
    
    def get_current_threshold(self, predicate_name: str) -> float:
        """
        Get current threshold for predicate.
        
        Args:
            predicate_name: Name of predicate
        
        Returns:
            Current threshold value
        """
        thresholds = self._load_thresholds()
        return thresholds.get(predicate_name, DEFAULT_THRESHOLDS.get(predicate_name, 0.50))
    
    def get_adjustment_history(self) -> List[Dict]:
        """Get adjustment history."""
        if not ADJUSTMENTS_FILE.exists():
            return []
        
        history = []
        with open(ADJUSTMENTS_FILE, 'r') as f:
            for line in f:
                if line.strip():
                    history.append(json.loads(line))
        
        return history
    
    def get_status(self) -> Dict:
        """Get current status of feedback loop."""
        thresholds = self._load_thresholds()
        history = self.get_adjustment_history()
        
        status = {
            "current_thresholds": thresholds,
            "total_adjustments": len(history),
            "last_adjustment": history[-1] if history else None,
            "predicates": {}
        }
        
        for predicate_name in thresholds.keys():
            accuracy = self.metrics.get_accuracy(predicate_name)
            rec = self.metrics.get_recommendation(predicate_name)
            
            status["predicates"][predicate_name] = {
                "threshold": thresholds[predicate_name],
                "accuracy": accuracy,
                "recommendation": rec["action"],
                "reason": rec["reason"]
            }
        
        return status


# ── CLI Interface ────────────────────────────────────────────────────
def main():
    """CLI interface for RSI feedback loop."""
    import argparse
    
    parser = argparse.ArgumentParser(description="RSI Feedback Loop")
    subparsers = parser.add_subparsers(dest="command")
    
    # Adjust command
    subparsers.add_parser("adjust", help="Adjust thresholds")
    
    # Status command
    subparsers.add_parser("status", help="Get status")
    
    # History command
    subparsers.add_parser("history", help="Get adjustment history")
    
    # Threshold command
    threshold_parser = subparsers.add_parser("threshold", help="Get threshold")
    threshold_parser.add_argument("predicate", help="Predicate name")
    
    args = parser.parse_args()
    feedback = RSIFeedbackLoop()
    
    if args.command == "adjust":
        adjustments = feedback.adjust_thresholds()
        print(f"Adjustments made: {len(adjustments['adjustments'])}")
        for adj in adjustments["adjustments"]:
            print(f"  {adj['predicate']}: {adj['old']} -> {adj['new']}")
            print(f"    Reason: {adj['reason']}")
    elif args.command == "status":
        status = feedback.get_status()
        print(f"Current thresholds:")
        for name, threshold in status["current_thresholds"].items():
            print(f"  {name}: {threshold}")
        print(f"\nTotal adjustments: {status['total_adjustments']}")
        if status["last_adjustment"]:
            print(f"Last adjustment: {status['last_adjustment']['timestamp']}")
        print(f"\nPer predicate:")
        for name, stats in status["predicates"].items():
            print(f"  {name}:")
            print(f"    Threshold: {stats['threshold']}")
            print(f"    Accuracy: {stats['accuracy']:.2%}")
            print(f"    Recommendation: {stats['recommendation']}")
            print(f"    Reason: {stats['reason']}")
    elif args.command == "history":
        history = feedback.get_adjustment_history()
        print(f"Adjustment history: {len(history)} entries")
        for entry in history:
            print(f"  {entry['timestamp']}: {len(entry['adjustments'])} adjustments")
            for adj in entry["adjustments"]:
                print(f"    {adj['predicate']}: {adj['old']} -> {adj['new']}")
    elif args.command == "threshold":
        threshold = feedback.get_current_threshold(args.predicate)
        print(f"Current threshold for {args.predicate}: {threshold}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
