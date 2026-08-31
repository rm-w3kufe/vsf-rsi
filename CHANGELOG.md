# Changelog — vsf-rsi

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
