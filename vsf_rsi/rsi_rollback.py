#!/usr/bin/env python3
"""
RSI Rollback — Auto-revert activated strategies if they degrade.

Monitors activated strategies for 50 evaluations.
If accuracy drops below baseline, reverts automatically.

Part of the L3 Autonomous Cycle: detect → generate → shadow → activate.
"""

import json
import logging
import os
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("vsf_rsi.rollback")

# ── Configuration ──────────────────────────────────────────────────
ROLLBACK_DIR = Path(os.environ.get(
    "RSI_ROLLBACK_DIR",
    str(Path(__file__).parent.parent.parent / "state" / "rollback")
))
ROLLBACK_FILE = ROLLBACK_DIR / "rollback_state.json"

MONITOR_WINDOW = 50      # Eval window before permanent activation
REVERT_THRESHOLD = 0.05  # Revert if accuracy drops >5% below baseline


@dataclass
class MonitoredStrategy:
    """A strategy being monitored after activation."""
    strategy_id: str
    fault_id: str
    tree: Dict[str, Any]
    baseline_accuracy: float
    activated_at: str
    evals_since_activation: int = 0
    recent_correct: int = 0
    recent_total: int = 0
    status: str = "monitoring"  # monitoring → confirmed → rolled_back

    @property
    def recent_accuracy(self) -> float:
        if self.recent_total == 0:
            return 0.0
        return self.recent_correct / self.recent_total

    @property
    def below_baseline(self) -> bool:
        return self.recent_accuracy < (self.baseline_accuracy - REVERT_THRESHOLD)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RollbackEvent:
    """Record of a rollback action."""
    strategy_id: str
    fault_id: str
    rolled_back_at: str
    baseline_accuracy: float
    final_accuracy: float
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class RollbackManager:
    """Monitors activated strategies and auto-reverts if they degrade.

    After activation, each strategy is monitored for MONITOR_WINDOW evaluations.
    If accuracy drops below baseline - REVERT_THRESHOLD, it's rolled back.
    If it survives the window, it's confirmed as permanent.
    """

    def __init__(self, engine: Any, metrics: Any = None):
        self.engine = engine
        self.metrics = metrics
        self._monitored: Dict[str, MonitoredStrategy] = {}
        self._rollbacks: List[RollbackEvent] = []
        self._load_state()

    def activate(self, strategy_id: str, fault_id: str,
                 tree: Dict[str, Any], baseline_accuracy: float) -> MonitoredStrategy:
        """Start monitoring a newly activated strategy.

        Args:
            strategy_id: Unique ID for this strategy
            fault_id: The fault it addresses
            tree: The socratic tree for this strategy
            baseline_accuracy: Baseline accuracy to maintain

        Returns:
            MonitoredStrategy for tracking
        """
        monitored = MonitoredStrategy(
            strategy_id=strategy_id,
            fault_id=fault_id,
            tree=tree,
            baseline_accuracy=baseline_accuracy,
            activated_at=datetime.now(timezone.utc).isoformat(),
            status="monitoring",
        )

        self._monitored[strategy_id] = monitored
        self._save_state()

        logger.info(f"Activating strategy {strategy_id} for monitoring "
                    f"(baseline={baseline_accuracy:.1%}, window={MONITOR_WINDOW})")

        return monitored

    def record_evaluation(self, strategy_id: str, correct: bool) -> Optional[str]:
        """Record an evaluation result for a monitored strategy.

        Args:
            strategy_id: Strategy that was evaluated
            correct: Whether the evaluation was correct

        Returns:
            "confirmed" if window survived, "rolled_back" if reverted,
            None if still monitoring
        """
        if strategy_id not in self._monitored:
            return None

        monitored = self._monitored[strategy_id]
        monitored.evals_since_activation += 1
        monitored.recent_total += 1
        if correct:
            monitored.recent_correct += 1

        # Check if monitoring window is complete
        if monitored.evals_since_activation >= MONITOR_WINDOW:
            if monitored.below_baseline:
                return self._rollback(strategy_id, "window_complete_below_baseline")
            else:
                return self._confirm(strategy_id)

        # Check if we should revert early (too many failures)
        if monitored.recent_total >= 10 and monitored.below_baseline:
            return self._rollback(strategy_id, "early_revert_accuracy_drop")

        self._save_state()
        return None

    def _confirm(self, strategy_id: str) -> str:
        """Confirm strategy as permanent."""
        self._monitored[strategy_id].status = "confirmed"
        self._save_state()
        logger.info(f"Strategy {strategy_id} CONFIRMED — "
                    f"survived {MONITOR_WINDOW} evals "
                    f"(accuracy={self._monitored[strategy_id].recent_accuracy:.1%})")
        return "confirmed"

    def _rollback(self, strategy_id: str, reason: str) -> str:
        """Rollback a strategy."""
        monitored = self._monitored[strategy_id]
        monitored.status = "rolled_back"

        event = RollbackEvent(
            strategy_id=strategy_id,
            fault_id=monitored.fault_id,
            rolled_back_at=datetime.now(timezone.utc).isoformat(),
            baseline_accuracy=monitored.baseline_accuracy,
            final_accuracy=monitored.recent_accuracy,
            reason=reason,
        )
        self._rollbacks.append(event)
        self._save_state()

        logger.warning(f"Strategy {strategy_id} ROLLED BACK — {reason} "
                       f"(baseline={monitored.baseline_accuracy:.1%}, "
                       f"final={monitored.recent_accuracy:.1%})")
        return "rolled_back"

    def get_monitored(self) -> List[MonitoredStrategy]:
        return [m for m in self._monitored.values() if m.status == "monitoring"]

    def get_confirmed(self) -> List[MonitoredStrategy]:
        return [m for m in self._monitored.values() if m.status == "confirmed"]

    def get_rolled_back(self) -> List[RollbackEvent]:
        return list(self._rollbacks)

    def get_tree(self, strategy_id: str) -> Optional[Dict[str, Any]]:
        """Get the tree for a monitored/confirmed strategy."""
        if strategy_id in self._monitored:
            return self._monitored[strategy_id].tree
        return None

    def _load_state(self):
        try:
            if ROLLBACK_FILE.exists():
                with open(ROLLBACK_FILE) as f:
                    data = json.load(f)
                for sid, sdata in data.get("monitored", {}).items():
                    self._monitored[sid] = MonitoredStrategy(**sdata)
                for rdata in data.get("rollbacks", []):
                    self._rollbacks.append(RollbackEvent(**rdata))
        except Exception as e:
            logger.warning(f"Failed to load rollback state: {e}")

    def _save_state(self):
        try:
            ROLLBACK_DIR.mkdir(parents=True, exist_ok=True)
            with open(ROLLBACK_FILE, "w") as f:
                json.dump({
                    "monitored": {sid: m.to_dict() for sid, m in self._monitored.items()},
                    "rollbacks": [r.to_dict() for r in self._rollbacks],
                }, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save rollback state: {e}")


# ── CLI ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m vsf_rsi.rsi_rollback <command>")
        print("Commands:")
        print("  monitored  — strategies under monitoring")
        print("  confirmed  — confirmed strategies")
        print("  rollbacks  — rollback events")
        sys.exit(1)

    mgr = RollbackManager.__new__(RollbackManager)
    mgr._monitored = {}
    mgr._rollbacks = []
    mgr._load_state()

    cmd = sys.argv[1]
    if cmd == "monitored":
        items = mgr.get_monitored()
        for m in items:
            print(f"  {m.strategy_id}: evals={m.evals_since_activation}/{MONITOR_WINDOW}, "
                  f"accuracy={m.recent_accuracy:.1%}")
    elif cmd == "confirmed":
        items = mgr.get_confirmed()
        for m in items:
            print(f"  {m.strategy_id}: accuracy={m.recent_accuracy:.1%}")
    elif cmd == "rollbacks":
        items = mgr.get_rolled_back()
        for r in items:
            print(f"  {r.strategy_id}: {r.reason} "
                  f"(baseline={r.baseline_accuracy:.1%}, final={r.final_accuracy:.1%})")
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
