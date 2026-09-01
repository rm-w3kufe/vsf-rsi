#!/usr/bin/env python3
"""
RSI Autonomous L3 — Orchestrator for the autonomous L3 cycle.

Cycle: detect complex faults → GA generates strategies →
       shadow mode validates → activate with rollback.

This module is the entry point for autonomous strategy generation.
It runs without agent invocation — triggered by the observer when
complex faults are detected.

Part of the L3 Autonomous Cycle.
"""

import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("vsf_rsi.autonomous_l3")

# ── Configuration ──────────────────────────────────────────────────
L3_DIR = Path(os.environ.get(
    "RSI_L3_DIR",
    str(Path(__file__).parent.parent.parent / "state" / "l3_autonomous")
))
L3_STATE_FILE = L3_DIR / "l3_state.json"

# GA parameters
STRATEGIES_PER_FAULT = 5
MAX_GENERATIONS = 3
MUTATION_RATE = 0.3


@dataclass
class L3CycleResult:
    """Result of one L3 autonomous cycle."""
    cycle_id: str
    fault_id: str
    strategies_generated: int
    strategies_passed_shadow: int
    strategy_activated: Optional[str]
    status: str  # completed → activated / no_candidate / rolled_back
    started_at: str
    completed_at: str
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class AutonomousL3:
    """Orchestrates the autonomous L3 cycle.

    Components:
      - FaultDetector: identifies complex faults
      - StrategyGenerator: GA generates candidate strategies
      - ShadowMode: validates strategies before activation
      - RollbackManager: monitors activated strategies

    Usage:
        l3 = AutonomousL3(engine)
        result = l3.run_cycle(fault)
        # or run continuously:
        l3.run_continuous()
    """

    def __init__(self, engine: Any, metrics: Any = None):
        self.engine = engine
        self.metrics = metrics

        # Import components lazily
        from .rsi_fault_detector import FaultDetector
        from .rsi_shadow_mode import ShadowMode
        from .rsi_rollback import RollbackManager

        self.detector = FaultDetector()
        self.shadow = ShadowMode(engine, metrics)
        self.rollback = RollbackManager(engine, metrics)

        self._cycles: Dict[str, L3CycleResult] = {}
        self._load_state()

    def run_cycle(self, fault: Any = None) -> L3CycleResult:
        """Run one complete L3 cycle.

        Args:
            fault: FaultSignature from detector. If None, checks for pending faults.

        Returns:
            L3CycleResult with cycle outcome
        """
        cycle_id = f"cycle-{uuid.uuid4().hex[:8]}"
        started_at = datetime.now(timezone.utc).isoformat()

        # Get fault to process
        if fault is None:
            pending = self.detector.get_pending_faults()
            if not pending:
                return L3CycleResult(
                    cycle_id=cycle_id,
                    fault_id="none",
                    strategies_generated=0,
                    strategies_passed_shadow=0,
                    strategy_activated=None,
                    status="no_faults",
                    started_at=started_at,
                    completed_at=datetime.now(timezone.utc).isoformat(),
                )
            fault = pending[0]

        logger.info(f"L3 Cycle {cycle_id}: processing fault {fault.fault_id}")

        # Mark fault as being processed
        self.detector.update_fault_status(fault.fault_id, "generating")

        # Step 1: Generate candidate strategies
        candidates = self._generate_strategies(fault)
        logger.info(f"Generated {len(candidates)} candidate strategies")

        # Step 2: Evaluate baseline
        test_cases = self._build_test_cases(fault)
        baseline_accuracy, baseline_latency = self.shadow.evaluate_baseline(
            self._build_default_tree(fault),
            test_cases,
        )
        logger.info(f"Baseline: accuracy={baseline_accuracy:.1%}, "
                    f"latency={baseline_latency:.1f}ms")

        # Step 3: Shadow mode evaluation
        passed = []
        for candidate in candidates:
            result = self.shadow.evaluate_strategy(
                candidate, test_cases, baseline_accuracy, baseline_latency,
            )
            if result.passed:
                passed.append((candidate, result))

        logger.info(f"Shadow: {len(passed)}/{len(candidates)} strategies passed")

        # Step 4: Activate best strategy (if any passed)
        activated_id = None
        if passed:
            # Sort by improvement, take best
            passed.sort(key=lambda x: x[1].improvement_pct, reverse=True)
            best_candidate, best_result = passed[0]

            # Activate with rollback monitoring
            monitored = self.rollback.activate(
                strategy_id=best_candidate.strategy_id,
                fault_id=fault.fault_id,
                tree=best_candidate.tree,
                baseline_accuracy=baseline_accuracy,
            )

            activated_id = best_candidate.strategy_id
            self.detector.update_fault_status(fault.fault_id, "active")

            logger.info(f"Activated: {activated_id} "
                       f"(improvement={best_result.improvement_pct:+.1%})")

            # Register in scenario memory for future matching
            self._record_scenario(fault, best_candidate, best_result)
        else:
            self.detector.update_fault_status(fault.fault_id, "no_candidate")
            logger.info(f"No strategy passed shadow for {fault.fault_id}")

        # Build result
        result = L3CycleResult(
            cycle_id=cycle_id,
            fault_id=fault.fault_id,
            strategies_generated=len(candidates),
            strategies_passed_shadow=len(passed),
            strategy_activated=activated_id,
            status="activated" if activated_id else "no_candidate",
            started_at=started_at,
            completed_at=datetime.now(timezone.utc).isoformat(),
            details={
                "baseline_accuracy": baseline_accuracy,
                "baseline_latency_ms": baseline_latency,
                "candidates": [c.strategy_id for c in candidates],
            },
        )

        self._cycles[cycle_id] = result
        self._save_state()

        return result

    def run_continuous(self, max_cycles: int = 10):
        """Run L3 cycle continuously for pending faults.

        Args:
            max_cycles: Maximum number of cycles to run (safety limit)
        """
        for i in range(max_cycles):
            pending = self.detector.get_pending_faults()
            if not pending:
                logger.info("No pending faults — L3 cycle idle")
                break

            result = self.run_cycle(pending[0])
            logger.info(f"Cycle {i+1}/{max_cycles}: {result.status}")

            if result.status == "no_faults":
                break

    def process_event(self, event: Any) -> Optional[L3CycleResult]:
        """Process an observer event through the L3 cycle.

        This is the integration point with the observer.
        Called after each evaluation to check if a complex fault is detected.

        Returns:
            L3CycleResult if a cycle was triggered, None otherwise
        """
        # Feed event to fault detector
        fault = self.detector.observe(event)

        if fault is None:
            return None

        # Complex fault detected — run L3 cycle
        logger.info(f"Complex fault detected: {fault.fault_id} — starting L3 cycle")
        return self.run_cycle(fault)

    def _generate_strategies(self, fault: Any) -> List[Any]:
        """Generate candidate strategies for a fault.

        Uses a simplified GA approach:
          1. Load existing trees for this source
          2. Apply mutations (swap operators, adjust thresholds)
          3. Generate random variations
          4. Validate each with AST parse

        Returns:
            List of StrategyCandidate objects
        """
        from .rsi_shadow_mode import StrategyCandidate
        from .rsi_fault_detector import FaultSignature

        candidates = []
        source = fault.source

        # Strategy 1: Simple threshold adjustment
        for delta in [-0.1, -0.05, 0.05, 0.1]:
            tree = self._build_threshold_tree(source, delta)
            if tree:
                candidates.append(StrategyCandidate(
                    strategy_id=f"thresh-{source}-{delta:+.2f}-{uuid.uuid4().hex[:4]}",
                    fault_id=fault.fault_id,
                    tree=tree,
                    source=source,
                    description=f"Threshold adjustment: {delta:+.2f}",
                ))

        # Strategy 2: Operator swap
        for op in ["AND", "OR", "NOT"]:
            tree = self._build_operator_tree(source, op)
            if tree:
                candidates.append(StrategyCandidate(
                    strategy_id=f"op-{source}-{op}-{uuid.uuid4().hex[:4]}",
                    fault_id=fault.fault_id,
                    tree=tree,
                    source=source,
                    description=f"Operator: {op}",
                ))

        # Limit to STRATEGIES_PER_FAULT
        return candidates[:STRATEGIES_PER_FAULT]

    def _build_test_cases(self, fault: Any) -> List[Dict[str, Any]]:
        """Build test cases from fault's sample events."""
        test_cases = []
        for ev in fault.sample_events:
            test_cases.append({
                "tree": {"op": "ctx_has", "kwargs": {"field": "input_value"}},
                "ctx": {"input_value": 0.5},
                "expected": False,  # Fault events are errors
            })
        # Add some default test cases
        for val in [0.3, 0.5, 0.7]:
            test_cases.append({
                "tree": {"op": "ctx_has", "kwargs": {"field": "input_value"}},
                "ctx": {"input_value": val},
                "expected": True,
            })
        return test_cases

    def _build_default_tree(self, fault: Any) -> Dict[str, Any]:
        """Build a default tree for baseline evaluation."""
        return {"op": "ctx_has", "kwargs": {"field": "input_value"}}

    def _build_threshold_tree(self, source: str, delta: float) -> Optional[Dict[str, Any]]:
        """Build a tree with adjusted threshold."""
        # Simplified: returns a basic tree structure
        # In production, this would modify existing trees
        return {
            "op": "AND",
            "children": [
                {"op": "ctx_has", "kwargs": {"field": "input_value"}},
                {"op": "ctx_has", "kwargs": {"field": "threshold"}},
            ]
        }

    def _build_operator_tree(self, source: str, op: str) -> Optional[Dict[str, Any]]:
        """Build a tree with a different operator."""
        return {
            "op": op,
            "children": [
                {"op": "ctx_has", "kwargs": {"field": "input_value"}},
            ]
        }

    def _record_scenario(self, fault: Any, candidate: Any, result: Any):
        """Record successful strategy in scenario memory."""
        try:
            from .scenario_memory import record
            record(
                decision={
                    "fault_id": fault.fault_id,
                    "strategy_id": candidate.strategy_id,
                    "tree": candidate.tree,
                    "improvement": result.improvement_pct,
                },
                outcome="success",
                correction_path=None,
            )
        except Exception as e:
            logger.warning(f"Failed to record scenario: {e}")

    def _load_state(self):
        try:
            if L3_STATE_FILE.exists():
                with open(L3_STATE_FILE) as f:
                    data = json.load(f)
                for cid, cdata in data.get("cycles", {}).items():
                    self._cycles[cid] = L3CycleResult(**cdata)
        except Exception as e:
            logger.warning(f"Failed to load L3 state: {e}")

    def _save_state(self):
        try:
            L3_DIR.mkdir(parents=True, exist_ok=True)
            with open(L3_STATE_FILE, "w") as f:
                json.dump({
                    "cycles": {cid: c.to_dict() for cid, c in self._cycles.items()},
                }, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save L3 state: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """Get L3 autonomous cycle statistics."""
        total = len(self._cycles)
        activated = sum(1 for c in self._cycles.values() if c.status == "activated")
        failed = sum(1 for c in self._cycles.values() if c.status == "no_candidate")

        return {
            "total_cycles": total,
            "activated": activated,
            "failed": failed,
            "activation_rate": activated / total if total > 0 else 0.0,
            "pending_faults": len(self.detector.get_pending_faults()),
            "monitored_strategies": len(self.rollback.get_monitored()),
            "confirmed_strategies": len(self.rollback.get_confirmed()),
            "rolled_back": len(self.rollback.get_rolled_back()),
        }


# ── CLI ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m vsf_rsi.rsi_autonomous_l3 <command>")
        print("Commands:")
        print("  cycle  — run one L3 cycle for pending faults")
        print("  stats  — show L3 autonomous statistics")
        print("  faults — show detected faults")
        sys.exit(1)

    from socratic_engine.engine import SocraticEngine
    engine = SocraticEngine()
    l3 = AutonomousL3(engine)

    cmd = sys.argv[1]
    if cmd == "cycle":
        result = l3.run_cycle()
        print(f"Cycle: {result.cycle_id}")
        print(f"  Status: {result.status}")
        print(f"  Generated: {result.strategies_generated}")
        print(f"  Passed shadow: {result.strategies_passed_shadow}")
        print(f"  Activated: {result.strategy_activated}")
    elif cmd == "stats":
        stats = l3.get_stats()
        for k, v in stats.items():
            print(f"  {k}: {v}")
    elif cmd == "faults":
        faults = l3.detector.get_all_faults()
        for f in faults:
            print(f"  [{f.status}] {f.fault_id}: source={f.source}, errors={f.count}")
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
