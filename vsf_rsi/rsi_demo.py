#!/usr/bin/env python3
"""
RSI Complete Demo — Demonstrates all 4 levels working together
Shows the full power of Recursive Self-Improvement.

Levels demonstrated:
1. Auto-Optimization: Adjusts thresholds based on metrics
2. Auto-Modification: Generates new trees based on gaps
3. Auto-Generation: Creates new components from patterns
4. Auto-Evolution: Evolves forests of trees genetically
"""

import random
import time
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

from scripts.vsl.classifier.rsi_metrics import RSIMetrics
from scripts.vsl.classifier.rsi_feedback_loop import RSIFeedbackLoop
from scripts.vsl.classifier.rsi_gap_detector import RSIGapDetector
from scripts.vsl.classifier.rsi_tree_generator import RSITreeGenerator
from scripts.vsl.classifier.rsi_pattern_detector import RSIPatternDetector
from scripts.vsl.classifier.rsi_predicate_generator import RSIPredicateGenerator
from scripts.vsl.classifier.rsi_advanced_tree_generator import RSIAdvancedTreeGenerator
from scripts.vsl.classifier.rsi_genetic_algorithm import RSIGeneticAlgorithm
from scripts.vsl.classifier.rsi_forest_generator import RSIForestGenerator


def print_header(title: str):
    """Print formatted header."""
    print()
    print("═" * 70)
    print(f"  {title}")
    print("═" * 70)
    print()


def print_step(step: int, title: str):
    """Print formatted step."""
    print(f"┌─ Step {step}: {title}")
    print("│")


def print_result(label: str, value):
    """Print formatted result."""
    if isinstance(value, float):
        print(f"│  {label}: {value:.4f}")
    else:
        print(f"│  {label}: {value}")


def print_footer():
    """Print formatted footer."""
    print("│")
    print("└" + "─" * 69)


def run_complete_demo():
    """Run complete RSI demo."""
    predicate = "ac_stasis_critical"
    
    print_header("RSI COMPLETE DEMONSTRATION")
    print(f"  Predicate: {predicate}")
    print(f"  Date: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"  Purpose: Show all 4 RSI levels working together")
    
    # ═══════════════════════════════════════════════════════════════
    # LEVEL 1: AUTO-OPTIMIZATION
    # ═══════════════════════════════════════════════════════════════
    print_header("LEVEL 1: AUTO-OPTIMIZATION")
    print("  Adjusts thresholds based on performance metrics")
    
    print_step(1, "Generate training data")
    metrics = RSIMetrics()
    
    for i in range(100):
        input_value = random.uniform(0.0, 1.0)
        expected = input_value > 0.7
        actual = expected
        latency = random.uniform(0.1, 5.0)
        
        metrics.track_classification(predicate, 0.7, input_value, expected, actual, latency)
    
    print_result("Samples generated", 100)
    print_footer()
    
    print_step(2, "Test multiple thresholds")
    test_thresholds = [0.5, 0.6, 0.7, 0.75, 0.8, 0.85, 0.9]
    results = {}
    
    for threshold in test_thresholds:
        accuracy = metrics.get_accuracy(predicate, threshold)
        results[threshold] = accuracy
        print_result(f"Threshold {threshold}", f"{accuracy:.2%}")
    
    print_footer()
    
    print_step(3, "Find optimal threshold")
    best_threshold = max(results, key=results.get)
    best_accuracy = results[best_threshold]
    
    print_result("Best threshold", best_threshold)
    print_result("Best accuracy", f"{best_accuracy:.2%}")
    print_footer()
    
    print_step(4, "Adjust threshold")
    feedback = RSIFeedbackLoop()
    current_threshold = feedback.get_current_threshold(predicate)
    
    print_result("Current threshold", current_threshold)
    print_result("New threshold", best_threshold)
    print_result("Improvement", f"{(best_accuracy - results[current_threshold]):.2%}")
    print_footer()
    
    # ═══════════════════════════════════════════════════════════════
    # LEVEL 2: AUTO-MODIFICATION
    # ═══════════════════════════════════════════════════════════════
    print_header("LEVEL 2: AUTO-MODIFICATION")
    print("  Generates new trees based on detected gaps")
    
    print_step(1, "Generate misclassifications")
    
    for i in range(50):
        input_value = random.uniform(0.0, 1.0)
        
        if random.random() < 0.3:  # 30% misclassification
            expected = random.choice([True, False])
            actual = not expected
        else:
            expected = input_value > 0.7
            actual = expected
        
        latency = random.uniform(0.1, 15.0)
        metrics.track_classification(predicate, 0.7, input_value, expected, actual, latency)
    
    print_result("Misclassifications generated", 50)
    print_footer()
    
    print_step(2, "Detect gaps")
    detector = RSIGapDetector()
    gaps = detector.detect_gaps(predicate)
    
    print_result("Gaps detected", len(gaps["gaps"]))
    for gap in gaps["gaps"]:
        print_result(f"  {gap['type']}", gap["severity"])
    print_footer()
    
    print_step(3, "Generate new tree")
    tree_gen = RSITreeGenerator()
    
    if gaps["gaps"]:
        tree_path = tree_gen.generate_tree(predicate, gaps)
        print_result("Generated tree", tree_path)
    else:
        print_result("No gaps", "No tree generated")
    print_footer()
    
    # ═══════════════════════════════════════════════════════════════
    # LEVEL 3: AUTO-GENERATION
    # ═══════════════════════════════════════════════════════════════
    print_header("LEVEL 3: AUTO-GENERATION")
    print("  Creates new components from detected patterns")
    
    print_step(1, "Generate diverse data")
    
    for i in range(100):
        input_value = random.uniform(0.0, 1.0)
        
        if random.random() < 0.2:  # 20% edge cases
            expected = random.choice([True, False])
            actual = expected
            latency = random.uniform(0.1, 5.0)
        elif random.random() < 0.3:  # 30% fast execution
            expected = input_value > 0.7
            actual = expected
            latency = random.uniform(0.01, 0.1)
        else:  # 50% normal
            expected = input_value > 0.7
            actual = expected
            latency = random.uniform(0.1, 10.0)
        
        metrics.track_classification(predicate, 0.7, input_value, expected, actual, latency)
    
    print_result("Diverse samples generated", 100)
    print_footer()
    
    print_step(2, "Detect patterns")
    pattern_detector = RSIPatternDetector()
    patterns = pattern_detector.detect_patterns(predicate)
    
    print_result("Patterns detected", len(patterns["patterns"]))
    for pattern in patterns["patterns"]:
        print_result(f"  {pattern['type']}", pattern["severity"])
    print_footer()
    
    print_step(3, "Generate components")
    predicate_gen = RSIPredicateGenerator()
    tree_gen_adv = RSIAdvancedTreeGenerator()
    
    generated_predicates = []
    generated_trees = []
    
    for pattern in patterns["patterns"]:
        # Generate predicate
        predicate_path = predicate_gen.generate_predicate({
            "name": f"{predicate}_{pattern['type']}",
            "purpose": pattern.get("suggestion", "Auto-generated"),
            "template": "edge_case_predicate"
        })
        generated_predicates.append(predicate_path)
        
        # Generate tree
        tree_path = tree_gen_adv.generate_advanced_tree({
            "name": f"{predicate}_{pattern['type']}",
            "purpose": pattern.get("suggestion", "Auto-generated"),
            "template": "threshold_optimized_tree",
            "best_threshold": 0.7
        })
        generated_trees.append(tree_path)
    
    print_result("Predicates generated", len(generated_predicates))
    print_result("Trees generated", len(generated_trees))
    print_footer()
    
    # ═══════════════════════════════════════════════════════════════
    # LEVEL 4: AUTO-EVOLUTION (FOREST)
    # ═══════════════════════════════════════════════════════════════
    print_header("LEVEL 4: AUTO-EVOLUTION (FOREST)")
    print("  Evolves forests of trees genetically")
    
    print_step(1, "Create initial forest")
    ga = RSIGeneticAlgorithm(population_size=10)
    forest = ga.create_forest(predicate)
    
    print_result("Forest created", f"{len(forest)} trees")
    print_footer()
    
    print_step(2, "Evaluate initial fitness")
    forest = ga.evaluate_fitness(forest, predicate)
    initial_avg = sum(g.fitness for g in forest) / len(forest)
    initial_max = max(g.fitness for g in forest)
    
    print_result("Initial avg fitness", initial_avg)
    print_result("Initial max fitness", initial_max)
    print_footer()
    
    print_step(3, "Evolve over 10 generations")
    print("│")
    print(f"│  {'Gen':<5} {'Avg Fitness':<15} {'Max Fitness':<15}")
    print(f"│  {'─'*5} {'─'*15} {'─'*15}")
    
    for gen in range(10):
        forest = ga.evolve_generation(forest, predicate)
        avg_fitness = sum(g.fitness for g in forest) / len(forest)
        max_fitness = max(g.fitness for g in forest)
        print(f"│  {gen+1:<5} {avg_fitness:<15.4f} {max_fitness:<15.4f}")
    
    print("│")
    print_footer()
    
    print_step(4, "Get best tree")
    best_tree = max(forest, key=lambda x: x.fitness)
    
    print_result("Best tree", best_tree.id)
    print_result("Best fitness", best_tree.fitness)
    print_result("Generation", best_tree.generation)
    print_footer()
    
    print_step(5, "Save forest")
    forest_gen = RSIForestGenerator()
    forest_path = forest_gen.generate_forest(predicate, 10)
    
    print_result("Forest saved", forest_path)
    print_footer()
    
    # ═══════════════════════════════════════════════════════════════
    # SUMMARY
    # ═══════════════════════════════════════════════════════════════
    print_header("RSI SYSTEM SUMMARY")
    
    print("  All 4 levels demonstrated:")
    print()
    print("  Level 1: Auto-Optimization")
    print("    - Tested 7 thresholds")
    print(f"    - Found optimal: {best_threshold} ({best_accuracy:.2%})")
    print()
    print("  Level 2: Auto-Modification")
    print(f"    - Detected {len(gaps['gaps'])} gaps")
    print(f"    - Generated {1 if gaps['gaps'] else 0} new tree")
    print()
    print("  Level 3: Auto-Generation")
    print(f"    - Detected {len(patterns['patterns'])} patterns")
    print(f"    - Generated {len(generated_predicates)} predicates")
    print(f"    - Generated {len(generated_trees)} trees")
    print()
    print("  Level 4: Auto-Evolution (Forest)")
    print(f"    - Created forest with {len(forest)} trees")
    print(f"    - Evolved over 10 generations")
    print(f"    - Best fitness: {best_tree.fitness:.4f}")
    print()
    print("  System is working!")
    print()
    print("═" * 70)


def main():
    """Run complete demo."""
    # Set random seed for reproducibility
    random.seed(42)
    
    run_complete_demo()


if __name__ == "__main__":
    main()
