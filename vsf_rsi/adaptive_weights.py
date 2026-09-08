"""adaptive_weights.py — Adaptive weight management for RSI self-modification.

Provides:
  - AdaptiveWeightManager: manages weights that adjust based on outcomes
  - Weight persistence (JSON save/load)
  - Feedback loop from outcomes to weights

Architecture:
  vsf-rsi → adaptive_weights → outcome feedback → weight adjustment → improved fitness

This enables second-order cybernetics: the system modifies its own improvement
parameters based on observed outcomes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone


@dataclass
class WeightConfig:
    """Configuration for adaptive weights."""
    
    # Fitness weights (GA)
    accuracy_weight: float = 0.4
    complexity_weight: float = 0.2
    diversity_weight: float = 0.2
    threshold_weight: float = 0.2
    
    # Threshold drift
    drift_step: float = 0.05
    drift_min: float = 0.05
    drift_max: float = 0.95
    
    # Learning rates
    fitness_learning_rate: float = 0.1
    drift_learning_rate: float = 0.05
    
    # Bounds
    min_weight: float = 0.1
    max_weight: float = 0.8
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "accuracy_weight": self.accuracy_weight,
            "complexity_weight": self.complexity_weight,
            "diversity_weight": self.diversity_weight,
            "threshold_weight": self.threshold_weight,
            "drift_step": self.drift_step,
            "drift_min": self.drift_min,
            "drift_max": self.drift_max,
            "fitness_learning_rate": self.fitness_learning_rate,
            "drift_learning_rate": self.drift_learning_rate,
            "min_weight": self.min_weight,
            "max_weight": self.max_weight,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WeightConfig":
        return cls(
            accuracy_weight=data.get("accuracy_weight", 0.4),
            complexity_weight=data.get("complexity_weight", 0.2),
            diversity_weight=data.get("diversity_weight", 0.2),
            threshold_weight=data.get("threshold_weight", 0.2),
            drift_step=data.get("drift_step", 0.05),
            drift_min=data.get("drift_min", 0.05),
            drift_max=data.get("drift_max", 0.95),
            fitness_learning_rate=data.get("fitness_learning_rate", 0.1),
            drift_learning_rate=data.get("drift_learning_rate", 0.05),
            min_weight=data.get("min_weight", 0.1),
            max_weight=data.get("max_weight", 0.8),
        )


@dataclass
class WeightAdjustment:
    """Record of a weight adjustment."""
    
    timestamp: str
    weight_name: str
    old_value: float
    new_value: float
    reason: str
    outcome_quality: float
    component: str = ""


class AdaptiveWeightManager:
    """Manages weights that adjust based on outcomes.
    
    Usage:
        manager = AdaptiveWeightManager()
        manager.load()
        
        # Get current weights for fitness evaluation
        weights = manager.get_fitness_weights()
        
        # Record outcome and adjust weights
        manager.record_outcome("predicate_gen", quality=0.85)
        manager.save()
    """
    
    def __init__(self, state_file: str | Path | None = None):
        if state_file:
            self.state_file = Path(state_file)
        else:
            self.state_file = Path.home() / "vOSlab" / "packages" / "public" / "vsf-rsi" / "adaptive_weights.json"
        
        self.config = WeightConfig()
        self.history: List[WeightAdjustment] = []
        self.outcomes: List[Dict[str, Any]] = []
    
    def load(self) -> None:
        """Load state from JSON file."""
        if self.state_file.exists():
            try:
                with open(self.state_file, "r") as f:
                    data = json.load(f)
                
                self.config = WeightConfig.from_dict(data.get("config", {}))
                self.history = [
                    WeightAdjustment(**h) for h in data.get("history", [])
                ]
                self.outcomes = data.get("outcomes", [])
            except (json.JSONDecodeError, KeyError):
                pass
    
    def save(self) -> None:
        """Save state to JSON file."""
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        
        data = {
            "config": self.config.to_dict(),
            "history": [
                {
                    "timestamp": h.timestamp,
                    "weight_name": h.weight_name,
                    "old_value": h.old_value,
                    "new_value": h.new_value,
                    "reason": h.reason,
                    "outcome_quality": h.outcome_quality,
                    "component": h.component,
                }
                for h in self.history[-100:]  # Keep last 100 adjustments
            ],
            "outcomes": self.outcomes[-200:],  # Keep last 200 outcomes
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        
        with open(self.state_file, "w") as f:
            json.dump(data, f, indent=2)
    
    def get_fitness_weights(self) -> Dict[str, float]:
        """Get current fitness weights for GA evaluation.
        
        Returns:
            Dict with accuracy, complexity, diversity, threshold weights.
        """
        return {
            "accuracy": self.config.accuracy_weight,
            "complexity": self.config.complexity_weight,
            "diversity": self.config.diversity_weight,
            "threshold": self.config.threshold_weight,
        }
    
    def get_drift_step(self, accuracy: float = 0.5) -> float:
        """Get adaptive drift step size based on current accuracy.
        
        Args:
            accuracy: Current accuracy at this threshold (0.0 to 1.0)
        
        Returns:
            Adaptive step size (larger when accuracy is low).
        """
        # Larger steps when accuracy is low, smaller when high
        adaptive_step = self.config.drift_step * (1.0 - accuracy * 0.5)
        
        # Apply bounds
        adaptive_step = max(self.config.drift_min, min(self.config.drift_max, adaptive_step))
        
        return adaptive_step
    
    def record_outcome(self, component: str, quality: float, metadata: Dict[str, Any] | None = None) -> None:
        """Record an outcome for weight adjustment.
        
        Args:
            component: Component that produced the outcome
            quality: Quality of the outcome (0.0 to 1.0)
            metadata: Additional metadata
        """
        outcome = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "component": component,
            "quality": quality,
            "metadata": metadata or {},
        }
        self.outcomes.append(outcome)
        
        # Adjust weights based on outcome
        self._adjust_weights_for_outcome(component, quality)
    
    def _adjust_weights_for_outcome(self, component: str, quality: float) -> None:
        """Adjust weights based on outcome quality.
        
        Strategy:
        - If quality is high (>0.8): keep weights stable or increase accuracy weight
        - If quality is medium (0.5-0.8): increase diversity weight
        - If quality is low (<0.5): increase complexity weight (simpler may be better)
        """
        lr = self.config.fitness_learning_rate
        
        if quality > 0.8:
            # High quality: increase accuracy weight slightly
            old = self.config.accuracy_weight
            self.config.accuracy_weight = min(
                self.config.max_weight,
                self.config.accuracy_weight + lr * quality
            )
            self._record_adjustment(
                "accuracy_weight", old, self.config.accuracy_weight,
                f"high quality ({quality:.2f})", quality, component
            )
        
        elif quality > 0.5:
            # Medium quality: increase diversity weight
            old = self.config.diversity_weight
            self.config.diversity_weight = min(
                self.config.max_weight,
                self.config.diversity_weight + lr * (1.0 - quality)
            )
            self._record_adjustment(
                "diversity_weight", old, self.config.diversity_weight,
                f"medium quality ({quality:.2f})", quality, component
            )
        
        else:
            # Low quality: increase complexity weight (simpler trees may be better)
            old = self.config.complexity_weight
            self.config.complexity_weight = min(
                self.config.max_weight,
                self.config.complexity_weight + lr * (1.0 - quality)
            )
            self._record_adjustment(
                "complexity_weight", old, self.config.complexity_weight,
                f"low quality ({quality:.2f})", quality, component
            )
        
        # Normalize weights to sum to 1.0
        self._normalize_weights()
    
    def _normalize_weights(self) -> None:
        """Normalize fitness weights to sum to 1.0."""
        total = (
            self.config.accuracy_weight +
            self.config.complexity_weight +
            self.config.diversity_weight +
            self.config.threshold_weight
        )
        
        if total > 0:
            self.config.accuracy_weight /= total
            self.config.complexity_weight /= total
            self.config.diversity_weight /= total
            self.config.threshold_weight /= total
    
    def _record_adjustment(
        self,
        weight_name: str,
        old_value: float,
        new_value: float,
        reason: str,
        outcome_quality: float,
        component: str,
    ) -> None:
        """Record a weight adjustment."""
        adjustment = WeightAdjustment(
            timestamp=datetime.now(timezone.utc).isoformat(),
            weight_name=weight_name,
            old_value=old_value,
            new_value=new_value,
            reason=reason,
            outcome_quality=outcome_quality,
            component=component,
        )
        self.history.append(adjustment)
    
    def get_adjustment_history(self, limit: int = 10) -> List[WeightAdjustment]:
        """Get recent weight adjustments."""
        return self.history[-limit:]
    
    def get_summary(self) -> Dict[str, Any]:
        """Get summary of weight manager state."""
        return {
            "config": self.config.to_dict(),
            "total_outcomes": len(self.outcomes),
            "total_adjustments": len(self.history),
            "recent_adjustments": [
                {
                    "weight": h.weight_name,
                    "change": f"{h.old_value:.3f} → {h.new_value:.3f}",
                    "reason": h.reason,
                }
                for h in self.history[-5:]
            ],
        }


# Global instance
_manager: Optional[AdaptiveWeightManager] = None


def get_weight_manager() -> AdaptiveWeightManager:
    """Get or create the global weight manager."""
    global _manager
    if _manager is None:
        _manager = AdaptiveWeightManager()
        _manager.load()
    return _manager


def record_outcome(component: str, quality: float, **kwargs: Any) -> None:
    """Record an outcome for weight adjustment."""
    manager = get_weight_manager()
    manager.record_outcome(component, quality, **kwargs)
    manager.save()


def get_fitness_weights() -> Dict[str, float]:
    """Get current fitness weights."""
    return get_weight_manager().get_fitness_weights()


def get_drift_step(accuracy: float = 0.5) -> float:
    """Get adaptive drift step."""
    return get_weight_manager().get_drift_step(accuracy)
