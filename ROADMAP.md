# Roadmap — vsf-rsi

## ✅ v0.1.0 — Core (2026-08-30)
- [x] Observer wrapper for socratic-engine
- [x] Bridge to rsi_metrics (track_classification)
- [x] Error discrimination (BLOCKING / STRUCTURAL / NONE)
- [x] L1 parameter drift (threshold adjustment, autonomous)
- [x] L2 capability extension (inject predicate wrappers, autonomous)
- [x] L3 predicate generation (pattern-based, human approval)
- [x] L4 genetic evolution (population-based, human approval)
- [x] Scenario memory integration (match/record)
- [x] dump_events() for observation
- [x] 50 tests passing, 2 skipped (scenario_memory)
- [x] GitHub Actions CI (pytest 3.10-3.12 + coverage ≥80%)
- [x] GitHub Actions Release (tag↔pyproject↔__init__ sync)
- [x] All hardcoded paths removed
- [x] All internal imports fixed (from vsf_rsi.*)

## ✅ v0.1.1 — Bug Fixes (2026-08-30)
- [x] BUG-001: Type validation for non-numeric inputs (HIGH)
- [x] BUG-002: Threshold drift bounds with MIN/MAX constants (MEDIUM)
- [x] BUG-003: Memory leak prevention with circular buffer (LOW)

## ✅ v0.1.2 — More Bug Fixes (2026-08-30)
- [x] BUG-004: is_error computed property via __post_init__ (MEDIUM)
- [x] BUG-005: load_thresholds path flexibility with PACKAGE_DIR (LOW)

## ✅ v0.1.3 — Logging (2026-08-30)
- [x] DEBT-001: Structured logging configuration with logging.getLogger()

## ✅ v0.1.4 — Error Recovery (2026-08-30)
- [x] DEBT-002: Error recovery throughout evaluate() pipeline

## ✅ v0.1.5 — Convergence Check (2026-08-30)
- [x] DEBT-004: Genetic algorithm convergence check with early stopping

## ✅ v0.1.6 — Pattern Decay (2026-08-30)
- [x] DEBT-005: Pattern decay for stale patterns (10% per day)

## ✅ v0.1.7 — Hardened (2026-08-30)
- [x] DEBT-003: Duplicate latency tracking removed
- [x] DEBT-006: Generated code validation with ast.parse()
- [x] DEBT-007: Version conflict detection in tree registry

## ✅ v0.1.8 — Release (2026-08-31)
- [x] Installation instructions in README
- [x] PyPI badge fixed
- [x] PyPI publishing configured
- [x] All v0.1.x bug fixes and improvements

## ✅ v0.1.9 — Integration (2026-08-31)
- [x] 1 threshold adjustment applied
- [x] End-to-end test: generate → evaluate → evolve → measurable improvement (50% → 0%)
- [x] Integration with state-canon-mcp (rsi_bridge.py)
- [x] Extended capabilities in README

## ✅ v0.2.0 — Validation
- [x] 50 real evaluations processed (gate: Fase 1)
- [x] 1 threshold adjustment applied
- [x] 10 runs processed, 1 improvement via scenario_memory (gate: Fase 2)
- [x] End-to-end test: generate → evaluate → evolve → measurable improvement (G3)
- [x] Integration with state-canon-mcp
- [x] All 16 rsi_*.py mapped to package components (G4)
- [x] Coverage ≥90%

## ✅ v0.2.2 — Integration Bridge + Hardening
- [x] adapt(): update pattern quality after execution
- [x] learn(): detect repeated patterns (≥N occurrences)
- [x] rsi_socratic_bridge.py: register predicates + trees in socratic-engine
- [x] Bash failure capture added to tool-integration plugin
- [x] register_rsi_tree_from_file() for generated tree loading
- [x] rsi_pipeline.py: full evolution cycle orchestrator
- [x] enforce_limits=True in RSIObserver for auto-generated trees
- [x] Fixed broken imports in rsi_demo.py (scripts.vsl.classifier → vsf_rsi)
- [x] Removed ~80 lines of test scaffolding (no longer needed)

## ✅ v0.2.3 — Context-Aware Predicate Generation
- [x] _create_context_aware_predicate: uses avg_threshold/avg_input from pattern data
- [x] error_class-based strategy selection (false_positive, false_negative, unknown)
- [x] Safety margin calculation (10% around threshold)
- [x] Fallback to static templates when pattern data unavailable
- [x] 10 tests in tests/test_rsi_predicate_semantic.py

## ✅ v0.2.4 — Behavioral Validation
- [x] validate_predicate_behavior(): runs predicate against test cases
- [x] Rejects predicates with accuracy below min_accuracy threshold
- [x] Normalizes PredicateResult → bool via is_true
- [x] Failure reporting: input, expected, got, index
- [x] 13 tests in tests/test_rsi_predicate_behavioral.py

## ✅ v0.2.5 — Adversarial Benchmark Suite
- [x] rsi_benchmark.py: load scenarios, run benchmarks, save/load reports, improvement curve
- [x] rsi_adversarial.py: 4 scenario generators (prisoner, parabola, xor, noise)
- [x] Baseline predicates for comparison (always_true, random, snr_threshold)
- [x] run_adversarial_benchmark() suite runner
- [x] 21 benchmark tests + 21 adversarial tests = 42 new tests

## ✅ v0.2.6 — Adversarial Challenge: First Evidence
- [x] rsi_adversarial_harness.py: genome→predicate bridge, GA with adversarial fitness
- [x] 5-fold cross-validation on all 4 scenario types
- [x] Results: GA improves over random by +52.5% mean (prisoner 100%, parabola 98.8%, xor 95%, noise 100%)
- [x] Hard mode: GA maintains 100% even at SNR~0.03
- [x] First measurable evidence that RSI produces genuine improvement

## ✅ v0.2.7 — Genoma-V3: Enriched Representation
- [x] rsi_genome_v3.py: variadic ops, feature chaining, sign normalization, parity
- [x] Checkerboard XOR: 100% train, 100% test (SOLVED autonomously)
- [x] 5D XOR: 80% test (improved from 30%), limit: high-arity parity
- [x] Unit Circle: 100% (maintained)
- [x] TabuMemory: avoids repeated failed feature combinations
- [x] Key insight: representation richness > search budget

## ✅ v0.2.8 — Security Fix: RCE Elimination (2026-09-01)
- [x] CRITICAL: eliminated exec()-based code injection in rsi_pipeline.py
- [x] CRITICAL: eliminated exec()-based code injection in rsi_socratic_bridge.py
- [x] Predicates now use structured condition trees (JSON) evaluated by socratic-engine
- [x] Input sanitization: _sanitize_value(), _sanitize_fault_signature()
- [x] enforce_limits=True added to all evaluation paths
- [x] Persistence format v2: trees instead of code strings
- [x] New built-in predicates: ctx_equals, ctx_contains
- [x] 34 security regression tests (including Claude's PoC)
- [x] 819/819 tests pass

## ✅ v0.2.9 — L3 Autonomous Cycle: "Estratega Autónomo" (2026-09-01)
- [x] rsi_fault_detector.py: detects complex faults (≥3 BLOCKING in 10 evals)
- [x] rsi_shadow_mode.py: validates strategies with 10 real evals before activation
- [x] rsi_rollback.py: monitors activated strategies, auto-reverts if degrades
- [x] rsi_autonomous_l3.py: orchestrator — detect → generate → shadow → activate
- [x] Safety: AST validation → shadow mode → ≥10% threshold → auto-rollback
- [x] Integrated with RSIObserver (autonomous_l3=True by default)
- [x] 24 new tests for autonomous cycle (843 total)
- [x] Bridge to L4: shadow mode = fitness eval, rollback = natural selection

## ✅ v0.2.10 — L3 Fixes & Comprehensive Cleanup (2026-09-02)
- [x] Fix `_rsi_trees` evaluation: trees registered as callable predicates via `engine.register()` closures
- [x] Global `_engine` singleton to avoid re-loading predicates on every bridge call
- [x] Fix `_evaluate_with_predicate` to check `engine.predicates` (not `_rsi_trees`)
- [x] Dead code removal: `Union` import, `inject_context` parameter
- [x] `RSIObserver.evaluate` complexity D→C via extracted helper methods
- [x] `RSIGenomeV2._apply_op` complexity D→C via dictionary dispatch
- [x] `MAX_ACTIONS=500` circular buffer for action tracking
- [x] DEBT-001: genome-to-tree with comparison predicates (gt/lt/eq), contradiction detection
- [x] DEBT-002: debt_verification_results.json updated passed=true
- [x] 855 tests total, all passing

## ✅ v0.2.11 — L3 Activation Loop Closure (2026-09-02)
- [x] `_feed_rollback_evaluations()` added to RSIObserver
- [x] RollbackManager.record_evaluation() now called after every evaluation
- [x] Matching: source/fault_id/strategy_id triple check
- [x] 3 new tests in TestRollbackLoop class
- [x] 858 tests total, all passing

## ✅ Phase P2 — Dashboard (2026-09-01)
- [x] Dashboard HTML with metrics visualization
- [x] Summary: total evaluations, accuracy, active sources
- [x] Per-source: evaluations, accuracy, thresholds, latency
- [x] Auto-refresh every 30s
- [x] Dark theme (GitHub-style)

## 🎯 v0.3.0 — Production
- [ ] Dashboard for observation (visual metrics + pattern timeline)
- [ ] Cross-validation (k-fold on error classification)
- [ ] Overfitting detection (scenario_memory + pattern decay)
- [ ] 5 components generated, 3 approved, 2 measurable improvements (gate: Fase 3)
- [ ] GA produces trees with fitness > 0.7 on real benchmark (gate: Fase 4)
- [ ] PyPI publication with install extras (`pip install vsf-rsi[full]`)

## 🔮 v1.0.0 — Maturity
- [ ] Co-evolution (predator-prey)
- [ ] Speciation (different tree types)
- [ ] Paraconsistent logic
- [ ] Frame semantics
- [ ] Full VSM kernel integration
