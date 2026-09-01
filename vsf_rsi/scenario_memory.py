#!/usr/bin/env python3
"""scenario_memory.py — procedural / scenario learning (second-order cybernetics).

The system observes its own decisions and outcomes, stores them as reusable
scenarios, and matches novel faults to prior correction paths. This is the
LEARNING SUBSTRATE of the autonomy loop: it supplies autonomy-cert C6
(scenario_learns). Closes the loop — the observer is part of the system.

Design note: the exploratory proposals (docs/scenario_memory_*.vsm) sketched this
in TypeScript. Implemented here in Python under child/scripts/vsl/ so it is
auditable by the same gate that certifies the rest of the child (mapped to
gate-suite). No behaviour change to the proposals' intent.
"""
import hashlib
import json
import os
import pathlib
import re

# Default store lives under learning_records/scenarios. Overridable via
# VSI_RSI_STORE environment variable (tests / drills pass a temp dir).
_DEFAULT_STORE = pathlib.Path(__file__).resolve().parents[2] / "learning_records" / "scenarios"


def _get_store() -> pathlib.Path:
    """Get the scenario store path (respects VSI_RSI_STORE env var)."""
    return pathlib.Path(os.environ.get("VSI_RSI_STORE", _DEFAULT_STORE))


# For backward compatibility
STORE = _get_store()


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def record(decision: str, outcome: str, correction_path: str,
           fault_signature: str | None = None) -> str:
    """Persist a scenario; returns its stable id. Never silently stores garbage."""
    if not decision or not outcome or not correction_path:
        raise ValueError("scenario requires decision + outcome + correction_path")
    sig = fault_signature or _norm(decision)
    sid = hashlib.sha256((sig + "|" + outcome).encode()).hexdigest()[:12]
    rec = {
        "id": sid,
        "decision": decision,
        "outcome": outcome,
        "correction_path": correction_path,
        "fault_signature": sig,
    }
    store = _get_store()
    store.mkdir(parents=True, exist_ok=True)
    (store / f"{sid}.json").write_text(json.dumps(rec, indent=2))
    return sid


def match(fault_signature: str, threshold: float = 0.0):
    """Retrieve the closest prior scenario for a novel fault.

    Returns (id, correction_path) or None. None == UNKNOWN: a novel fault is
    NEVER hallucinated into a match (negative-control: unseen -> UNKNOWN).
    Corrupted/forged records are ignored, not trusted.
    """
    q = _norm(fault_signature)
    best, best_score = None, -1.0
    store = _get_store()
    for p in store.glob("*.json"):
        try:
            rec = json.loads(p.read_text())
        except (json.JSONDecodeError, OSError):
            continue  # corrupted/forged record ignored
        if not isinstance(rec, dict) or "correction_path" not in rec:
            continue
        score = _similarity(q, _norm(rec.get("fault_signature", "")))
        if score > best_score:
            best, best_score = rec, score
    if best is None or best_score <= threshold:
        return None  # UNKNOWN — no fabricated match
    return best["id"], best["correction_path"]




def adapt(scenario_id: str, quality: float, learned_from_failure: bool = False):
    """Update pattern quality based on outcome. Quality ∈ [0.0, 1.0].
    
    - quality: how useful was this pattern (0.0 = useless, 1.0 = perfect)
    - learned_from_failure: if True, pattern was learned from a failure
    """
    if not 0.0 <= quality <= 1.0:
        raise ValueError(f"quality must be in [0.0, 1.0], got {quality}")
    
    store = _get_store()
    target = store / f"{scenario_id}.json"
    if not target.exists():
        raise FileNotFoundError(f"scenario {scenario_id} not found")
    
    rec = json.loads(target.read_text())
    rec["quality"] = quality
    rec["learned_from_failure"] = learned_from_failure
    rec["adapted_at"] = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
    target.write_text(json.dumps(rec, indent=2))
    return rec


def learn(min_occurrences: int = 3):
    """Detect patterns that repeated ≥ min_occurrences times.
    
    Returns list of {fault_signature, count, avg_quality, correction_path}
    for patterns that suggest systematic issues.
    """
    store = _get_store()
    patterns = {}
    
    for p in store.glob("*.json"):
        try:
            rec = json.loads(p.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(rec, dict):
            continue
        
        sig = rec.get("fault_signature", "unknown")
        if sig not in patterns:
            patterns[sig] = {
                "fault_signature": sig,
                "records": [],
                "correction_path": rec.get("correction_path", ""),
            }
        patterns[sig]["records"].append(rec)
    
    # Find patterns that repeat enough
    results = []
    for sig, data in patterns.items():
        count = len(data["records"])
        if count >= min_occurrences:
            qualities = [r.get("quality", 0.5) for r in data["records"]]
            avg_quality = sum(qualities) / len(qualities) if qualities else 0.5
            results.append({
                "fault_signature": sig,
                "count": count,
                "avg_quality": avg_quality,
                "correction_path": data["correction_path"],
            })
    
    return sorted(results, key=lambda x: -x["count"])

def validate_store():
    """Return ids of corrupted/forged records (missing correction_path / unparseable)."""
    bad = []
    store = _get_store()
    for p in store.glob("*.json"):
        try:
            rec = json.loads(p.read_text())
        except (json.JSONDecodeError, OSError):
            bad.append(p.stem)
            continue
        if not isinstance(rec, dict) or "correction_path" not in rec:
            bad.append(p.stem)
    return bad


def _similarity(a: str, b: str) -> float:
    sa, sb = set(a.split()), set(b.split())
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)
