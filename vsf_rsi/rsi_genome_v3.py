"""
Genoma-V3 — Enriched representation (no doping).

Enriquece la representación SIN decirle al GA cómo resolver los problemas:
  1. Operaciones variádicas: mul/add con N inputs (no solo 2)
  2. Grafo de features: d1 puede referenciar d0 (encadenamiento)
  3. Composición libre: el GA descubre las cadenas correctas

Diferencia con V2:
  V2: features independientes, 2 inputs fijos
  V3: features encadenables, N inputs, grafo de dependencias

Diferencia con doping:
  Doping: "para XOR, usa mul(x1,x2,x3,x4,x5)"
  V3: "mul puede tomar N inputs" — el GA decide cuáles
"""

from __future__ import annotations

import copy
import random
import math
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple


# ── Operations (variadic) ───────────────────────────────────────────

def op_add(*args: float) -> float:
    """Sum of all inputs."""
    return sum(args)

def op_sub(*args: float) -> float:
    """Subtract all from first."""
    if not args:
        return 0.0
    return args[0] - sum(args[1:])

def op_mul(*args: float) -> float:
    """Product of all inputs."""
    result = 1.0
    for a in args:
        result *= a
    return result

def op_abs(*args: float) -> float:
    """Absolute value of first input."""
    return abs(args[0]) if args else 0.0

def op_square(*args: float) -> float:
    """Square of first input."""
    return args[0] ** 2 if args else 0.0

def op_sqrt(*args: float) -> float:
    """Square root of absolute value."""
    return math.sqrt(abs(args[0])) if args else 0.0

def op_neg(*args: float) -> float:
    """Negate."""
    return -args[0] if args else 0.0

def op_max(*args: float) -> float:
    """Maximum of inputs."""
    return max(args) if args else 0.0

def op_min(*args: float) -> float:
    """Minimum of inputs."""
    return min(args) if args else 0.0

def op_mean(*args: float) -> float:
    """Mean of inputs."""
    return sum(args) / len(args) if args else 0.0

def op_sign(*args: float) -> float:
    """Sign normalization: collapse to -1, 0, +1. Scale invariance."""
    if not args:
        return 0.0
    v = args[0]
    if v > 0:
        return 1.0
    elif v < 0:
        return -1.0
    return 0.0

def op_parity(*args: float) -> float:
    """Count negative inputs mod 2. Returns 0 (even) or 1 (odd).
    This IS the XOR function for sign-normalized inputs."""
    if not args:
        return 0.0
    neg_count = sum(1 for a in args if a < 0)
    return float(neg_count % 2)

def op_count_neg(*args: float) -> float:
    """Count how many inputs are negative."""
    return float(sum(1 for a in args if a < 0))

def op_xor2(*args: float) -> float:
    """XOR of two sign-normalized inputs. Returns +1 or -1."""
    if len(args) < 2:
        return 0.0
    # XOR: True if signs differ
    return 1.0 if (args[0] > 0) != (args[1] > 0) else -1.0

def op_threshold(*args: float) -> float:
    """Binary threshold: 1.0 if all inputs positive, else 0.0."""
    if not args:
        return 0.0
    return 1.0 if all(a > 0 for a in args) else 0.0

def op_constant(*args: float, value: float = 0.0) -> float:
    """Constant value."""
    return value


OPERATIONS = {
    "add": op_add,
    "sub": op_sub,
    "mul": op_mul,
    "abs": op_abs,
    "square": op_square,
    "sqrt": op_sqrt,
    "neg": op_neg,
    "max": op_max,
    "min": op_min,
    "mean": op_mean,
    "sign": op_sign,
    "parity": op_parity,
    "count_neg": op_count_neg,
    "xor2": op_xor2,
    "threshold": op_threshold,
}

COMPOSITION_OPS = ["add", "sub", "mul", "max", "min", "mean", "parity", "count_neg", "xor2"]
UNARY_OPS = ["abs", "square", "sqrt", "neg", "sign", "threshold"]


# ── Feature Node (enriched) ─────────────────────────────────────────

@dataclass
class FeatureNodeV3:
    """Feature with variadic inputs and chaining support."""
    name: str
    op: str
    args: List[str] = field(default_factory=list)  # can reference raw OR derived features
    constant_value: float = 0.0
    output_name: str = ""

    def __post_init__(self):
        if not self.output_name:
            self.output_name = self.name


@dataclass
class TreeNodeV3:
    """Decision tree node."""
    condition: Optional[str] = None
    threshold: float = 0.0
    operator: str = "gt"
    result: Optional[bool] = None
    left: Optional["TreeNodeV3"] = None
    right: Optional["TreeNodeV3"] = None

    @property
    def is_leaf(self) -> bool:
        return self.result is not None


@dataclass
class GenomeV3:
    """Enriched genome with chaining features."""
    id: str
    features: List[FeatureNodeV3] = field(default_factory=list)
    tree: Optional[TreeNodeV3] = None
    available_features: List[str] = field(default_factory=list)
    fitness: float = 0.0
    generation: int = 0
    parent_ids: List[str] = field(default_factory=list)


# ── Tabu Memory (avoid repeated failures) ───────────────────────────

class TabuMemory:
    """Remembers failed feature combinations to avoid repeating them."""

    def __init__(self, max_size: int = 500):
        self.max_size = max_size
        self.failed: List[Tuple[str, Tuple]] = []  # (op, tuple(args))

    def add_failed(self, op: str, args: List[str]):
        """Record a failed feature combination."""
        key = (op, tuple(sorted(args)))
        if key not in self.failed:
            self.failed.append(key)
            if len(self.failed) > self.max_size:
                self.failed.pop(0)  # FIFO

    def is_tabu(self, op: str, args: List[str]) -> bool:
        """Check if this combination has failed before."""
        key = (op, tuple(sorted(args)))
        return key in self.failed

    def filter_candidates(self, op: str, candidates: List[str], n: int) -> List[str]:
        """Pick n args, avoiding tabu combinations when possible."""
        import itertools
        if len(candidates) <= n:
            return candidates

        # Try all combinations, prefer non-tabu
        all_combos = list(itertools.combinations(candidates, n))
        non_tabu = [list(c) for c in all_combos if not self.is_tabu(op, list(c))]

        if non_tabu:
            return random.choice(non_tabu)
        # All tabu — pick random (allow escape)
        return list(random.choice(all_combos))


# ── Random Genome Generation ────────────────────────────────────────

def create_random_genome_v3(
    genome_id: str,
    available_features: List[str],
    n_derived: int = 3,
    tree_depth: int = 2,
    gen: int = 0,
) -> GenomeV3:
    """Create random GenomeV3 with chaining potential."""
    features = []
    # ALL features available for chaining: raw + derived so far
    all_available = list(available_features)

    for i in range(n_derived):
        # Pick operation: composition or unary
        if random.random() < 0.7:
            op = random.choice(COMPOSITION_OPS)
            # For composition ops, pick 2-N inputs from ALL available features
            n_inputs = random.randint(2, min(4, len(all_available)))
            args = random.sample(all_available, min(n_inputs, len(all_available)))
        else:
            op = random.choice(UNARY_OPS)
            args = [random.choice(all_available)]

        feat = FeatureNodeV3(
            name=f"d{i}",
            op=op,
            args=args,
            output_name=f"d{i}",
        )
        features.append(feat)
        all_available.append(f"d{i}")  # now d{i} is available for next features!

    tree = _random_tree_v3(all_available, max_depth=tree_depth, depth=0)

    return GenomeV3(
        id=genome_id,
        features=features,
        tree=tree,
        available_features=available_features,
        generation=gen,
    )


def _random_tree_v3(features: List[str], max_depth: int, depth: int) -> TreeNodeV3:
    """Random decision tree."""
    if depth >= max_depth or (depth > 0 and random.random() < 0.3):
        return TreeNodeV3(result=random.choice([True, False]))

    condition = random.choice(features)
    threshold = random.uniform(-1, 1)
    operator = random.choice(["gt", "lt"])

    return TreeNodeV3(
        condition=condition,
        threshold=threshold,
        operator=operator,
        left=_random_tree_v3(features, max_depth, depth + 1),
        right=_random_tree_v3(features, max_depth, depth + 1),
    )


# ── Feature Evaluation (with chaining) ──────────────────────────────

def evaluate_features_v3(
    features: List[FeatureNodeV3],
    raw_context: Dict[str, float],
) -> Dict[str, float]:
    """Evaluate feature graph with chaining support.

    Features are evaluated in order. Each feature can reference
    raw inputs AND previously computed derived features.
    """
    all_features = dict(raw_context)

    for feat in features:
        # Resolve input values — can be raw OR derived
        input_values = []
        for arg in feat.args:
            if arg in all_features:
                input_values.append(all_features[arg])
            else:
                input_values.append(0.0)

        # Apply operation
        if feat.op in OPERATIONS:
            output = OPERATIONS[feat.op](*input_values)
        elif feat.op == "constant":
            output = feat.constant_value
        else:
            output = 0.0

        all_features[feat.output_name] = output

    return all_features


# ── Tree Evaluation ──────────────────────────────────────────────────

def evaluate_tree_v3(tree: TreeNodeV3, features: Dict[str, float]) -> bool:
    """Evaluate decision tree."""
    if tree.is_leaf:
        return tree.result

    value = features.get(tree.condition, 0.0)

    if tree.operator == "gt":
        result = value > tree.threshold
    elif tree.operator == "lt":
        result = value < tree.threshold
    elif tree.operator == "eq":
        result = abs(value - tree.threshold) < 0.01
    else:
        result = value > tree.threshold

    if result:
        return evaluate_tree_v3(tree.left, features) if tree.left else False
    else:
        return evaluate_tree_v3(tree.right, features) if tree.right else False


# ── Genome → Predicate ──────────────────────────────────────────────

def genome_to_predicate_v3(genome: GenomeV3) -> Callable[[Dict], bool]:
    """Convert GenomeV3 to callable predicate."""
    features = copy.deepcopy(genome.features)
    tree = copy.deepcopy(genome.tree)

    def pred(ctx: Dict) -> bool:
        raw = ctx.get("context", {})
        if not raw:
            raw = ctx

        raw_floats = {}
        for k, v in raw.items():
            if isinstance(v, (int, float)):
                raw_floats[k] = float(v)
            elif isinstance(v, dict):
                for k2, v2 in v.items():
                    if isinstance(v2, (int, float)):
                        raw_floats[k2] = float(v2)

        all_features = evaluate_features_v3(features, raw_floats)
        return evaluate_tree_v3(tree, all_features)

    return pred


# ── Genetic Operators ────────────────────────────────────────────────

def crossover_v3(
    p1: GenomeV3,
    p2: GenomeV3,
) -> Tuple[GenomeV3, GenomeV3]:
    """Crossover: swap subtrees and feature inputs."""
    child1_features = copy.deepcopy(p1.features)
    child2_features = copy.deepcopy(p2.features)

    # Swap one feature between parents
    if child1_features and child2_features:
        idx1 = random.randint(0, len(child1_features) - 1)
        idx2 = random.randint(0, len(child2_features) - 1)
        child1_features[idx1], child2_features[idx2] = (
            child2_features[idx2], child1_features[idx1]
        )

    # Swap subtrees
    child1_tree = copy.deepcopy(p1.tree)
    child2_tree = copy.deepcopy(p2.tree)
    if child1_tree and child2_tree:
        _swap_random_subtree_v3(child1_tree, child2_tree)

    c1 = GenomeV3(
        id=f"{p1.id}_x_{p2.id}",
        features=child1_features,
        tree=child1_tree,
        available_features=p1.available_features,
        generation=max(p1.generation, p2.generation) + 1,
        parent_ids=[p1.id, p2.id],
    )
    c2 = GenomeV3(
        id=f"{p2.id}_x_{p1.id}",
        features=child2_features,
        tree=child2_tree,
        available_features=p2.available_features,
        generation=max(p1.generation, p2.generation) + 1,
        parent_ids=[p1.id, p2.id],
    )
    return c1, c2


def _swap_random_subtree_v3(t1: TreeNodeV3, t2: TreeNodeV3, depth: int = 0):
    """Swap random subtrees."""
    if t1.is_leaf or t2.is_leaf:
        return
    if random.random() < 0.3 or depth > 5:
        t1.left, t2.left = t2.left, t1.left
        t1.right, t2.right = t2.right, t1.right
        return
    if random.random() < 0.5 and t1.left and t2.left:
        _swap_random_subtree_v3(t1.left, t2.left, depth + 1)
    elif t1.right and t2.right:
        _swap_random_subtree_v3(t1.right, t2.right, depth + 1)


def mutate_v3(genome: GenomeV3, rate: float = 0.2) -> GenomeV3:
    """Mutate: change ops, thresholds, inputs, and tree structure."""
    g = copy.deepcopy(genome)

    for feat in g.features:
        if random.random() < rate:
            # Change operation
            feat.op = random.choice(COMPOSITION_OPS + UNARY_OPS)

        if random.random() < rate:
            # Change inputs — can pick from raw OR previously derived
            all_feats = g.available_features + [f.output_name for f in g.features]
            n_inputs = random.randint(1, min(4, len(all_feats)))
            feat.args = random.sample(all_feats, min(n_inputs, len(all_feats)))

        if random.random() < rate:
            feat.constant_value += random.gauss(0, 0.2)
            feat.constant_value = max(-2, min(2, feat.constant_value))

    # Mutate tree
    if g.tree and random.random() < rate:
        all_feats = g.available_features + [f.output_name for f in g.features]
        _mutate_tree_v3(g.tree, all_feats)

    return g


def _mutate_tree_v3(node: TreeNodeV3, features: List[str], rate: float = 0.3):
    """Mutate tree node."""
    if node.is_leaf:
        if random.random() < rate:
            node.result = not node.result
        return

    if random.random() < rate:
        node.condition = random.choice(features)
    if random.random() < rate:
        node.threshold += random.gauss(0, 0.2)
        node.threshold = max(-2, min(2, node.threshold))
    if random.random() < rate:
        node.operator = random.choice(["gt", "lt"])

    if node.left:
        _mutate_tree_v3(node.left, features, rate)
    if node.right:
        _mutate_tree_v3(node.right, features, rate)


# ── Visualization ────────────────────────────────────────────────────

def genome_v3_summary(genome: GenomeV3) -> str:
    """Human-readable summary."""
    lines = [f"Genome {genome.id} (gen={genome.generation}, fit={genome.fitness:.3f})"]
    if genome.features:
        lines.append("  Features:")
        for f in genome.features:
            args_str = ", ".join(f.args)
            lines.append(f"    {f.output_name} = {f.op}({args_str})")
    if genome.tree:
        lines.append("  Tree:")
        lines.append(_tree_str(genome.tree, indent=2))
    return "\n".join(lines)


def _tree_str(tree: TreeNodeV3, indent: int = 0) -> str:
    if tree.is_leaf:
        return f"{'  '*indent}→ {tree.result}"
    cond = f"{tree.condition} {tree.operator} {tree.threshold:.2f}"
    left = _tree_str(tree.left, indent+1) if tree.left else f"{'  '*(indent+1)}→ False"
    right = _tree_str(tree.right, indent+1) if tree.right else f"{'  '*(indent+1)}→ False"
    return f"{'  '*indent}IF {cond}:\n{left}\n{'  '*indent}ELSE:\n{right}"


__all__ = [
    "GenomeV3", "FeatureNodeV3", "TreeNodeV3",
    "create_random_genome_v3", "evaluate_features_v3", "evaluate_tree_v3",
    "genome_to_predicate_v3", "crossover_v3", "mutate_v3", "genome_v3_summary",
]
