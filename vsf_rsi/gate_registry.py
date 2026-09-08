"""
gate_registry.py — Unified gate registry for dynamic gate integration.

This module unifies all gate sources:
1. Static gate trees (.opencode/plugins/support/trees/*.tree.vsm)
2. Gap-definition gates (.opencode/plugins/operational/gap-definitions/*.gap.json)
3. RSI-generated gates (from rsi_pipeline.py)

The registry provides a single lookup API for the gap-resolver and other consumers.
"""

import os
import json
import glob
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from enum import Enum


class GateType(Enum):
    """Types of gates in the system."""
    STATIC = "static"           # Pre-defined gate trees
    GAP = "gap"                 # Gap-definition gates
    RSI = "rsi"                 # RSI-generated gates
    HYBRID = "hybrid"           # Combination of multiple sources


class GateSeverity(Enum):
    """Gate severity levels."""
    CRITICAL = "CRITICAL"       # Block action, require human approval
    HIGH = "HIGH"               # Block action, allow override
    MEDIUM = "MEDIUM"           # Report, allow action
    LOW = "LOW"                 # Report only
    INFO = "INFO"               # Log only


@dataclass
class GateDefinition:
    """Unified gate definition."""
    id: str
    name: str
    description: str
    gate_type: GateType
    source: str                  # File path or generator name
    trigger: Dict[str, Any]      # When to evaluate
    evaluation: Dict[str, Any]   # How to evaluate (tree or predicate)
    actions: List[Dict[str, Any]]  # What to do on match
    severity: GateSeverity = GateSeverity.MEDIUM
    enabled: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GateResult:
    """Result of gate evaluation."""
    gate_id: str
    decision: str                # PASS, BLOCK, UNKNOWN
    evidence: Dict[str, Any]
    actions_executed: List[str]
    timestamp: float


class GateRegistry:
    """Unified registry for all gate sources."""
    
    def __init__(self, repo_root: Optional[str] = None):
        self.repo_root = repo_root or os.environ.get("VOS_REPO_ROOT", "/home/rmw3/vOSlab")
        # Use VSF root for plugin paths (actual location)
        self.vsf_root = os.environ.get("VOSF_ROOT", "/home/rmw3/vsf")
        # Use agent-specific state directory for RSI predicates
        self.agent_state_dir = os.environ.get("VOS_AGENT_STATE_DIR", 
            os.path.expanduser("~/.vos/agents/rmw3-vOSlab"))
        self.gates: Dict[str, GateDefinition] = {}
        self._load_all_gates()
    
    def _load_all_gates(self):
        """Load gates from all sources."""
        self._load_static_gates()
        self._load_gap_definition_gates()
        self._load_rsi_gates()
    
    def _load_static_gates(self):
        """Load pre-defined gate trees from .opencode/plugins/support/trees/."""
        trees_dir = os.path.join(self.vsf_root, ".opencode", "plugins", "support", "trees")
        if not os.path.exists(trees_dir):
            return
        
        for tree_file in glob.glob(os.path.join(trees_dir, "*.tree.vsm")):
            try:
                gate_id = os.path.basename(tree_file).replace(".tree.vsm", "")
                gate = GateDefinition(
                    id=f"static_{gate_id}",
                    name=f"Static Gate: {gate_id}",
                    description=f"Pre-defined gate tree: {gate_id}",
                    gate_type=GateType.STATIC,
                    source=tree_file,
                    trigger={"type": "always"},
                    evaluation={"type": "socratic", "tree": tree_file},
                    actions=[{"type": "report", "severity": "MEDIUM"}],
                    severity=GateSeverity.MEDIUM
                )
                self.gates[gate.id] = gate
            except Exception as e:
                print(f"Warning: Failed to load static gate {tree_file}: {e}")
    
    def _load_gap_definition_gates(self):
        """Load gap-definition gates from .opencode/plugins/operational/gap-definitions/."""
        gap_dir = os.path.join(self.vsf_root, ".opencode", "plugins", "operational", "gap-definitions")
        if not os.path.exists(gap_dir):
            return
        
        for gap_file in glob.glob(os.path.join(gap_dir, "*.gap.json")):
            try:
                with open(gap_file, "r") as f:
                    gap_def = json.load(f)
                
                # Determine severity from actions
                severity = GateSeverity.MEDIUM
                for action in gap_def.get("actions", []):
                    if action.get("severity") == "CRITICAL":
                        severity = GateSeverity.CRITICAL
                        break
                    elif action.get("severity") == "HIGH":
                        severity = GateSeverity.HIGH
                    elif action.get("severity") == "MEDIUM":
                        severity = GateSeverity.MEDIUM
                    elif action.get("severity") == "LOW":
                        severity = GateSeverity.LOW
                
                gate = GateDefinition(
                    id=gap_def.get("id", os.path.basename(gap_file).replace(".gap.json", "")),
                    name=gap_def.get("name", f"Gap Gate: {gap_file}"),
                    description=gap_def.get("description", ""),
                    gate_type=GateType.GAP,
                    source=gap_file,
                    trigger=gap_def.get("trigger", {}),
                    evaluation=gap_def.get("evaluation", {}),
                    actions=gap_def.get("actions", []),
                    severity=severity,
                    metadata=gap_def.get("metadata", {})
                )
                self.gates[gate.id] = gate
            except Exception as e:
                print(f"Warning: Failed to load gap definition {gap_file}: {e}")
    
    def _load_rsi_gates(self):
        """Load RSI-generated gates from agent-specific state directory."""
        predicates_dir = os.path.join(self.agent_state_dir, "vsf-rsi", "predicates")
        if not os.path.exists(predicates_dir):
            return
        
        for pred_file in glob.glob(os.path.join(predicates_dir, "*.json")):
            try:
                with open(pred_file, "r") as f:
                    pred_def = json.load(f)
                
                # Only load RSI-generated predicates
                if pred_def.get("source") != "rsi_pipeline":
                    continue
                
                gate = GateDefinition(
                    id=f"rsi_{pred_def.get('predicate_name', os.path.basename(pred_file))}",
                    name=f"RSI Gate: {pred_def.get('predicate_name', 'unknown')}",
                    description=f"Auto-generated gate from RSI pattern: {pred_def.get('fault_signature', '')}",
                    gate_type=GateType.RSI,
                    source=pred_file,
                    trigger={"type": "always"},
                    evaluation={"type": "socratic", "tree": pred_def.get("tree", {})},
                    actions=[{"type": "report", "severity": "MEDIUM"}],
                    severity=GateSeverity.MEDIUM,
                    metadata={
                        "fault_signature": pred_def.get("fault_signature", ""),
                        "correction_path": pred_def.get("correction_path", ""),
                        "generated_at": pred_def.get("generated_at", 0)
                    }
                )
                self.gates[gate.id] = gate
            except Exception as e:
                print(f"Warning: Failed to load RSI gate {pred_file}: {e}")
    
    def get_gate(self, gate_id: str) -> Optional[GateDefinition]:
        """Get a specific gate by ID."""
        return self.gates.get(gate_id)
    
    def get_gates_by_type(self, gate_type: GateType) -> List[GateDefinition]:
        """Get all gates of a specific type."""
        return [g for g in self.gates.values() if g.gate_type == gate_type]
    
    def get_gates_by_trigger(self, trigger_type: str) -> List[GateDefinition]:
        """Get all gates that match a specific trigger type."""
        matching = []
        for gate in self.gates.values():
            if not gate.enabled:
                continue
            gate_trigger = gate.trigger.get("type", "")
            if gate_trigger == "always" or gate_trigger == trigger_type:
                matching.append(gate)
        return matching
    
    def get_active_gates(self) -> List[GateDefinition]:
        """Get all enabled gates."""
        return [g for g in self.gates.values() if g.enabled]
    
    def register_gate(self, gate: GateDefinition) -> bool:
        """Register a new gate dynamically."""
        if gate.id in self.gates:
            print(f"Warning: Gate {gate.id} already exists")
            return False
        self.gates[gate.id] = gate
        return True
    
    def unregister_gate(self, gate_id: str) -> bool:
        """Unregister a gate."""
        if gate_id in self.gates:
            del self.gates[gate_id]
            return True
        return False
    
    def enable_gate(self, gate_id: str) -> bool:
        """Enable a gate."""
        gate = self.gates.get(gate_id)
        if gate:
            gate.enabled = True
            return True
        return False
    
    def disable_gate(self, gate_id: str) -> bool:
        """Disable a gate."""
        gate = self.gates.get(gate_id)
        if gate:
            gate.enabled = False
            return True
        return False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert registry to dictionary for serialization."""
        return {
            "gates": {
                gate_id: {
                    "id": gate.id,
                    "name": gate.name,
                    "description": gate.description,
                    "gate_type": gate.gate_type.value,
                    "source": gate.source,
                    "trigger": gate.trigger,
                    "evaluation": gate.evaluation,
                    "actions": gate.actions,
                    "severity": gate.severity.value,
                    "enabled": gate.enabled,
                    "metadata": gate.metadata
                }
                for gate_id, gate in self.gates.items()
            },
            "summary": {
                "total": len(self.gates),
                "by_type": {
                    gate_type.value: len(self.get_gates_by_type(gate_type))
                    for gate_type in GateType
                },
                "enabled": len(self.get_active_gates())
            }
        }
    
    def print_summary(self):
        """Print a summary of all registered gates."""
        print("=== Gate Registry Summary ===")
        print(f"Total gates: {len(self.gates)}")
        print(f"Enabled: {len(self.get_active_gates())}")
        print()
        
        for gate_type in GateType:
            gates = self.get_gates_by_type(gate_type)
            if gates:
                print(f"{gate_type.value.upper()} gates ({len(gates)}):")
                for gate in gates:
                    status = "✓" if gate.enabled else "✗"
                    print(f"  {status} {gate.id}: {gate.name}")
                print()


# Singleton instance
_registry = None

def get_registry(repo_root: Optional[str] = None) -> GateRegistry:
    """Get or create the global gate registry."""
    global _registry
    if _registry is None:
        _registry = GateRegistry(repo_root)
    return _registry


def reload_registry(repo_root: Optional[str] = None) -> GateRegistry:
    """Reload the gate registry from all sources."""
    global _registry
    _registry = GateRegistry(repo_root)
    return _registry


# CLI entry point
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--json":
        registry = get_registry()
        print(json.dumps(registry.to_dict(), indent=2))
    else:
        registry = get_registry()
        registry.print_summary()
