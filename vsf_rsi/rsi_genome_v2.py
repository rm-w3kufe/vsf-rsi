"""
Genoma-V2 — Feature construction + decision tree genome.

解决了 Genoma-V1 的根本限制：
  V1: {threshold, branch_count} → 只能做 1D 阈值
  V2: {features, tree} → 可以表示任意布尔逻辑

结构：
  1. Feature Construction: 从原始特征派生新特征 (z = x*y, z = x²+y²)
  2. Decision Tree: 在特征上做条件判断的树

操作符：
  - 算术: add, sub, mul, div, abs, square
  - 比较: gt, lt, eq
  - 逻辑: and, or, not
  - 常数: constant
"""

from __future__ import annotations

import copy
import random
import math
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple


# ── Feature Construction ─────────────────────────────────────────────

ARITHMETIC_OPS = ["add", "sub", "mul", "abs", "square"]
COMPARISON_OPS = ["gt", "lt"]
LOGIC_OPS = ["and", "or", "not"]
CONSTANT_OPS = ["constant"]

ALL_OPS = ARITHMETIC_OPS + COMPARISON_OPS + LOGIC_OPS + CONSTANT_OPS


@dataclass
class FeatureNode:
    """A node in the feature construction graph."""
    name: str
    op: str  # operation: add, sub, mul, abs, square, gt, lt, and, or, not, constant
    args: List[str] = field(default_factory=list)  # input feature names
    constant_value: float = 0.0  # for constant op
    output_name: str = ""  # name of output feature

    def __post_init__(self):
        if not self.output_name:
            self.output_name = self.name


@dataclass
class TreeNode:
    """A node in the decision tree."""
    condition: Optional[str] = None  # feature name for comparison
    threshold: float = 0.0
    operator: str = "gt"  # gt, lt, eq
    result: Optional[bool] = None  # leaf node result
    left: Optional["TreeNode"] = None  # branch for True
    right: Optional["TreeNode"] = None  # branch for False

    @property
    def is_leaf(self) -> bool:
        return self.result is not None


@dataclass
class GenomeV2:
    """Genome V2: feature construction + decision tree."""
    id: str
    features: List[FeatureNode] = field(default_factory=list)
    tree: Optional[TreeNode] = None
    available_features: List[str] = field(default_factory=list)  # raw input features
    fitness: float = 0.0
    generation: int = 0
    parent_ids: List[str] = field(default_factory=list)


# ── Random Genome Generation ────────────────────────────────────────

def create_random_genome_v2(
    genome_id: str,
    available_features: List[str],
    n_derived: int = 2,
    tree_depth: int = 2,
    gen: int = 0,
) -> GenomeV2:
    """Create a random GenomeV2."""
    features = []
    current_features = list(available_features)

    for i in range(n_derived):
        # Pick 1-2 input features
        n_inputs = random.choice([1, 2])
        inputs = random.sample(current_features, min(n_inputs, len(current_features)))

        # Pick operation
        op = random.choice(ARITHMETIC_OPS)

        # For constant ops, add a constant feature
        if op in ["gt", "lt"]:
            const_name = f"_const_{i}"
            features.append(FeatureNode(
                name=const_name,
                op="constant",
                constant_value=random.uniform(-1, 1),
                output_name=const_name,
            ))
            inputs.append(const_name)
            current_features.append(const_name)

        feat = FeatureNode(
            name=f"derived_{i}",
            op=op,
            args=inputs,
            output_name=f"d{i}",
        )
        features.append(feat)
        current_features.append(f"d{i}")

    # Build random tree
    tree = _random_tree(current_features, max_depth=tree_depth, depth=0)

    return GenomeV2(
        id=genome_id,
        features=features,
        tree=tree,
        available_features=available_features,
        generation=gen,
    )


def _random_tree(features: List[str], max_depth: int, depth: int) -> TreeNode:
    """Create a random decision tree."""
    # Leaf at max depth or randomly
    if depth >= max_depth or (depth > 0 and random.random() < 0.3):
        return TreeNode(result=random.choice([True, False]))

    # Internal node
    condition = random.choice(features)
    threshold = random.uniform(-1, 1)
    operator = random.choice(["gt", "lt"])

    return TreeNode(
        condition=condition,
        threshold=threshold,
        operator=operator,
        left=_random_tree(features, max_depth, depth + 1),
        right=_random_tree(features, max_depth, depth + 1),
    )


# ── Feature Evaluation ──────────────────────────────────────────────

def evaluate_features(
    features: List[FeatureNode],
    raw_context: Dict[str, float],
) -> Dict[str, float]:
    """Evaluate feature construction graph.

    Args:
        features: list of FeatureNodes defining derived features
        raw_context: raw input features (e.g., {"x": 0.5, "y": -0.3})

    Returns:
        dict of all features (raw + derived)
    """
    # Start with raw features
    all_features = dict(raw_context)

    # Evaluate derived features in order
    for feat in features:
        # Resolve input values
        input_values = []
        for arg in feat.args:
            if arg in all_features:
                input_values.append(all_features[arg])
            else:
                input_values.append(0.0)  # missing feature defaults to 0

        # Compute output
        output = _apply_op(feat.op, input_values, feat.constant_value)
        all_features[feat.output_name] = output

    return all_features


def _apply_op(op: str, inputs: List[float], constant: float = 0.0) -> float:
    """Apply an operation to input values."""
    # Operation handlers
    ops = {
        "add": lambda: sum(inputs) if inputs else 0.0,
        "sub": lambda: inputs[0] - inputs[1] if len(inputs) >= 2 else inputs[0] if inputs else 0.0,
        "mul": lambda: __import__('functools').reduce(lambda a, b: a * b, inputs, 1.0),
        "abs": lambda: abs(inputs[0]) if inputs else 0.0,
        "square": lambda: inputs[0] ** 2 if inputs else 0.0,
        "constant": lambda: constant,
        "gt": lambda: 1.0 if inputs[0] > inputs[1] else 0.0 if len(inputs) >= 2 else 0.0,
        "lt": lambda: 1.0 if inputs[0] < inputs[1] else 0.0 if len(inputs) >= 2 else 0.0,
        "and": lambda: 1.0 if all(v > 0.5 for v in inputs) else 0.0,
        "or": lambda: 1.0 if any(v > 0.5 for v in inputs) else 0.0,
        "not": lambda: 0.0 if inputs and inputs[0] > 0.5 else 1.0,
    }
    
    handler = ops.get(op, lambda: 0.0)
    return handler()


# ── Tree Evaluation ──────────────────────────────────────────────────

def evaluate_tree(tree: TreeNode, features: Dict[str, float]) -> bool:
    """Evaluate a decision tree against feature values."""
    if tree.is_leaf:
        return tree.result

    # Get feature value
    value = features.get(tree.condition, 0.0)

    # Apply comparison
    if tree.operator == "gt":
        result = value > tree.threshold
    elif tree.operator == "lt":
        result = value < tree.threshold
    elif tree.operator == "eq":
        result = abs(value - tree.threshold) < 0.01
    else:
        result = value > tree.threshold

    # Recurse
    if result:
        return evaluate_tree(tree.left, features) if tree.left else False
    else:
        return evaluate_tree(tree.right, features) if tree.right else False


# ── Genome → Predicate ──────────────────────────────────────────────

def genome_to_predicate_v2(genome: GenomeV2) -> Callable[[Dict], bool]:
    """Convert GenomeV2 to a callable predicate.

    The predicate receives a context dict, evaluates features,
    and runs the decision tree.
    """
    # Deep copy to avoid mutation
    features = copy.deepcopy(genome.features)
    tree = copy.deepcopy(genome.tree)

    def pred(ctx: Dict) -> bool:
        # Extract raw features from context
        # Look in "context" nested dict or top level
        raw = ctx.get("context", {})
        if not raw:
            raw = ctx

        # Convert to floats
        raw_floats = {}
        for k, v in raw.items():
            if isinstance(v, (int, float)):
                raw_floats[k] = float(v)
            elif isinstance(v, dict):
                # Handle nested dicts (e.g., variables in XOR)
                for k2, v2 in v.items():
                    if isinstance(v2, (int, float)):
                        raw_floats[k2] = float(v2)

        # Evaluate features
        all_features = evaluate_features(features, raw_floats)

        # Evaluate tree
        return evaluate_tree(tree, all_features)

    return pred


# ── Genetic Operators ────────────────────────────────────────────────

def crossover_v2(
    p1: GenomeV2,
    p2: GenomeV2,
) -> Tuple[GenomeV2, GenomeV2]:
    """Crossover two genomes by swapping subtrees and features."""
    # Swap a random feature from each
    child1_features = copy.deepcopy(p1.features)
    child2_features = copy.deepcopy(p2.features)

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
        _swap_random_subtree(child1_tree, child2_tree)

    # Build children with combined features
    all_features_1 = child1_features + [f for f in p2.features if f not in child1_features]
    all_features_2 = child2_features + [f for f in p1.features if f not in child2_features]

    c1 = GenomeV2(
        id=f"{p1.id}_x_{p2.id}",
        features=all_features_1[:len(p1.features)],  # keep original count
        tree=child1_tree,
        available_features=p1.available_features,
        generation=max(p1.generation, p2.generation) + 1,
        parent_ids=[p1.id, p2.id],
    )
    c2 = GenomeV2(
        id=f"{p2.id}_x_{p1.id}",
        features=all_features_2[:len(p2.features)],
        tree=child2_tree,
        available_features=p2.available_features,
        generation=max(p1.generation, p2.generation) + 1,
        parent_ids=[p1.id, p2.id],
    )
    return c1, c2


def _swap_random_subtree(t1: TreeNode, t2: TreeNode, depth: int = 0):
    """Swap random subtrees between two trees."""
    if t1.is_leaf or t2.is_leaf:
        return

    if random.random() < 0.3 or depth > 5:
        # Swap this node's children with the other
        t1.left, t2.left = t2.left, t1.left
        t1.right, t2.right = t2.right, t1.right
        return

    # Recurse into a random child
    if random.random() < 0.5 and t1.left and t2.left:
        _swap_random_subtree(t1.left, t2.left, depth + 1)
    elif t1.right and t2.right:
        _swap_random_subtree(t1.right, t2.right, depth + 1)


def mutate_v2(genome: GenomeV2, rate: float = 0.2) -> GenomeV2:
    """Mutate a GenomeV2."""
    g = copy.deepcopy(genome)

    # Mutate features
    for feat in g.features:
        if random.random() < rate:
            # Change operation
            feat.op = random.choice(ARITHMETIC_OPS)

        if random.random() < rate:
            # Change constant value
            feat.constant_value += random.gauss(0, 0.2)
            feat.constant_value = max(-2, min(2, feat.constant_value))

    # Mutate tree
    if g.tree and random.random() < rate:
        _mutate_tree_node(g.tree, g.available_features + [f.output_name for f in g.features])

    return g


def _mutate_tree_node(node: TreeNode, features: List[str], rate: float = 0.3):
    """Mutate a single tree node."""
    if node.is_leaf:
        if random.random() < rate:
            node.result = not node.result
        return

    if random.random() < rate:
        # Change condition feature
        node.condition = random.choice(features)

    if random.random() < rate:
        # Change threshold
        node.threshold += random.gauss(0, 0.2)
        node.threshold = max(-2, min(2, node.threshold))

    if random.random() < rate:
        # Change operator
        node.operator = random.choice(["gt", "lt"])

    # Recurse
    if node.left:
        _mutate_tree_node(node.left, features, rate)
    if node.right:
        _mutate_tree_node(node.right, features, rate)


# ── Visualization ────────────────────────────────────────────────────

def genome_to_tree_str(tree: TreeNode, indent: int = 0) -> str:
    """Convert tree to human-readable string."""
    if tree.is_leaf:
        return f"{'  '*indent}→ {tree.result}"

    cond = f"{tree.condition} {tree.operator} {tree.threshold:.2f}"
    left_str = genome_to_tree_str(tree.left, indent + 1) if tree.left else f"{'  '*(indent+1)}→ False"
    right_str = genome_to_tree_str(tree.right, indent + 1) if tree.right else f"{'  '*(indent+1)}→ False"

    return f"{'  '*indent}IF {cond}:\n{left_str}\n{'  '*indent}ELSE:\n{right_str}"


def genome_v2_summary(genome: GenomeV2) -> str:
    """Human-readable summary of a genome."""
    lines = [f"Genome {genome.id} (gen={genome.generation}, fitness={genome.fitness:.3f})"]

    if genome.features:
        lines.append("  Features:")
        for f in genome.features:
            args_str = ", ".join(f.args)
            lines.append(f"    {f.output_name} = {f.op}({args_str})")

    if genome.tree:
        lines.append("  Tree:")
        lines.append(genome_to_tree_str(genome.tree, indent=2))

    return "\n".join(lines)


__all__ = [
    "GenomeV2",
    "FeatureNode",
    "TreeNode",
    "create_random_genome_v2",
    "evaluate_features",
    "evaluate_tree",
    "genome_to_predicate_v2",
    "crossover_v2",
    "mutate_v2",
    "genome_to_tree_str",
    "genome_v2_summary",
]
