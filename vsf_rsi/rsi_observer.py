#!/usr/bin/env python3
"""
RSI Observer — Integration bridge between socratic-engine and rsi_metrics.

design: docs/spec_revision/design-sources/rsi-observer-v1/rsi_observer_design.vsm

Wraps SocraticEngine.evaluate() to:
  1. Capture EvaluationEvents (truth, certified, source, latency)
  2. Bridge to rsi_metrics via track_classification()
  3. Discriminate errors (BLOCKING / STRUCTURAL / NONE)
  4. Resolve errors (parameter_drift or capability_extension)

RSI Modes:
  CAPABILITY (default): parameter_drift + capability_extension
  SAFE:                 parameter_drift only

Future: get_expected() will plug into VSM kernel for multi-source truth.
"""

import json
import os
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

# ── Imports from sibling modules ──────────────────────────────────
import sys
_classifier_dir = Path(__file__).parent
if str(_classifier_dir) not in sys.path:
    sys.path.insert(0, str(_classifier_dir))

from vsf_rsi.rsi_metrics import RSIMetrics

# Import socratic_engine types (required)
try:
    from socratic_engine.engine import Truth
except ImportError:
    # Fallback if socratic_engine not available
    class Truth:
        TRUE = "TRUE"
        FALSE = "FALSE"
        UNKNOWN = "UNKNOWN"

# Import scenario_memory (optional, from system path or package)
try:
    import scenario_memory as _sm
    _HAS_SCENARIO_MEMORY = True
except ImportError:
    _sm = None
    _HAS_SCENARIO_MEMORY = False

# Import rsi_predicate_generator (optional)
try:
    from vsf_rsi.rsi_predicate_generator import RSIPredicateGenerator
    _HAS_PREDICATE_GENERATOR = True
except ImportError:
    _HAS_PREDICATE_GENERATOR = False

# Import rsi_genetic_algorithm (optional)
try:
    from vsf_rsi.rsi_genetic_algorithm import RSIGeneticAlgorithm, TreeGenome
    _HAS_GENETIC_ALGORITHM = True
except ImportError:
    _HAS_GENETIC_ALGORITHM = False


# ── Constants ─────────────────────────────────────────────────────

class RSIMode(str, Enum):
    CAPABILITY = "CAPABILITY"
    SAFE = "SAFE"


class ErrorClass(str, Enum):
    NONE = "NONE"
    BLOCKING = "BLOCKING"
    STRUCTURAL = "STRUCTURAL"


class ActionLevel(str, Enum):
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"
    L4 = "L4"


# Default thresholds (fallback if rsi_thresholds.json doesn't exist)
DEFAULT_THRESHOLDS: Dict[str, float] = {
    "ac_stasis_critical": 0.70,
    "ac_stasis_warning": 0.80,
    "ac_viable_false": 0.50,
}

# BUG-002: Threshold drift bounds (prevent drift to 0 or infinity)
MIN_THRESHOLD: float = 0.05
MAX_THRESHOLD: float = 0.95
THRESHOLD_STEP: float = 0.05

# BUG-003: Memory leak prevention (circular buffer for events)
MAX_EVENTS: int = 1000

# BUG-001: Type validation (valid input types for comparison)
VALID_INPUT_TYPES = (int, float)


# ── Data Classes ──────────────────────────────────────────────────

@dataclass
class EvaluationEvent:
    """
    Captures each socratic-engine evaluation.
    Populated by the observer wrapper.
    """
    # From wrapper (automatic)
    tree_id: str = ""
    timestamp: str = ""
    latency_ms: float = 0.0

    # From Evaluation (extracted)
    source: str = ""
    truth: str = "UNKNOWN"
    certified: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    # From context (injected by caller)
    task_id: str = ""
    threshold: float = 0.70
    input_value: float = 0.5

    # Derived
    actual: bool = False
    expected: bool = False
    is_error: bool = False
    error_class: str = "NONE"


@dataclass
class RSIAction:
    """
    Action that the observer takes or proposes.
    Generated when an error is discriminated.
    """
    event: EvaluationEvent
    level: str = "L1"
    action_type: str = ""
    params: Dict[str, Any] = field(default_factory=dict)
    autonomous: bool = True
    resolution: str = ""


# ── Core Functions ────────────────────────────────────────────────

def get_expected(input_value: float, optimal_threshold: float) -> bool:
    """
    Derive ground truth: error expected when input_value is BELOW threshold.
    The predicate fires (TRUE) when input < threshold (danger zone).
    If input < threshold, we expect TRUE. If predicate returns FALSE → error.

    FUTURE: This function will be replaced by:
        vsm_kernel.calculate_truth(sources, viable_region)
    when the VSM recursive kernel is integrated.
    """
    return input_value < optimal_threshold


def load_thresholds() -> Dict[str, float]:
    """Load thresholds from rsi_thresholds.json, falling back to defaults."""
    thresholds_file = (
        Path(__file__).parent.parent.parent
        / "state" / "monitoring" / "rsi_thresholds.json"
    )
    if thresholds_file.exists():
        try:
            with open(thresholds_file, "r") as f:
                loaded = json.load(f)
            # Merge with defaults (defaults fill missing keys)
            result = dict(DEFAULT_THRESHOLDS)
            result.update(loaded)
            return result
        except (json.JSONDecodeError, OSError):
            pass
    return dict(DEFAULT_THRESHOLDS)


def discriminate(
    event: EvaluationEvent,
    memory: Optional[Dict[str, List[str]]] = None,
) -> str:
    """
    Classify error as BLOCKING, STRUCTURAL, or NONE.

    Criteria (in priority order):
      1. Does the error block the next step? → BLOCKING
      2. Is this the first occurrence? → likely BLOCKING
      3. Is the predicate certified? → BLOCKING (motor can't decide safely)
      4. Is there a similar scenario in memory? → apply previous resolution
    """
    if not event.is_error:
        return ErrorClass.NONE.value

    # Criterion 3: certified predicates are critical
    if event.certified:
        return ErrorClass.BLOCKING.value

    # Criterion 2: first occurrence → treat as blocking
    if memory is not None:
        if event.source not in memory:
            return ErrorClass.BLOCKING.value
        # Criterion 4: known scenario → structural
        return ErrorClass.STRUCTURAL.value

    # Default: blocking (conservative — assume critical without memory)
    return ErrorClass.BLOCKING.value


def match_scenario(fault_signature: str) -> Optional[str]:
    """
    Match a fault signature against scenario_memory.
    Returns correction_path if found, None otherwise.
    """
    if not _HAS_SCENARIO_MEMORY:
        return None
    try:
        result = _sm.match(fault_signature, threshold=0.3)
        if result is not None:
            scenario_id, correction_path = result
            # Guard against recursive scenario_match prefixes
            if correction_path.startswith("scenario_match"):
                return None
            return correction_path
    except Exception:
        pass
    return None


def record_scenario(
    event: EvaluationEvent,
    action: RSIAction,
    outcome: str = "resolved",
) -> Optional[str]:
    """
    Record a scenario in scenario_memory for future matching.
    Returns scenario_id if recorded, None otherwise.
    """
    if not _HAS_SCENARIO_MEMORY:
        return None
    try:
        fault_sig = f"{event.source}:error={event.error_class}"
        decision = f"evaluate({event.source}, truth={event.truth})"
        correction = action.resolution or action.action_type
        scenario_id = _sm.record(
            decision=decision,
            outcome=outcome,
            correction_path=correction,
            fault_signature=fault_sig,
        )
        return scenario_id
    except Exception:
        return None


# ── L3: Predicate Generation from Error Patterns ────────────────

def analyze_error_patterns(events: List[EvaluationEvent]) -> List[Dict[str, Any]]:
    """
    Analyze error events to detect patterns.
    Returns a list of patterns, each with:
      - source: predicate name
      - error_class: BLOCKING/STRUCTURAL
      - count: number of occurrences
      - avg_threshold: average threshold when errors occurred
      - avg_input: average input value when errors occurred
      - correction: most common correction path
    """
    from collections import Counter, defaultdict

    # Group errors by source
    by_source = defaultdict(list)
    for e in events:
        if e.is_error:
            by_source[e.source].append(e)

    patterns = []
    for source, source_events in by_source.items():
        if len(source_events) < 2:
            continue  # Need at least 2 occurrences for a pattern

        error_classes = [e.error_class for e in source_events]
        most_common_class = Counter(error_classes).most_common(1)[0][0]

        thresholds = [e.threshold for e in source_events]
        inputs = [e.input_value for e in source_events]

        patterns.append({
            "source": source,
            "error_class": most_common_class,
            "count": len(source_events),
            "avg_threshold": sum(thresholds) / len(thresholds),
            "avg_input": sum(inputs) / len(inputs),
            "error_ratio": len(source_events) / len(events) if events else 0,
        })

    # Sort by count (most frequent first)
    patterns.sort(key=lambda p: p["count"], reverse=True)
    return patterns


def generate_predicate_from_pattern(
    pattern: Dict[str, Any],
    engine: Any = None,
) -> Optional[RSIAction]:
    """
    L3: Generate a new predicate from an error pattern.
    Returns an RSIAction proposing the new predicate.
    """
    if not _HAS_PREDICATE_GENERATOR:
        return None

    source = pattern["source"]
    new_name = f"_rsi_gen_{source}"

    # Check if already exists in engine
    if engine and new_name in engine.predicates:
        return RSIAction(
            event=EvaluationEvent(source=source),
            level=ActionLevel.L3.value,
            action_type="generate_predicate_exists",
            params={"name": new_name},
            autonomous=True,
            resolution=f"predicate_already_exists:{new_name}",
        )

    # Create pattern for generator
    gen_pattern = {
        "name": new_name,
        "purpose": f"Auto-generated from {pattern['count']} errors on {source}",
        "template": "edge_case_predicate",
        "base_predicate": source,
        "error_class": pattern["error_class"],
        "avg_threshold": pattern["avg_threshold"],
        "avg_input": pattern["avg_input"],
    }

    try:
        generator = RSIPredicateGenerator()
        filepath = generator.generate_predicate(gen_pattern, base_predicate=source)

        return RSIAction(
            event=EvaluationEvent(source=source),
            level=ActionLevel.L3.value,
            action_type="generate_predicate",
            params={
                "name": new_name,
                "filepath": filepath,
                "pattern": pattern,
            },
            autonomous=False,  # L3 requires human approval
            resolution=f"predicate_generated:{new_name}(file={filepath})",
        )
    except Exception as e:
        return RSIAction(
            event=EvaluationEvent(source=source),
            level=ActionLevel.L3.value,
            action_type="generate_predicate_failed",
            params={"name": new_name, "error": str(e)},
            autonomous=False,
            resolution=f"generation_failed:{e}",
        )


def generate_predicate_if_warranted(
    events: List[EvaluationEvent],
    engine: Any = None,
    min_occurrences: int = 3,
) -> List[RSIAction]:
    """
    L3: Analyze events and generate predicates for frequent error patterns.
    Only generates if a pattern has at least min_occurrences errors.
    """
    patterns = analyze_error_patterns(events)
    actions = []

    for pattern in patterns:
        if pattern["count"] >= min_occurrences:
            action = generate_predicate_from_pattern(pattern, engine)
            if action is not None:
                actions.append(action)

    return actions


# ── L4: Genetic Evolution of Predicates ─────────────────────────

def evolve_predicate_population(
    predicate_name: str,
    generations: int = 5,
    population_size: int = 10,
    mutation_rate: float = 0.1,
) -> Optional[RSIAction]:
    """
    L4: Evolve a population of predicates using genetic algorithms.
    Requires human approval.
    """
    if not _HAS_GENETIC_ALGORITHM:
        return None

    try:
        ga = RSIGeneticAlgorithm(
            population_size=population_size,
            mutation_rate=mutation_rate,
        )

        # Create initial forest
        forest = ga.create_forest(predicate_name)

        # Evolve for N generations
        best_genome = None
        for gen in range(generations):
            forest = ga.evaluate_fitness(forest, predicate_name)
            forest = ga.select_parents(forest, method="tournament")
            forest = ga.crossover_population(forest)
            forest = ga.mutate_population(forest)
            forest = ga.next_generation(forest, predicate_name)

            # Track best
            if forest:
                best = max(forest, key=lambda g: g.fitness)
                if best_genome is None or best.fitness > best_genome.fitness:
                    best_genome = best

        if best_genome is None:
            return None

        return RSIAction(
            event=EvaluationEvent(source=predicate_name),
            level=ActionLevel.L4.value,
            action_type="evolve_forest",
            params={
                "predicate_name": predicate_name,
                "generations": generations,
                "population_size": population_size,
                "best_fitness": round(best_genome.fitness, 4),
                "best_id": best_genome.id,
            },
            autonomous=False,  # L4 requires human approval
            resolution=f"evolved:{best_genome.id}(fitness={best_genome.fitness:.4f})",
        )
    except Exception as e:
        return RSIAction(
            event=EvaluationEvent(source=predicate_name),
            level=ActionLevel.L4.value,
            action_type="evolve_forest_failed",
            params={"predicate_name": predicate_name, "error": str(e)},
            autonomous=False,
            resolution=f"evolution_failed:{e}",
        )


def evolve_if_warranted(
    events: List[EvaluationEvent],
    min_errors: int = 10,
    generations: int = 5,
) -> List[RSIAction]:
    """
    L4: Evolve predicates that have enough error history.
    Only evolves if a predicate has at least min_errors errors.
    """
    from collections import Counter

    # Count errors per source
    error_sources = [e.source for e in events if e.is_error]
    counts = Counter(error_sources)

    actions = []
    for source, count in counts.items():
        if count >= min_errors:
            action = evolve_predicate_population(
                source, generations=generations
            )
            if action is not None:
                actions.append(action)

    return actions


def resolve_error(
    event: EvaluationEvent,
    ctx: Dict[str, Any],
    mode: str = RSIMode.CAPABILITY.value,
    engine: Any = None,
    tree: Any = None,
) -> Optional[RSIAction]:
    """
    Attempt to resolve a BLOCKING error.

    Mode SAFE: only parameter_drift (adjust context).
    Mode CAPABILITY: parameter_drift + capability_extension (inject components).

    Returns RSIAction describing what was done, or None if unresolvable.
    """
    error_class = discriminate(event)
    if error_class != ErrorClass.BLOCKING.value:
        return None

    # L1: parameter_drift — always allowed
    action = _try_parameter_drift(event, ctx)
    if action is not None:
        return action

    # L2: capability_extension — only in CAPABILITY mode
    if mode == RSIMode.CAPABILITY.value:
        action = _try_capability_extension(event, ctx, engine, tree)
        if action is not None:
            return action

    # Unresolvable
    return RSIAction(
        event=event,
        level=ActionLevel.L1.value,
        action_type="none",
        autonomous=True,
        resolution="error_unresolvable",
    )


def _try_parameter_drift(
    event: EvaluationEvent,
    ctx: Dict[str, Any],
) -> Optional[RSIAction]:
    """
    L1: Adjust threshold in context. Always autonomous.
    BUG-002: Uses MIN_THRESHOLD and MAX_THRESHOLD constants.
    """
    thresholds = ctx.get("_rsi_thresholds", {})
    current = thresholds.get(event.source, event.threshold)

    # BUG-002: Heuristic with bounds (prevent drift to 0 or infinity)
    if event.input_value > current:
        new_threshold = min(current + THRESHOLD_STEP, MAX_THRESHOLD)
    else:
        new_threshold = max(current - THRESHOLD_STEP, MIN_THRESHOLD)

    if abs(new_threshold - current) < 0.001:
        return None  # Already at boundary

    # Apply drift to context
    if "_rsi_thresholds" not in ctx:
        ctx["_rsi_thresholds"] = dict(thresholds)
    ctx["_rsi_thresholds"][event.source] = new_threshold

    return RSIAction(
        event=event,
        level=ActionLevel.L1.value,
        action_type="adjust_threshold",
        params={"old": current, "new": new_threshold},
        autonomous=True,
        resolution=f"threshold_adjusted:{current:.3f}→{new_threshold:.3f}",
    )


def _try_capability_extension(
    event: EvaluationEvent,
    ctx: Dict[str, Any],
    engine: Any = None,
    tree: Any = None,
) -> Optional[RSIAction]:
    """
    L2: Inject temporary predicate into the engine.

    Creates a wrapper predicate that adjusts the threshold dynamically.
    The wrapper is registered in the engine and can be used in subsequent
    evaluations.
    """
    if engine is None:
        return None

    original_name = event.source
    new_name = f"_rsi_adj_{original_name}"

    # Don't re-inject if already exists
    if new_name in engine.predicates:
        return RSIAction(
            event=event,
            level=ActionLevel.L2.value,
            action_type="inject_predicate_exists",
            params={"name": new_name},
            autonomous=True,
            resolution=f"predicate_already_injected:{new_name}",
        )

    # Get the original predicate function
    original_pred = engine.predicates.get(original_name)
    if original_pred is None:
        return None

    # Create a wrapper that applies RSI threshold adjustment
    def make_wrapper(orig_pred, pred_name):
        def rsi_adjusted_wrapper(ctx, threshold=0.70, **kw):
            # Apply RSI threshold override from context
            rsi_t = ctx.get("_rsi_thresholds", {})
            adjusted_threshold = rsi_t.get(pred_name, threshold)

            # Call original predicate with adjusted threshold
            try:
                result = orig_pred(ctx, threshold=adjusted_threshold, **kw)
                return result
            except TypeError:
                # Fallback: call without threshold if original doesn't accept it
                return orig_pred(ctx, **kw)

        rsi_adjusted_wrapper.__name__ = f"rsi_adj_{pred_name}"
        rsi_adjusted_wrapper.__doc__ = (
            f"RSI-adjusted wrapper for {pred_name}. "
            f"Automatically applies ctx['_rsi_thresholds'] override."
        )
        return rsi_adjusted_wrapper

    wrapper = make_wrapper(original_pred, original_name)

    # Register the wrapper in the engine (direct dict assignment)
    try:
        engine.predicates[new_name] = wrapper
    except (AttributeError, TypeError):
        return None

    # Validate: test the wrapper with a simple evaluation
    try:
        test_ctx = {"_rsi_thresholds": ctx.get("_rsi_thresholds", {})}
        test_node = {"predicate": new_name, "args": ["$ctx"]}
        test_result = engine.evaluate(test_node, test_ctx)
        if not hasattr(test_result, "truth"):
            raise ValueError("Wrapper validation failed: no truth attribute")
    except Exception:
        # Validation failed — don't inject
        try:
            del engine.predicates[new_name]
        except (KeyError, AttributeError):
            pass
        return RSIAction(
            event=event,
            level=ActionLevel.L2.value,
            action_type="inject_predicate_failed",
            params={"name": new_name, "error": "validation_failed"},
            autonomous=False,
            resolution="injection_validation_failed",
        )

    return RSIAction(
        event=event,
        level=ActionLevel.L2.value,
        action_type="inject_predicate",
        params={"name": new_name, "wraps": original_name},
        autonomous=True,
        resolution=f"predicate_injected:{new_name}(wraps {original_name})",
    )


# ── Observer Class ────────────────────────────────────────────────

class RSIObserver:
    """
    Wraps SocraticEngine.evaluate() to observe, classify, and resolve errors.

    Usage:
        engine = SocraticEngine()
        observer = RSIObserver(engine)

        # Inject thresholds into context
        ctx = {"task_id": "demo", "input_value": 0.75}
        result = observer.evaluate(tree, ctx)

        # Access collected events
        for event in observer.events:
            print(event.source, event.truth, event.error_class)
    """

    def __init__(
        self,
        engine: Any,
        mode: str = None,
        metrics: Optional[RSIMetrics] = None,
    ):
        self.engine = engine
        self.mode = mode or os.environ.get("RSI_MODE", RSIMode.CAPABILITY.value)
        self.metrics = metrics or RSIMetrics()
        self.thresholds = load_thresholds()
        self.events: List[EvaluationEvent] = []
        self.actions: List[RSIAction] = []
        self._has_scenario_memory = _HAS_SCENARIO_MEMORY

    def evaluate(
        self,
        tree: Any,
        ctx: Optional[Dict[str, Any]] = None,
        tree_id: str = "",
    ) -> Any:
        """
        Evaluate a tree through the socratic engine with observation.

        Wraps engine.evaluate() to:
          1. Inject thresholds into ctx
          2. Measure latency
          3. Capture evaluation result
          4. Build EvaluationEvent
          5. Bridge to rsi_metrics
          6. Discriminate and resolve errors
        """
        ctx = ctx or {}

        # Inject thresholds if not already present
        if "_rsi_thresholds" not in ctx:
            ctx["_rsi_thresholds"] = dict(self.thresholds)

        # Inject mode if not already present
        if "_rsi_mode" not in ctx:
            ctx["_rsi_mode"] = self.mode

        # Measure latency
        t_start = time.monotonic()

        # BUG-001: Try-evaluate with type validation fallback
        try:
            result = self.engine.evaluate(tree, ctx)
        except TypeError as e:
            # Predicate crashed on non-numeric input
            t_end = time.monotonic()
            latency_ms = (t_end - t_start) * 1000.0
            
            # Create a fallback result
            class FallbackResult:
                is_true = False
                truth = Truth.UNKNOWN
                certified = False
                metadata = {"error": "predicate_crash", "message": str(e)}
                source = "unknown"
            
            result = FallbackResult()
            
            # Override input_value to prevent re-crash in _build_event
            ctx["input_value"] = 0.5

        t_end = time.monotonic()
        latency_ms = (t_end - t_start) * 1000.0

        # Build event
        event = self._build_event(result, ctx, tree_id, latency_ms)
        # BUG-003: Circular buffer to prevent memory leak
        self.events.append(event)
        if len(self.events) > MAX_EVENTS:
            self.events = self.events[-MAX_EVENTS:]

        # Bridge to rsi_metrics
        self._bridge_to_metrics(event)

        # Discriminate and resolve
        if event.is_error:
            # Try scenario_memory match first
            fault_sig = f"{event.source}:error={event.error_class}"
            scenario_correction = match_scenario(fault_sig)

            if scenario_correction:
                # Found a matching scenario — apply its correction
                action = RSIAction(
                    event=event,
                    level=ActionLevel.L1.value,
                    action_type="scenario_match",
                    params={"correction": scenario_correction},
                    autonomous=True,
                    resolution=f"scenario_matched:{scenario_correction}",
                )
            else:
                # No match — use standard resolution
                action = resolve_error(
                    event, ctx,
                    mode=self.mode,
                    engine=self.engine,
                    tree=tree,
                )

            if action is not None:
                self.actions.append(action)

                # If parameter_drift modified ctx, re-evaluate
                if action.action_type == "adjust_threshold" and action.autonomous:
                    # BUG-001: Wrap re-evaluation in try-except too
                    try:
                        result = self.engine.evaluate(tree, ctx)
                    except TypeError:
                        # Re-evaluation also crashed — keep original result
                        pass

                # Record the scenario for future matching
                record_scenario(event, action)

        return result

    def _build_event(
        self,
        result: Any,
        ctx: Dict[str, Any],
        tree_id: str,
        latency_ms: float,
    ) -> EvaluationEvent:
        """Build an EvaluationEvent from an engine result."""
        # BUG-001: Extract and validate input_value type
        input_value = ctx.get("input_value", 0.5)
        
        # Validate type BEFORE comparison
        if not isinstance(input_value, VALID_INPUT_TYPES):
            # Non-numeric input: treat as error (cannot compare)
            source = getattr(result, "source", "unknown") if result else "unknown"
            thresholds = ctx.get("_rsi_thresholds", self.thresholds)
            optimal = thresholds.get(source, 0.70)
            
            event = EvaluationEvent(
                tree_id=tree_id,
                timestamp=datetime.now(timezone.utc).isoformat(),
                latency_ms=latency_ms,
                source=source,
                truth="UNKNOWN",
                certified=False,
                metadata={"error": "non_numeric_input", "input_type": type(input_value).__name__},
                task_id=ctx.get("task_id", ""),
                threshold=optimal,
                input_value=0.5,  # fallback
                actual=False,
                expected=False,
                is_error=True,  # always error for non-numeric
                error_class=ErrorClass.BLOCKING.value,
            )
            return event
        
        # Normal path: compute expected from threshold
        thresholds = ctx.get("_rsi_thresholds", self.thresholds)
        source = getattr(result, "source", "unknown")
        optimal = thresholds.get(source, 0.70)
        expected = get_expected(input_value, optimal)

        actual = result.is_true if hasattr(result, "is_true") else False
        truth_str = result.truth.value if hasattr(result, "truth") else "UNKNOWN"

        is_error = expected != actual

        event = EvaluationEvent(
            tree_id=tree_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            latency_ms=latency_ms,
            source=source,
            truth=truth_str,
            certified=getattr(result, "certified", False),
            metadata=getattr(result, "metadata", {}),
            task_id=ctx.get("task_id", ""),
            threshold=optimal,
            input_value=input_value,
            actual=actual,
            expected=expected,
            is_error=is_error,
            error_class="NONE",
        )

        # Classify error
        if is_error:
            event.error_class = discriminate(event)

        return event

    def _bridge_to_metrics(self, event: EvaluationEvent) -> None:
        """Feed EvaluationEvent to rsi_metrics via track_classification()."""
        try:
            self.metrics.track_classification(
                predicate_name=event.source,
                threshold=event.threshold,
                input_value=event.input_value,
                expected=event.expected,
                actual=event.actual,
                latency_ms=event.latency_ms,
            )
        except Exception:
            # Metrics bridge is best-effort, never block evaluation
            pass

    def get_events_by_source(self, source: str) -> List[EvaluationEvent]:
        """Filter events by predicate/operator source."""
        return [e for e in self.events if e.source == source]

    def get_error_summary(self) -> Dict[str, int]:
        """Summary of errors by class."""
        summary = {"NONE": 0, "BLOCKING": 0, "STRUCTURAL": 0}
        for e in self.events:
            summary[e.error_class] = summary.get(e.error_class, 0) + 1
        return summary

    def get_stats(self) -> Dict[str, Any]:
        """Overall observer statistics."""
        total = len(self.events)
        errors = sum(1 for e in self.events if e.is_error)
        avg_latency = (
            sum(e.latency_ms for e in self.events) / total
            if total > 0 else 0.0
        )
        return {
            "total_evaluations": total,
            "total_errors": errors,
            "error_rate": errors / total if total > 0 else 0.0,
            "avg_latency_ms": round(avg_latency, 3),
            "actions_taken": len(self.actions),
            "mode": self.mode,
        }

    def dump_events(self, path: Optional[str] = None) -> str:
        """
        Dump events and actions to JSON for observation dashboard.
        Returns the path written.
        """
        if path is None:
            path = str(
                Path(__file__).parent.parent.parent
                / "state" / "monitoring" / "rsi_events.json"
            )

        data = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "stats": self.get_stats(),
            "events": [
                {
                    "tree_id": e.tree_id,
                    "timestamp": e.timestamp,
                    "latency_ms": round(e.latency_ms, 3),
                    "source": e.source,
                    "truth": e.truth,
                    "certified": e.certified,
                    "task_id": e.task_id,
                    "threshold": e.threshold,
                    "input_value": e.input_value,
                    "actual": e.actual,
                    "expected": e.expected,
                    "is_error": e.is_error,
                    "error_class": e.error_class,
                }
                for e in self.events
            ],
            "actions": [
                {
                    "level": a.level,
                    "action_type": a.action_type,
                    "params": a.params,
                    "autonomous": a.autonomous,
                    "resolution": a.resolution,
                    "source": a.event.source,
                    "timestamp": a.event.timestamp,
                }
                for a in self.actions
            ],
        }

        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

        return path

    def analyze_patterns(self) -> List[Dict[str, Any]]:
        """
        L3: Analyze error events to detect patterns.
        Returns list of patterns sorted by frequency.
        """
        return analyze_error_patterns(self.events)

    def generate_predicates(self, min_occurrences: int = 3) -> List[RSIAction]:
        """
        L3: Generate new predicates from frequent error patterns.
        Only generates if a pattern has at least min_occurrences errors.
        Returns list of actions (proposals for human approval).
        """
        actions = generate_predicate_if_warranted(
            self.events, self.engine, min_occurrences
        )
        self.actions.extend(actions)
        return actions

    def evolve_predicates(
        self,
        min_errors: int = 10,
        generations: int = 5,
    ) -> List[RSIAction]:
        """
        L4: Evolve predicates that have enough error history.
        Only evolves if a predicate has at least min_errors errors.
        Returns list of actions (proposals for human approval).
        """
        actions = evolve_if_warranted(
            self.events, min_errors, generations
        )
        self.actions.extend(actions)
        return actions
