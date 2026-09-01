# Changelog — vsf-rsi

## [0.2.7] — 2026-09-01

### Added
- **Genome V3** (`rsi_genome_v3.py`) — Genetic Algorithm with enriched genome representation
  - Feature construction graph with variadic operations (mul, add with N inputs)
  - Feature chaining: d1 can reference d0 (sequential composition)
  - Sign normalization: `op_sign` collapses continuous to {-1, 0, +1}
  - Parity detection: `op_parity` counts negative inputs mod 2
  - XOR-2: `op_xor2` compares signs of two inputs
  - Count negatives: `op_count_neg` for sign-based features
  - TabuMemory: remembers failed feature combinations to avoid repetition
- **Stress test suite** (`rsi_stress_test.py`) — 32 tests across 7 dimensions
- Checkerboard XOR solved at 100% (GA autonomously discovered sign + parity)
- 5D XOR improved to 80% test accuracy

## [0.2.6] — 2026-09-01

### Added
- **rsi_adversarial_harness.py** — genome→predicate bridge, GA with adversarial fitness
- **rsi_stress_test.py** — breaking point analysis across 7 dimensions
- 5-fold cross-validation on all 4 scenario types
- Results: GA improves over random by +52.5% mean

## [0.2.5] — 2026-09-01

### Added
- **rsi_benchmark.py** — Benchmark framework: load scenarios, run benchmarks, save/load reports, compute improvement curves
- **rsi_adversarial.py** — 4 adversarial scenario generators:
  - Prisoner's Dilemma (cooperation detection under noise)
  - La Parábola Silenciosa (non-linear logic, hidden order in chaos)
  - XOR de Alta Dimensión (5-variable non-separable interactions)
  - Señal en Ruido Blanco (weak signal detection, SNR < 1)
- **validate_predicate_behavior()** — run predicates against {input, expected} test cases, reject below min_accuracy
- **Context-aware predicate generation** — `_create_context_aware_predicate()` uses avg_threshold, avg_input, error_class
- **CI fix** — install socratic-engine before running tests (RSI-CI-INSTALL-FIX)

### Changed
- **scenario_to_test_case()** — now passes through nested `context` field for rich predicates
- **rsi_observer.py** — feature-detect `enforce_limits` via `inspect.signature` (backward-compatible with old socratic-engine)

## [0.2.4] — 2026-09-01

### Added
- **validate_predicate_behavior()** — runs predicates against test cases, rejects below min_accuracy
- 13 behavioral validation tests

## [0.2.3] — 2026-09-01

### Added
- **_create_context_aware_predicate()** — uses avg_threshold/avg_input from pattern data
- error_class-based strategy selection (false_positive, false_negative, unknown)
- Safety margin calculation (10% around threshold)
- 10 context-aware generation tests

## [0.2.2] — 2026-09-01

### Fixed
- **rsi_observer.py** — feature-detect `enforce_limits` via `inspect.signature` for backward compatibility

## [0.2.1] — 2026-08-31

### Fixed
- CI: install socratic-engine from cloned repo

## [0.2.0] — 2026-08-31

### Added
- **Scenario Memory Integration** (`test_scenario_memory_integration.py`)
  - Full RSI loop: 10 evaluation runs, scenario_memory records failures, matches corrections, improves results
  - Demonstrates procedural learning: failures → scenario records → correction matching → threshold adjustment
- **Comprehensive test coverage** (708 tests, 99% coverage)
  - `test_debt002_error_recovery.py` — 22 tests proving error recovery works
  - `test_scenario_memory_deep.py` — scenario_memory 100% coverage
  - `test_rsi_scenario_bridge_deep.py` — bridge import fallback coverage
  - `test_rsi_pattern_detector_cli.py` — CLI main() coverage
  - `test_rsi_tree_generator_cli.py` — CLI main() coverage
  - `test_rsi_feedback_loop_cli.py` — CLI main() coverage
  - `test_rsi_forest_generator_cli.py` — CLI main() coverage
  - `test_rsi_observer_final.py` — import fallbacks + exception handlers

### Fixed
- DEBT-002: Error recovery verified with 22 dedicated tests (evaluate() never crashes)
- DEBT-003 latencies bugs: Fixed in `rsi_metrics.py`, `rsi_gap_detector.py`, `rsi_pattern_detector.py`
- Bare import: `rsi_gap_detector.py` fixed `from rsi_metrics import RSIMetrics` → `from vsf_rsi.rsi_metrics import RSIMetrics`
- `rsi_metrics.py` architectural fix: instance-level paths via `_metrics_file` property

### Changed
- `scenario_memory` exported from `vsf_rsi` package (public API)
- ROADMAP v0.2.0 items all checked off
- README expanded with all 16 module capabilities, CLI usage, demo, and testing sections
- Coverage: 31% → 99%

## [0.1.9] — 2026-08-31

### Added
- `rsi_bridge.py` — integration with state-canon-mcp
  - `get_rsi_rules()`: query rules constraining RSI behavior
  - `query_canon()`: query canonical state
  - `get_rsi_focus()`: get current RSI focus state
  - `feed_metrics_to_canon()`: feed metrics back to state canon
- Extended capabilities documentation in README
- Installation instructions (pip, source)

### Changed
- Version bumped to 0.1.9

## [0.1.8] — 2026-08-31

### Added
- Installation instructions in README (pip install, from source)
- PyPI badge in README

### Changed
- Version bumped to 0.1.8

## [0.1.7] — 2026-08-30

### Added
- **DEBT-003**: Removed duplicate latency tracking
- Latency now only stored at threshold level (not predicate level)
- `get_latency()` computes predicate-level from threshold-level data
- Reduced storage overhead

- **DEBT-006**: Added validation of generated code
- `generate_predicate()` now validates Python syntax before writing
- Uses `ast.parse()` to check for syntax errors
- Raises `ValueError` if generated code is invalid

- **DEBT-007**: Added version conflict detection
- `register_tree()` now checks for same predicate with different path
- Prevents multiple active trees for the same predicate
- Returns conflict info if detected

## [0.1.6] — 2026-08-30

### Added
- **DEBT-005**: Pattern decay for stale patterns
- Added `PATTERN_DECAY_RATE` (0.1/day) and `PATTERN_MIN_STRENGTH` (0.1) constants
- Patterns now have `last_seen` and `strength` fields
- Exponential decay applied when saving patterns
- Patterns with strength below threshold are automatically removed

### Changed
- Patterns now expire over time (10% decay per day)
- Old patterns that haven't been seen recently are removed
- Prevents stale patterns from influencing decisions

## [0.1.5] — 2026-08-30

### Added
- **DEBT-004**: Convergence check for genetic algorithm
- Added `CONVERGENCE_THRESHOLD` (0.001) and `CONVERGENCE_PATIENCE` (3) constants
- Early stopping when fitness improvement is below threshold for N generations
- Updated `evolve_forest()` in both v1 and v2 genetic algorithms
- Added `converged` and `max_generations` to evolution results

### Changed
- Evolution now stops early when converged (saves compute)
- Results include whether evolution converged or ran all generations

## [0.1.4] — 2026-08-30

### Added
- **DEBT-002**: Error recovery throughout evaluate() pipeline
- Catch-all exception handler for engine.evaluate()
- Fallback event creation when _build_event() fails
- Error recovery for _bridge_to_metrics()
- Error recovery for error discrimination/resolution
- Error recovery for scenario recording

### Changed
- System now continues with degraded functionality on failures
- All critical paths wrapped in try-except blocks
- Errors logged but don't crash the observer

## [0.1.3] — 2026-08-30

### Added
- **DEBT-001**: Added logging configuration with `logging.getLogger("vsf_rsi.observer")`
- Logger initialized in `RSIObserver.__init__`
- Info logging for: initialization, error detection, scenario matches
- Debug logging for: action taken
- Warning logging for: predicate crashes, re-evaluation failures

## [0.1.2] — 2026-08-30

### Fixed
- **BUG-004 (MEDIUM)**: `is_error` is now computed from `expected != actual`
- **BUG-005 (LOW)**: `load_thresholds()` accepts optional `thresholds_dir` parameter

### Changed
- `EvaluationEvent.is_error` uses `__post_init__` (no longer settable)
- Added `PACKAGE_DIR` and `STATE_DIR` constants
- Tests updated to use `expected/actual` instead of `is_error`

## [0.1.1] — 2026-08-30

### Fixed
- **BUG-001 (HIGH)**: Type validation — non-numeric inputs no longer crash observer
- **BUG-002 (MEDIUM)**: Threshold drift bounds — added MIN/MAX/STEP constants
- **BUG-003 (LOW)**: Memory leak — circular buffer limits events to 1000

### Added
- `MIN_THRESHOLD`, `MAX_THRESHOLD`, `THRESHOLD_STEP` constants
- `MAX_EVENTS` constant for circular buffer
- `VALID_INPUT_TYPES` tuple for type validation
- `Truth` import from socratic_engine (with fallback)
- Try-except around `engine.evaluate()` calls
- Try-except around re-evaluation after threshold adjustment

## [0.1.0] — 2026-08-30

### Added
- **RSI Observer** — wraps `SocraticEngine.evaluate()` to capture every evaluation event
- **Bridge** — feeds events to `rsi_metrics` for tracking
- **Discriminator** — classifies errors as BLOCKING or STRUCTURAL
- **Resolver** — applies the appropriate improvement level (L1-L4)
- **L1 Parameter Drift** — adjusts thresholds automatically (autonomous)
- **L2 Capability Extension** — creates wrapper predicates (autonomous)
- **L3 Predicate Generation** — generates new predicates from error patterns (human approval)
- **L4 Genetic Evolution** — evolves populations of predicates (human approval)
- **Scenario Memory** — records and matches past corrections
- **dump_events()** — JSON output for observation
- **50 tests** passing (2 skipped when scenario_memory not installed)
- **GitHub Actions CI** — pytest 3.10-3.12 with coverage ≥80%
- **GitHub Actions Release** — tag↔pyproject↔__init__ sync, PyPI publish

### Fixed
- Removed all hardcoded `/home/rmw3/*` paths
- Fixed all internal imports (`from vsf_rsi.rsi_*`)
- MANIFEST_FILE and EVOLUTION_DIR use package-relative paths
- scenario_memory tests skip gracefully when not installed

### Security
- L1/L2 are autonomous (reversible)
- L3/L4 require human approval
- A0/A0.1 purpose inalienable
- A5 autonomy ceiling enforced
- R17 destructive actions require explicit consent
