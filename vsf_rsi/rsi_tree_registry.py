#!/usr/bin/env python3
"""
RSI Tree Registry — Manages generated trees
Tracks, validates, and activates auto-generated trees.

RSI LEVEL 2: AUTO-MODIFICATION
- Register new trees in system
- Validate tree syntax
- Activate/deactivate trees
- Track tree performance
"""

import json
import os
import subprocess
from datetime import datetime, timezone
from typing import Dict, List, Optional
from pathlib import Path

# ── Configuration ────────────────────────────────────────────────────
REGISTRY_DIR = Path(__file__).parent.parent.parent / "state" / "monitoring"
REGISTRY_FILE = REGISTRY_DIR / "rsi_tree_registry.json"
TREES_DIR = Path(__file__).parent.parent.parent.parent / ".opencode" / "plugins" / "support" / "trees"


class RSITreeRegistry:
    """Registry for auto-generated trees."""
    
    def __init__(self):
        """Initialize tree registry."""
        self.registry_dir = REGISTRY_DIR
        self.registry_dir.mkdir(parents=True, exist_ok=True)
        self.trees_dir = TREES_DIR
        
    def register_tree(self, tree_path: str, predicate: str, metadata: Optional[Dict] = None) -> Dict:
        """
        Register a new tree.
        
        Args:
            tree_path: Path to tree file
            predicate: Predicate name
            metadata: Optional metadata
        
        Returns:
            Registration result
        """
        # Validate tree syntax
        validation = self.validate_tree(tree_path)
        
        if not validation["valid"]:
            return {
                "success": False,
                "error": f"Tree validation failed: {validation['error']}",
                "path": tree_path
            }
        
        # Load registry
        registry = self._load_registry()
        
        # Check if tree already exists
        for entry in registry["trees"]:
            if entry["path"] == tree_path:
                return {
                    "success": False,
                    "error": "Tree already registered",
                    "path": tree_path
                }
        
        # Add to registry
        tree_entry = {
            "path": tree_path,
            "predicate": predicate,
            "registered": datetime.now(timezone.utc).isoformat(),
            "status": "active",
            "metadata": metadata or {},
            "validation": validation
        }
        
        registry["trees"].append(tree_entry)
        
        # Save registry
        self._save_registry(registry)
        
        return {
            "success": True,
            "tree": tree_entry
        }
    
    def validate_tree(self, tree_path: str) -> Dict:
        """
        Validate tree syntax.
        
        Args:
            tree_path: Path to tree file
        
        Returns:
            Validation result
        """
        try:
            # Check if file exists
            if not os.path.exists(tree_path):
                return {
                    "valid": False,
                    "error": "File not found"
                }
            
            # Read file
            with open(tree_path, 'r') as f:
                content = f.read()
            
            # Basic VSM validation
            if "⟦" not in content or "⟧" not in content:
                return {
                    "valid": False,
                    "error": "Missing VSM header/footer"
                }
            
            if "@vsm 1.2" not in content:
                return {
                    "valid": False,
                    "error": "Missing @vsm 1.2"
                }
            
            if "@status" not in content:
                return {
                    "valid": False,
                    "error": "Missing @status"
                }
            
            # Check for decision tree
            if "decision(" not in content:
                return {
                    "valid": False,
                    "error": "Missing decision() tree"
                }
            
            # Run VSL parser if available
            parser_path = Path(__file__).parent.parent / "vsl" / "parser" / "vsl_parser.py"
            if parser_path.exists():
                result = subprocess.run(
                    ["python3", str(parser_path), tree_path, "--strict"],
                    capture_output=True,
                    text=True
                )
                
                if result.returncode != 0:
                    return {
                        "valid": False,
                        "error": f"VSL parser error: {result.stderr}"
                    }
            
            return {
                "valid": True,
                "message": "Tree validation passed"
            }
            
        except Exception as e:
            return {
                "valid": False,
                "error": f"Validation error: {str(e)}"
            }
    
    def activate_tree(self, tree_path: str) -> bool:
        """
        Activate a tree.
        
        Args:
            tree_path: Path to tree file
        
        Returns:
            True if successful
        """
        registry = self._load_registry()
        
        for entry in registry["trees"]:
            if entry["path"] == tree_path:
                entry["status"] = "active"
                entry["activated"] = datetime.now(timezone.utc).isoformat()
                self._save_registry(registry)
                return True
        
        return False
    
    def deactivate_tree(self, tree_path: str) -> bool:
        """
        Deactivate a tree.
        
        Args:
            tree_path: Path to tree file
        
        Returns:
            True if successful
        """
        registry = self._load_registry()
        
        for entry in registry["trees"]:
            if entry["path"] == tree_path:
                entry["status"] = "inactive"
                entry["deactivated"] = datetime.now(timezone.utc).isoformat()
                self._save_registry(registry)
                return True
        
        return False
    
    def get_active_trees(self) -> List[Dict]:
        """Get all active trees."""
        registry = self._load_registry()
        return [t for t in registry["trees"] if t["status"] == "active"]
    
    def get_trees_by_predicate(self, predicate: str) -> List[Dict]:
        """Get trees for a predicate."""
        registry = self._load_registry()
        return [t for t in registry["trees"] if t["predicate"] == predicate]
    
    def get_registry_stats(self) -> Dict:
        """Get registry statistics."""
        registry = self._load_registry()
        
        stats = {
            "total_trees": len(registry["trees"]),
            "active_trees": 0,
            "inactive_trees": 0,
            "predicates": {},
            "recent_registrations": []
        }
        
        for tree in registry["trees"]:
            if tree["status"] == "active":
                stats["active_trees"] += 1
            else:
                stats["inactive_trees"] += 1
            
            predicate = tree["predicate"]
            if predicate not in stats["predicates"]:
                stats["predicates"][predicate] = 0
            stats["predicates"][predicate] += 1
        
        # Get recent registrations (last 5)
        stats["recent_registrations"] = sorted(
            registry["trees"],
            key=lambda x: x.get("registered", ""),
            reverse=True
        )[:5]
        
        return stats
    
    def _load_registry(self) -> Dict:
        """Load registry from file."""
        if REGISTRY_FILE.exists():
            with open(REGISTRY_FILE, 'r') as f:
                return json.load(f)
        return {"trees": []}
    
    def _save_registry(self, registry: Dict) -> None:
        """Save registry to file."""
        with open(REGISTRY_FILE, 'w') as f:
            json.dump(registry, f, indent=2)


# ── CLI Interface ────────────────────────────────────────────────────
def main():
    """CLI interface for RSI tree registry."""
    import argparse
    
    parser = argparse.ArgumentParser(description="RSI Tree Registry")
    subparsers = parser.add_subparsers(dest="command")
    
    # Register command
    register_parser = subparsers.add_parser("register", help="Register tree")
    register_parser.add_argument("path", help="Tree path")
    register_parser.add_argument("predicate", help="Predicate name")
    
    # Validate command
    validate_parser = subparsers.add_parser("validate", help="Validate tree")
    validate_parser.add_argument("path", help="Tree path")
    
    # Activate command
    activate_parser = subparsers.add_parser("activate", help="Activate tree")
    activate_parser.add_argument("path", help="Tree path")
    
    # Deactivate command
    deactivate_parser = subparsers.add_parser("deactivate", help="Deactivate tree")
    deactivate_parser.add_argument("path", help="Tree path")
    
    # List command
    subparsers.add_parser("list", help="List active trees")
    
    # Stats command
    subparsers.add_parser("stats", help="Get registry stats")
    
    args = parser.parse_args()
    registry = RSITreeRegistry()
    
    if args.command == "register":
        result = registry.register_tree(args.path, args.predicate)
        if result["success"]:
            print(f"Registered: {args.path}")
        else:
            print(f"Error: {result['error']}")
    elif args.command == "validate":
        result = registry.validate_tree(args.path)
        if result["valid"]:
            print(f"Valid: {result['message']}")
        else:
            print(f"Invalid: {result['error']}")
    elif args.command == "activate":
        if registry.activate_tree(args.path):
            print(f"Activated: {args.path}")
        else:
            print(f"Error: Tree not found")
    elif args.command == "deactivate":
        if registry.deactivate_tree(args.path):
            print(f"Deactivated: {args.path}")
        else:
            print(f"Error: Tree not found")
    elif args.command == "list":
        trees = registry.get_active_trees()
        print(f"Active trees: {len(trees)}")
        for tree in trees:
            print(f"  {tree['predicate']}: {tree['path']}")
    elif args.command == "stats":
        stats = registry.get_registry_stats()
        print(f"Total trees: {stats['total_trees']}")
        print(f"Active trees: {stats['active_trees']}")
        print(f"Inactive trees: {stats['inactive_trees']}")
        print(f"Predicates: {stats['predicates']}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
