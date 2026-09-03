#!/usr/bin/env python3
"""
RSI Component Registry — Manages all generated components
Tracks predicates, trees, and other auto-generated components.

RSI LEVEL 3: AUTO-GENERATION
- Register all generated components
- Validate component syntax
- Activate/deactivate components
- Track component performance
"""

import json
import os
import subprocess
from datetime import datetime, timezone
from typing import Dict, List, Optional
from pathlib import Path

# ── Configuration ────────────────────────────────────────────────────
REGISTRY_DIR = Path(__file__).parent.parent.parent / "state" / "monitoring"
REGISTRY_FILE = REGISTRY_DIR / "rsi_component_registry.json"


class RSIComponentRegistry:
    """Registry for all auto-generated components."""
    
    def __init__(self):
        """Initialize component registry."""
        self.registry_dir = REGISTRY_DIR
        self.registry_dir.mkdir(parents=True, exist_ok=True)
        
    def register_component(self, component_type: str, component_path: str, name: str, metadata: Optional[Dict] = None) -> Dict:
        """
        Register a new component.
        
        Args:
            component_type: Type of component (predicate, tree, etc.)
            component_path: Path to component file
            name: Component name
            metadata: Optional metadata
        
        Returns:
            Registration result
        """
        # Validate component syntax
        validation = self.validate_component(component_type, component_path)
        
        if not validation["valid"]:
            return {
                "success": False,
                "error": f"Component validation failed: {validation['error']}",
                "path": component_path
            }
        
        # Load registry
        registry = self._load_registry()
        
        # Check if component already exists
        for entry in registry["components"]:
            if entry["path"] == component_path:
                return {
                    "success": False,
                    "error": "Component already registered",
                    "path": component_path
                }
        
        # Add to registry
        component_entry = {
            "type": component_type,
            "path": component_path,
            "name": name,
            "registered": datetime.now(timezone.utc).isoformat(),
            "status": "active",
            "metadata": metadata or {},
            "validation": validation
        }
        
        registry["components"].append(component_entry)
        
        # Save registry
        self._save_registry(registry)
        
        return {
            "success": True,
            "component": component_entry
        }
    
    def validate_component(self, component_type: str, component_path: str) -> Dict:
        """
        Validate component syntax.
        
        Args:
            component_type: Type of component
            component_path: Path to component file
        
        Returns:
            Validation result
        """
        try:
            # Check if file exists
            if not os.path.exists(component_path):
                return {
                    "valid": False,
                    "error": "File not found"
                }
            
            # Read file
            with open(component_path, 'r') as f:
                content = f.read()
            
            if component_type == "predicate":
                return self._validate_predicate(content)
            elif component_type == "tree":
                return self._validate_tree(content)
            else:
                return {
                    "valid": True,
                    "message": "Unknown component type, skipping validation"
                }
            
        except Exception as e:
            return {
                "valid": False,
                "error": f"Validation error: {str(e)}"
            }
    
    def _validate_predicate(self, content: str) -> Dict:
        """Validate predicate syntax."""
        # Check for function definition
        if "def " not in content:
            return {
                "valid": False,
                "error": "Missing function definition"
            }
        
        # Check for return statement
        if "return " not in content:
            return {
                "valid": False,
                "error": "Missing return statement"
            }
        
        # Check for PREDICATE registration
        if "PREDICATE" not in content:
            return {
                "valid": False,
                "error": "Missing PREDICATE registration"
            }
        
        return {
            "valid": True,
            "message": "Predicate validation passed"
        }
    
    def _validate_tree(self, content: str) -> Dict:
        """Validate tree syntax."""
        # Check for VSM header/footer
        if "⟦" not in content or "⟧" not in content:
            return {
                "valid": False,
                "error": "Missing VSM header/footer"
            }
        
        # Check for @vsm 1.2
        if "@vsm 1.2" not in content:
            return {
                "valid": False,
                "error": "Missing @vsm 1.2"
            }
        
        # Check for @status
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
        
        return {
            "valid": True,
            "message": "Tree validation passed"
        }
    
    def activate_component(self, component_path: str) -> bool:
        """
        Activate a component.
        
        Args:
            component_path: Path to component file
        
        Returns:
            True if successful
        """
        registry = self._load_registry()
        
        for entry in registry["components"]:
            if entry["path"] == component_path:
                entry["status"] = "active"
                entry["activated"] = datetime.now(timezone.utc).isoformat()
                self._save_registry(registry)
                return True
        
        return False
    
    def deactivate_component(self, component_path: str) -> bool:
        """
        Deactivate a component.
        
        Args:
            component_path: Path to component file
        
        Returns:
            True if successful
        """
        registry = self._load_registry()
        
        for entry in registry["components"]:
            if entry["path"] == component_path:
                entry["status"] = "inactive"
                entry["deactivated"] = datetime.now(timezone.utc).isoformat()
                self._save_registry(registry)
                return True
        
        return False
    
    def get_active_components(self, component_type: Optional[str] = None) -> List[Dict]:
        """Get all active components (optionally filtered by type)."""
        registry = self._load_registry()
        
        if component_type:
            return [c for c in registry["components"] if c["status"] == "active" and c["type"] == component_type]
        else:
            return [c for c in registry["components"] if c["status"] == "active"]
    
    def get_components_by_name(self, name: str) -> List[Dict]:
        """Get components by name."""
        registry = self._load_registry()
        return [c for c in registry["components"] if c["name"] == name]
    
    def get_registry_stats(self) -> Dict:
        """Get registry statistics."""
        registry = self._load_registry()
        
        stats = {
            "total_components": len(registry["components"]),
            "active_components": 0,
            "inactive_components": 0,
            "by_type": {},
            "recent_registrations": []
        }
        
        for component in registry["components"]:
            if component["status"] == "active":
                stats["active_components"] += 1
            else:
                stats["inactive_components"] += 1
            
            comp_type = component["type"]
            if comp_type not in stats["by_type"]:
                stats["by_type"][comp_type] = 0
            stats["by_type"][comp_type] += 1
        
        # Get recent registrations (last 5)
        stats["recent_registrations"] = sorted(
            registry["components"],
            key=lambda x: x.get("registered", ""),
            reverse=True
        )[:5]
        
        return stats
    
    def _load_registry(self) -> Dict:
        """Load registry from file."""
        if REGISTRY_FILE.exists():
            try:
                with open(REGISTRY_FILE, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                return {"components": []}
        return {"components": []}
    
    def _save_registry(self, registry: Dict) -> None:
        """Save registry to file."""
        with open(REGISTRY_FILE, 'w') as f:
            json.dump(registry, f, indent=2)


# ── CLI Interface ────────────────────────────────────────────────────
def main():
    """CLI interface for RSI component registry."""
    import argparse
    
    parser = argparse.ArgumentParser(description="RSI Component Registry")
    subparsers = parser.add_subparsers(dest="command")
    
    # Register command
    register_parser = subparsers.add_parser("register", help="Register component")
    register_parser.add_argument("type", choices=["predicate", "tree"], help="Component type")
    register_parser.add_argument("path", help="Component path")
    register_parser.add_argument("name", help="Component name")
    
    # Validate command
    validate_parser = subparsers.add_parser("validate", help="Validate component")
    validate_parser.add_argument("type", choices=["predicate", "tree"], help="Component type")
    validate_parser.add_argument("path", help="Component path")
    
    # Activate command
    activate_parser = subparsers.add_parser("activate", help="Activate component")
    activate_parser.add_argument("path", help="Component path")
    
    # Deactivate command
    deactivate_parser = subparsers.add_parser("deactivate", help="Deactivate component")
    deactivate_parser.add_argument("path", help="Component path")
    
    # List command
    list_parser = subparsers.add_parser("list", help="List active components")
    list_parser.add_argument("--type", choices=["predicate", "tree"], help="Component type")
    
    # Stats command
    subparsers.add_parser("stats", help="Get registry stats")
    
    args = parser.parse_args()
    registry = RSIComponentRegistry()
    
    if args.command == "register":
        result = registry.register_component(args.type, args.path, args.name)
        if result["success"]:
            print(f"Registered: {args.path}")
        else:
            print(f"Error: {result['error']}")
    elif args.command == "validate":
        result = registry.validate_component(args.type, args.path)
        if result["valid"]:
            print(f"Valid: {result['message']}")
        else:
            print(f"Invalid: {result['error']}")
    elif args.command == "activate":
        if registry.activate_component(args.path):
            print(f"Activated: {args.path}")
        else:
            print(f"Error: Component not found")
    elif args.command == "deactivate":
        if registry.deactivate_component(args.path):
            print(f"Deactivated: {args.path}")
        else:
            print(f"Error: Component not found")
    elif args.command == "list":
        components = registry.get_active_components(args.type)
        print(f"Active components: {len(components)}")
        for component in components:
            print(f"  {component['name']}: {component['path']}")
    elif args.command == "stats":
        stats = registry.get_registry_stats()
        print(f"Total components: {stats['total_components']}")
        print(f"Active components: {stats['active_components']}")
        print(f"Inactive components: {stats['inactive_components']}")
        print(f"By type: {stats['by_type']}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
