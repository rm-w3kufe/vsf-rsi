#!/usr/bin/env python3
"""
RSI Genetic Algorithm — Evolves trees using genetic principles
Uses Forest concept: population of trees that evolve over generations.

RSI LEVEL 4: AUTO-EVOLUTION
- Population management (Forest)
- Fitness evaluation
- Selection (tournament, roulette)
- Crossover (subtree exchange)
- Mutation (branch modification)
- Generational evolution
"""

import json
import os
import random
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from dataclasses import dataclass, asdict
from vsf_rsi.rsi_metrics import RSIMetrics

# ── Configuration ────────────────────────────────────────────────────
EVOLUTION_DIR = Path(__file__).parent.parent / "docs"
FOREST_FILE = EVOLUTION_DIR / "rsi_forest.json"
EVOLUTION_HISTORY_FILE = EVOLUTION_DIR / "rsi_evolution_history.jsonl"

# DEBT-004: Convergence check configuration
CONVERGENCE_THRESHOLD: float = 0.001  # Minimum fitness improvement to consider
CONVERGENCE_PATIENCE: int = 3         # Generations without improvement before stopping


@dataclass
class TreeGenome:
    """Genetic representation of a tree."""
    id: str
    name: str
    genes: Dict  # Tree structure as genes
    fitness: float = 0.0
    generation: int = 0
    parent_ids: List[str] = None
    created: str = ""
    
    def __post_init__(self):
        if self.parent_ids is None:
            self.parent_ids = []
        if not self.created:
            self.created = datetime.now(timezone.utc).isoformat()


class RSIGeneticAlgorithm:
    """Genetic algorithm for tree evolution."""
    
    def __init__(self, population_size: int = 10, mutation_rate: float = 0.1):
        """
        Initialize genetic algorithm.
        
        Args:
            population_size: Number of trees in forest
            mutation_rate: Probability of mutation (0.0 to 1.0)
        """
        self.population_size = population_size
        self.mutation_rate = mutation_rate
        self.metrics = RSIMetrics()
        self.evolution_dir = EVOLUTION_DIR
        self.evolution_dir.mkdir(parents=True, exist_ok=True)
        
        # Auto-rebuild metrics from history if store is empty (closes feedback loop)
        if not self.metrics._load_metrics():
            self.metrics.rebuild_from_history()
        
    def create_forest(self, predicate_name: str) -> List[TreeGenome]:
        """
        Create initial forest (population) of trees.
        
        Args:
            predicate_name: Name of predicate
        
        Returns:
            List of TreeGenome objects
        """
        forest = []
        
        for i in range(self.population_size):
            # Create random tree genome
            genome = TreeGenome(
                id=f"{predicate_name}_gen0_{i}",
                name=f"{predicate_name}_tree_{i}",
                genes=self._random_genome(predicate_name),
                generation=0
            )
            forest.append(genome)
        
        # Save forest
        self._save_forest(predicate_name, forest)
        
        return forest
    
    def _random_genome(self, predicate_name: str) -> Dict:
        """Create random genome for a tree."""
        # Genome represents tree structure
        return {
            "type": "decision",
            "branches": [
                {
                    "condition": random.choice([
                        "ctx_equals($ctx, 'value', 0.5)",
                        "ctx_equals($ctx, 'value', 0.7)",
                        "ctx_equals($ctx, 'value', 0.9)",
                        "ctx_has($ctx, 'active')",
                        "TRUE"
                    ]),
                    "action": random.choice([
                        '{"home": "ok", "truth": "normal", "certified": TRUE}',
                        '{"home": "warning", "truth": "borderline", "certified": TRUE}',
                        '{"home": "critical", "truth": "edge case", "certified": TRUE}',
                        '{"home": "escalate", "truth": "unknown", "certified": TRUE}'
                    ])
                }
                for _ in range(random.randint(2, 5))
            ],
            "threshold": random.uniform(0.5, 0.9),
            "complexity": random.randint(1, 5)
        }
    
    def evaluate_fitness(self, forest: List[TreeGenome], predicate_name: str) -> List[TreeGenome]:
        """
        Evaluate fitness of each tree in forest.
        
        Args:
            forest: List of TreeGenome objects
            predicate_name: Name of predicate
        
        Returns:
            Updated forest with fitness scores
        """
        for genome in forest:
            # Calculate fitness based on multiple factors
            fitness = 0.0
            
            # Factor 1: Accuracy (from metrics)
            accuracy = self.metrics.get_accuracy(predicate_name, genome.genes.get("threshold", 0.7))
            fitness += accuracy * 0.4  # 40% weight
            
            # Factor 2: Complexity penalty (simpler is better)
            complexity = genome.genes.get("complexity", 1)
            fitness += (1.0 / complexity) * 0.2  # 20% weight
            
            # Factor 3: Branch diversity (more diverse is better)
            branch_count = len(genome.genes.get("branches", []))
            fitness += min(branch_count / 5, 1.0) * 0.2  # 20% weight
            
            # Factor 4: Threshold appropriateness
            threshold = genome.genes.get("threshold", 0.7)
            if 0.6 <= threshold <= 0.8:  # Optimal range
                fitness += 0.2  # 20% weight
            
            genome.fitness = fitness
        
        return forest
    
    def select_parents(self, forest: List[TreeGenome], method: str = "tournament") -> List[TreeGenome]:
        """
        Select parents for reproduction.
        
        Args:
            forest: List of TreeGenome objects
            method: Selection method (tournament, roulette)
        
        Returns:
            List of selected parents
        """
        parents = []
        
        if method == "tournament":
            # Tournament selection
            for _ in range(len(forest) // 2):
                # Select random candidates
                candidates = random.sample(forest, min(3, len(forest)))
                # Select best
                winner = max(candidates, key=lambda x: x.fitness)
                parents.append(winner)
        
        elif method == "roulette":
            # Roulette wheel selection
            total_fitness = sum(g.fitness for g in forest)
            if total_fitness == 0:
                return random.sample(forest, min(2, len(forest)))
            
            for _ in range(len(forest) // 2):
                pick = random.uniform(0, total_fitness)
                current = 0
                for genome in forest:
                    current += genome.fitness
                    if current >= pick:
                        parents.append(genome)
                        break
        
        return parents
    
    def crossover(self, parent1: TreeGenome, parent2: TreeGenome) -> Tuple[TreeGenome, TreeGenome]:
        """
        Perform crossover between two parents.
        
        Args:
            parent1: First parent
            parent2: Second parent
        
        Returns:
            Two offspring
        """
        # Create offspring by mixing genes
        offspring1_genes = self._mix_genes(parent1.genes, parent2.genes)
        offspring2_genes = self._mix_genes(parent2.genes, parent1.genes)
        
        offspring1 = TreeGenome(
            id=f"{parent1.name}_x_{parent2.name}_1",
            name=f"{parent1.name}_cross_1",
            genes=offspring1_genes,
            generation=max(parent1.generation, parent2.generation) + 1,
            parent_ids=[parent1.id, parent2.id]
        )
        
        offspring2 = TreeGenome(
            id=f"{parent1.name}_x_{parent2.name}_2",
            name=f"{parent1.name}_cross_2",
            genes=offspring2_genes,
            generation=max(parent1.generation, parent2.generation) + 1,
            parent_ids=[parent1.id, parent2.id]
        )
        
        return offspring1, offspring2
    
    def _mix_genes(self, genes1: Dict, genes2: Dict) -> Dict:
        """Mix genes from two parents."""
        mixed = {}
        
        for key in genes1:
            if key in genes2:
                # Randomly choose from either parent
                mixed[key] = random.choice([genes1[key], genes2[key]])
            else:
                mixed[key] = genes1[key]
        
        # Add any unique genes from parent2
        for key in genes2:
            if key not in mixed:
                mixed[key] = genes2[key]
        
        return mixed
    
    def mutate(self, genome: TreeGenome) -> TreeGenome:
        """
        Perform mutation on a genome.
        
        Args:
            genome: Genome to mutate
        
        Returns:
            Mutated genome
        """
        if random.random() > self.mutation_rate:
            return genome  # No mutation
        
        # Create mutated copy
        mutated_genes = genome.genes.copy()
        
        # Choose mutation type
        mutation_type = random.choice(["threshold", "branch", "complexity"])
        
        if mutation_type == "threshold":
            # Mutate threshold
            old_threshold = mutated_genes.get("threshold", 0.7)
            new_threshold = old_threshold + random.uniform(-0.1, 0.1)
            new_threshold = max(0.1, min(0.9, new_threshold))  # Clamp
            mutated_genes["threshold"] = new_threshold
        
        elif mutation_type == "branch":
            # Mutate a branch
            if "branches" in mutated_genes and mutated_genes["branches"]:
                branch_idx = random.randint(0, len(mutated_genes["branches"]) - 1)
                mutated_genes["branches"][branch_idx]["condition"] = random.choice([
                    "ctx_equals($ctx, 'value', 0.5)",
                    "ctx_equals($ctx, 'value', 0.7)",
                    "ctx_equals($ctx, 'value', 0.9)",
                    "ctx_has($ctx, 'active')",
                    "TRUE"
                ])
        
        elif mutation_type == "complexity":
            # Mutate complexity
            old_complexity = mutated_genes.get("complexity", 1)
            new_complexity = old_complexity + random.choice([-1, 1])
            new_complexity = max(1, min(5, new_complexity))  # Clamp
            mutated_genes["complexity"] = new_complexity
        
        return TreeGenome(
            id=f"{genome.id}_mut",
            name=f"{genome.name}_mut",
            genes=mutated_genes,
            fitness=0.0,  # Needs re-evaluation
            generation=genome.generation,
            parent_ids=[genome.id]
        )
    
    def evolve_generation(self, forest: List[TreeGenome], predicate_name: str) -> List[TreeGenome]:
        """
        Evolve one generation.
        
        Args:
            forest: Current forest
            predicate_name: Name of predicate
        
        Returns:
            New forest (next generation)
        """
        # 1. Evaluate fitness
        forest = self.evaluate_fitness(forest, predicate_name)
        
        # 2. Select parents
        parents = self.select_parents(forest)
        
        # 3. Create offspring through crossover
        offspring = []
        for i in range(0, len(parents) - 1, 2):
            child1, child2 = self.crossover(parents[i], parents[i + 1])
            offspring.extend([child1, child2])
        
        # 4. Apply mutation
        offspring = [self.mutate(child) for child in offspring]
        
        # 5. Select next generation (elitism + offspring)
        # Keep top 20% from current generation
        elite_count = max(1, len(forest) // 5)
        elite = sorted(forest, key=lambda x: x.fitness, reverse=True)[:elite_count]
        
        # Fill rest with offspring
        next_generation = elite + offspring[:self.population_size - elite_count]
        
        # Ensure we have exactly population_size
        while len(next_generation) < self.population_size:
            next_generation.append(self._create_random_offspring(predicate_name))
        
        return next_generation[:self.population_size]
    
    def _create_random_offspring(self, predicate_name: str) -> TreeGenome:
        """Create random offspring."""
        return TreeGenome(
            id=f"{predicate_name}_random_{random.randint(0, 10000)}",
            name=f"{predicate_name}_random",
            genes=self._random_genome(predicate_name),
            generation=0
        )
    
    def evolve_forest(
        self,
        predicate_name: str,
        generations: int = 10,
        patience: int = CONVERGENCE_PATIENCE,
        convergence_threshold: float = CONVERGENCE_THRESHOLD,
    ) -> Dict:
        """
        Evolve forest over multiple generations.
        DEBT-004: Added convergence check with early stopping.
        
        Args:
            predicate_name: Name of predicate
            generations: Maximum number of generations
            patience: Generations without improvement before stopping
            convergence_threshold: Minimum fitness improvement to consider
        
        Returns:
            Evolution results
        """
        # Create initial forest
        forest = self.create_forest(predicate_name)
        
        evolution_history = []
        best_fitness = 0.0
        generations_without_improvement = 0
        converged = False
        
        for gen in range(generations):
            # Evolve one generation
            forest = self.evolve_generation(forest, predicate_name)
            
            # Record history
            avg_fitness = sum(g.fitness for g in forest) / len(forest)
            max_fitness = max(g.fitness for g in forest)
            best_tree = max(forest, key=lambda x: x.fitness)
            
            gen_record = {
                "generation": gen,
                "avg_fitness": avg_fitness,
                "max_fitness": max_fitness,
                "best_tree_id": best_tree.id,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            evolution_history.append(gen_record)
            
            # DEBT-004: Check for convergence
            improvement = max_fitness - best_fitness
            if improvement > convergence_threshold:
                best_fitness = max_fitness
                generations_without_improvement = 0
            else:
                generations_without_improvement += 1
            
            # Save history
            self._append_history(gen_record)
            
            # DEBT-004: Early stopping if converged
            if generations_without_improvement >= patience:
                converged = True
                break
        
        # Save final forest
        self._save_forest(predicate_name, forest)
        
        # Get best tree
        best_tree = max(forest, key=lambda x: x.fitness)
        
        return {
            "generations": len(evolution_history),
            "max_generations": generations,
            "converged": converged,
            "final_forest": forest,
            "best_tree": best_tree,
            "evolution_history": evolution_history,
            "improvement": evolution_history[-1]["max_fitness"] - evolution_history[0]["max_fitness"]
        }
    
    def _save_forest(self, predicate_name: str, forest: List[TreeGenome]) -> None:
        """Save forest to file."""
        forest_data = {
            "predicate": predicate_name,
            "population_size": len(forest),
            "trees": [asdict(g) for g in forest],
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        with open(FOREST_FILE, 'w') as f:
            json.dump(forest_data, f, indent=2)
    
    def _load_forest(self, predicate_name: str) -> List[TreeGenome]:
        """Load forest from file."""
        if FOREST_FILE.exists():
            with open(FOREST_FILE, 'r') as f:
                data = json.load(f)
                if data.get("predicate") == predicate_name:
                    return [TreeGenome(**t) for t in data.get("trees", [])]
        return []
    
    def _append_history(self, record: Dict) -> None:
        """Append evolution history."""
        with open(EVOLUTION_HISTORY_FILE, 'a') as f:
            f.write(json.dumps(record) + "\n")
    
    def get_evolution_stats(self, predicate_name: str) -> Dict:
        """Get evolution statistics."""
        forest = self._load_forest(predicate_name)
        
        if not forest:
            return {"error": "No forest found"}
        
        fitness_scores = [g.fitness for g in forest]
        
        return {
            "predicate": predicate_name,
            "population_size": len(forest),
            "avg_fitness": sum(fitness_scores) / len(fitness_scores),
            "max_fitness": max(fitness_scores),
            "min_fitness": min(fitness_scores),
            "best_tree": max(forest, key=lambda x: x.fitness).id,
            "generations": max(g.generation for g in forest)
        }


# ── CLI Interface ────────────────────────────────────────────────────
def main():
    """CLI interface for RSI genetic algorithm."""
    import argparse
    
    parser = argparse.ArgumentParser(description="RSI Genetic Algorithm")
    subparsers = parser.add_subparsers(dest="command")
    
    # Evolve command
    evolve_parser = subparsers.add_parser("evolve", help="Evolve forest")
    evolve_parser.add_argument("predicate", help="Predicate name")
    evolve_parser.add_argument("--generations", type=int, default=10, help="Number of generations")
    evolve_parser.add_argument("--population", type=int, default=10, help="Population size")
    
    # Stats command
    stats_parser = subparsers.add_parser("stats", help="Get evolution stats")
    stats_parser.add_argument("predicate", help="Predicate name")
    
    args = parser.parse_args()
    
    if args.command == "evolve":
        ga = RSIGeneticAlgorithm(population_size=args.population)
        result = ga.evolve_forest(args.predicate, args.generations)
        
        print(f"Evolution complete: {result['generations']} generations")
        print(f"Best tree: {result['best_tree'].id}")
        print(f"Best fitness: {result['best_tree'].fitness:.4f}")
        print(f"Improvement: {result['improvement']:.4f}")
    elif args.command == "stats":
        ga = RSIGeneticAlgorithm()
        stats = ga.get_evolution_stats(args.predicate)
        print(f"Forest stats for {args.predicate}:")
        print(f"  Population: {stats['population_size']}")
        print(f"  Avg fitness: {stats['avg_fitness']:.4f}")
        print(f"  Max fitness: {stats['max_fitness']:.4f}")
        print(f"  Best tree: {stats['best_tree']}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
