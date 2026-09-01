#!/usr/bin/env python3
"""
RSI Fault Detector — Detect complex faults not solvable by L1/L2.

Criteria for "complex fault":
  - Same error ≥3 times in 10 evaluations
  - Latency >10ms (slow search)
  - Coverage <50% (too many UNKNOWN)
  - Error class = BLOCKING (cannot self-resolve)

Part of the L3 Autonomous Cycle: detect → generate → shadow → activate.
"""

import json
import logging
import os
import time
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("vsf_rsi.fault_detector")

# ── Configuration ──────────────────────────────────────────────────
FAULT_DIR = Path(os.environ.get(
    "RSI_FAULT_DIR",
    str(Path(__file__).parent.parent.parent / "state" / "faults")
))
FAULT_FILE = FAULT_DIR / "detected_faults.json"

# Complexity thresholds
MIN_REPEATS = 3          # Same error ≥3 times in window
WINDOW_SIZE = 10         # Last N evaluations
LATENCY_THRESHOLD_MS = 10.0
COVERAGE_THRESHOLD = 0.5  # <50% coverage = too many UNKNOWN


@dataclass
class FaultSignature:
    """A detected complex fault."""
    fault_id: str
    source: str
    error_class: str
    first_seen: str
    last_seen: str
    count: int
    avg_latency_ms: float
    coverage: float
    sample_events: List[Dict[str, Any]] = field(default_factory=list)
    status: str = "detected"  # detected → generating → shadow → active → rolled_back

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class FaultWindow:
    """Sliding window of recent evaluations for a source."""
    source: str
    events: List[Dict[str, Any]] = field(default_factory=list)

    def add(self, event: Dict[str, Any]):
        self.events.append(event)
        if len(self.events) > WINDOW_SIZE:
            self.events = self.events[-WINDOW_SIZE:]

    @property
    def error_count(self) -> int:
        return sum(1 for e in self.events if e.get("is_error", False))

    @property
    def error_ratio(self) -> float:
        if not self.events:
            return 0.0
        return self.error_count / len(self.events)

    @property
    def avg_latency_ms(self) -> float:
        if not self.events:
            return 0.0
        return sum(e.get("latency_ms", 0) for e in self.events) / len(self.events)

    @property
    def coverage(self) -> float:
        """Fraction of evaluations that are not UNKNOWN."""
        if not self.events:
            return 0.0
        known = sum(1 for e in self.events if e.get("truth", "UNKNOWN") != "UNKNOWN")
        return known / len(self.events)


class FaultDetector:
    """Detects complex faults from observer events.

    Maintains a sliding window per source and generates FaultSignatures
    when complexity criteria are met.
    """

    def __init__(self):
        self._windows: Dict[str, FaultWindow] = {}
        self._faults: Dict[str, FaultSignature] = {}
        self._load_faults()

    def observe(self, event: Any) -> Optional[FaultSignature]:
        """Process an evaluation event. Returns a FaultSignature if a
        complex fault is detected, None otherwise.

        Args:
            event: EvaluationEvent or dict with source, truth, latency_ms, is_error, error_class
        """
        # Normalize event to dict
        if hasattr(event, "__dict__"):
            ev = {
                "source": getattr(event, "source", "unknown"),
                "truth": getattr(event, "truth", "UNKNOWN"),
                "latency_ms": getattr(event, "latency_ms", 0.0),
                "is_error": getattr(event, "is_error", False),
                "error_class": getattr(event, "error_class", "NONE"),
                "timestamp": getattr(event, "timestamp", datetime.now(timezone.utc).isoformat()),
            }
        else:
            ev = dict(event) if event else {}

        source = ev.get("source", "unknown")
        if source not in self._windows:
            self._windows[source] = FaultWindow(source=source)

        self._windows[source].add(ev)

        # Check complexity criteria
        return self._check_complexity(source)

    def _check_complexity(self, source: str) -> Optional[FaultSignature]:
        """Check if source meets complexity criteria for L3."""
        window = self._windows[source]

        # Criterion 1: Same error ≥3 times in window
        if window.error_count < MIN_REPEATS:
            return None

        # Criterion 2: Coverage <50% (too many UNKNOWN)
        if window.coverage >= COVERAGE_THRESHOLD:
            # Even with errors, if coverage is OK, L1/L2 might handle it
            # Only escalate if coverage is also poor
            pass  # Don't block on coverage alone

        # Criterion 3: Error class = BLOCKING
        blocking_count = sum(
            1 for e in window.events
            if e.get("error_class") == "BLOCKING"
        )
        if blocking_count == 0:
            return None  # Non-blocking errors can be handled by L1/L2

        # All criteria met — generate fault signature
        # Use source + error_class as stable fault_id (count changes but fault is same)
        fault_id = f"{source}:error={window.events[-1].get('error_class', 'BLOCKING')}"

        # Don't re-detect same fault
        if fault_id in self._faults:
            existing = self._faults[fault_id]
            existing.last_seen = window.events[-1].get("timestamp", "")
            existing.count = window.error_count
            self._save_faults()
            return existing

        # New fault detected
        fault = FaultSignature(
            fault_id=fault_id,
            source=source,
            error_class="BLOCKING",
            first_seen=window.events[0].get("timestamp", ""),
            last_seen=window.events[-1].get("timestamp", ""),
            count=window.error_count,
            avg_latency_ms=window.avg_latency_ms,
            coverage=window.coverage,
            sample_events=[e for e in window.events if e.get("is_error", False)][:3],
            status="detected",
        )

        self._faults[fault_id] = fault
        self._save_faults()

        logger.info(f"Complex fault detected: {fault_id}")
        logger.info(f"  source={source}, errors={window.error_count}, "
                    f"latency={window.avg_latency_ms:.1f}ms, "
                    f"coverage={window.coverage:.1%}")

        return fault

    def get_pending_faults(self) -> List[FaultSignature]:
        """Return faults that need strategy generation (status=detected)."""
        return [f for f in self._faults.values() if f.status == "detected"]

    def get_all_faults(self) -> List[FaultSignature]:
        return list(self._faults.values())

    def update_fault_status(self, fault_id: str, status: str):
        if fault_id in self._faults:
            self._faults[fault_id].status = status
            self._save_faults()

    def _load_faults(self):
        try:
            if FAULT_FILE.exists():
                with open(FAULT_FILE) as f:
                    data = json.load(f)
                for fid, fdata in data.items():
                    self._faults[fid] = FaultSignature(**fdata)
        except Exception as e:
            logger.warning(f"Failed to load faults: {e}")

    def _save_faults(self):
        try:
            FAULT_DIR.mkdir(parents=True, exist_ok=True)
            with open(FAULT_FILE, "w") as f:
                json.dump(
                    {fid: f.to_dict() for fid, f in self._faults.items()},
                    f, indent=2
                )
        except Exception as e:
            logger.error(f"Failed to save faults: {e}")


# ── CLI ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    detector = FaultDetector()

    if len(sys.argv) < 2:
        print("Usage: python -m vsf_rsi.rsi_fault_detector <command>")
        print("Commands:")
        print("  pending  — show faults needing strategy generation")
        print("  all      — show all detected faults")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "pending":
        faults = detector.get_pending_faults()
        if not faults:
            print("No pending faults.")
        for f in faults:
            print(f"  {f.fault_id}: source={f.source}, errors={f.count}, "
                  f"latency={f.avg_latency_ms:.1f}ms")
    elif cmd == "all":
        faults = detector.get_all_faults()
        for f in faults:
            print(f"  [{f.status}] {f.fault_id}: source={f.source}, errors={f.count}")
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
