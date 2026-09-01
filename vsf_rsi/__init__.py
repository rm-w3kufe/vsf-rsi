"""
vsf-rsi — Recursive Self-Improvement for VSM systems

A cybernetic feedback loop that observes, evaluates, and improves
socratic-engine predicates and trees through parameter drift,
capability extension, predicate generation, and genetic evolution.
"""

__version__ = "0.2.9"

from .rsi_observer import RSIObserver, RSIMode
from .rsi_metrics import RSIMetrics
from . import scenario_memory

__all__ = [
    "RSIObserver",
    "RSIMode",
    "RSIMetrics",
    "scenario_memory",
    "genome_v3",
]
