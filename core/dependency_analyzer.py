"""Analyze module dependencies and detect circular dependencies."""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from collections import defaultdict, deque

from .module_resolver import SymbolTable


@dataclass
class FileDependency:
    """Represents a dependency between two files."""

    source_file: str  # File that depends on another
    target_file: str  # File being depended on
    imported_symbols: List[str]  # What is imported
    line: int  # Line number of import


@dataclass
class DependencyGraph:
    """Complete dependency graph for a codebase."""

    dependencies: List[FileDependency] = field(default_factory=list)
    files: Set[str] = field(default_factory=set)
    _adjacency_list: Dict[str, List[str]] = field(default_factory=lambda: defaultdict(list))
    _reverse_adjacency: Dict[str, List[str]] = field(default_factory=lambda: defaultdict(list))

    def add_dependency(self, dep: FileDependency):
        """Add a dependency to the graph."""
        self.dependencies.append(dep)
        self.files.add(dep.source_file)
        self.files.add(dep.target_file)
        self._adjacency_list[dep.source_file].append(dep.target_file)
        self._reverse_adjacency[dep.target_file].append(dep.source_file)

    def get_dependencies(self, file_path: str) -> List[str]:
        """Get all files that this file depends on."""
        return list(set(self._adjacency_list.get(file_path, [])))

    def get_dependents(self, file_path: str) -> List[str]:
        """Get all files that depend on this file."""
        return list(set(self._reverse_adjacency.get(file_path, [])))

    def has_circular_dependencies(self) -> bool:
        """Check if the graph has any circular dependencies."""
        cycles = self.find_cycles()
        return len(cycles) > 0

    def find_cycles(self) -> List[List[str]]:
        """Find all circular dependencies in the graph."""
        cycles = []
        visited = set()
        rec_stack = set()

        def dfs(node: str, path: List[str]):
            """Depth-first search to detect cycles."""
            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            for neighbor in self._adjacency_list.get(node, []):
                if neighbor not in visited:
                    dfs(neighbor, path.copy())
                elif neighbor in rec_stack:
                    # Found a cycle
                    cycle_start = path.index(neighbor)
                    cycle = path[cycle_start:] + [neighbor]
                    cycles.append(cycle)

            rec_stack.remove(node)

        for file in self.files:
            if file not in visited:
                dfs(file, [])

        return cycles

    def calculate_levels(self) -> Dict[str, int]:
        """
        Calculate dependency levels for all files.
        Level 0 = no dependencies, Level N = depends on files at level N-1
        """
        levels = {}
        in_degree = defaultdict(int)

        # Calculate in-degree for each file
        for file in self.files:
            in_degree[file] = len(self.get_dependencies(file))

        # BFS to assign levels
        queue = deque([f for f in self.files if in_degree[f] == 0])
        current_level = 0

        while queue:
            level_size = len(queue)
            for _ in range(level_size):
                file = queue.popleft()
                levels[file] = current_level

                # Reduce in-degree for dependents
                for dependent in self.get_dependents(file):
                    in_degree[dependent] -= 1
                    if in_degree[dependent] == 0:
                        queue.append(dependent)

            current_level += 1

        # Handle remaining files (part of cycles)
        for file in self.files:
            if file not in levels:
                levels[file] = -1  # Mark as part of a cycle

        return levels

    def get_core_files(self, top_n: int = 10) -> List[Tuple[str, int]]:
        """
        Get the most important "core" files based on number of dependents.

        Args:
            top_n: Number of top files to return

        Returns:
            List of (file_path, num_dependents) tuples
        """
        dependent_counts = [
            (file, len(self.get_dependents(file))) for file in self.files
        ]
        dependent_counts.sort(key=lambda x: x[1], reverse=True)
        return dependent_counts[:top_n]

    def get_leaf_files(self) -> List[str]:
        """Get files that don't have any dependents (leaf nodes)."""
        return [file for file in self.files if len(self.get_dependents(file)) == 0]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        levels = self.calculate_levels()
        cycles = self.find_cycles()
        core_files = self.get_core_files(10)

        return {
            "dependencies": [
                {
                    "source_file": dep.source_file,
                    "target_file": dep.target_file,
                    "imported_symbols": dep.imported_symbols,
                    "line": dep.line,
                }
                for dep in self.dependencies
            ],
            "files": list(self.files),
            "stats": {
                "total_files": len(self.files),
                "total_dependencies": len(self.dependencies),
                "has_cycles": len(cycles) > 0,
                "num_cycles": len(cycles),
                "leaf_files": len(self.get_leaf_files()),
            },
            "levels": levels,
            "cycles": [[str(Path(f).name) for f in cycle] for cycle in cycles],
            "core_files": [
                {"file": str(Path(file).name), "full_path": file, "dependents": count}
                for file, count in core_files
            ],
        }


class DependencyAnalyzer:
    """Analyze module dependencies in a JavaScript codebase."""

    def __init__(self, root_path: str, symbol_table: Optional[SymbolTable] = None):
        """
        Initialize the dependency analyzer.

        Args:
            root_path: Root directory of the project
            symbol_table: Pre-built symbol table (optional)
        """
        self.root_path = Path(root_path).resolve()
        self.symbol_table = symbol_table
        self.dependency_graph = DependencyGraph()

    def analyze(self) -> DependencyGraph:
        """
        Analyze dependencies for the entire repository.

        Returns:
            Complete dependency graph
        """
        if self.symbol_table is None:
            from .module_resolver import ModuleResolver
            print("📊 Building symbol table...")
            resolver = ModuleResolver(str(self.root_path))
            self.symbol_table = resolver.resolve_repository()

        print("🔗 Building dependency graph...")

        # Build dependency graph from imports
        for import_info in self.symbol_table.imports:
            if import_info.resolved_path:
                dep = FileDependency(
                    source_file=import_info.source_file,
                    target_file=import_info.resolved_path,
                    imported_symbols=import_info.imported_symbols,
                    line=import_info.source_line,
                )
                self.dependency_graph.add_dependency(dep)

        # Analyze for cycles
        print("🔍 Checking for circular dependencies...")
        cycles = self.dependency_graph.find_cycles()
        if cycles:
            print(f"⚠️  Found {len(cycles)} circular dependencies!")
            for i, cycle in enumerate(cycles[:5], 1):  # Show first 5
                cycle_names = [str(Path(f).name) for f in cycle]
                print(f"   Cycle {i}: {' → '.join(cycle_names)}")
        else:
            print("✅ No circular dependencies found")

        # Calculate levels
        print("📊 Calculating dependency levels...")
        levels = self.dependency_graph.calculate_levels()
        max_level = max(levels.values()) if levels else 0
        print(f"   Max dependency level: {max_level}")

        # Find core files
        print("🎯 Identifying core files...")
        core_files = self.dependency_graph.get_core_files(5)
        for file, count in core_files:
            file_name = Path(file).name
            print(f"   {file_name}: {count} dependents")

        return self.dependency_graph

    def save_dependency_graph(self, output_path: str):
        """Save the dependency graph to a JSON file."""
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(self.dependency_graph.to_dict(), f, indent=2)
        print(f"✅ Dependency graph saved to {output_path}")

    def generate_summary(self) -> str:
        """Generate a human-readable summary of the dependency analysis."""
        levels = self.dependency_graph.calculate_levels()
        cycles = self.dependency_graph.find_cycles()
        core_files = self.dependency_graph.get_core_files(10)
        leaf_files = self.dependency_graph.get_leaf_files()

        summary = []
        summary.append("=" * 80)
        summary.append("DEPENDENCY ANALYSIS SUMMARY")
        summary.append("=" * 80)
        summary.append("")

        # Basic stats
        summary.append(f"Total Files: {len(self.dependency_graph.files)}")
        summary.append(f"Total Dependencies: {len(self.dependency_graph.dependencies)}")
        summary.append(f"Leaf Files (no dependents): {len(leaf_files)}")
        summary.append("")

        # Circular dependencies
        if cycles:
            summary.append(f"⚠️  CIRCULAR DEPENDENCIES DETECTED: {len(cycles)}")
            for i, cycle in enumerate(cycles[:5], 1):
                cycle_names = [str(Path(f).name) for f in cycle]
                summary.append(f"   Cycle {i}: {' → '.join(cycle_names)}")
            if len(cycles) > 5:
                summary.append(f"   ... and {len(cycles) - 5} more cycles")
            summary.append("")
        else:
            summary.append("✅ No circular dependencies")
            summary.append("")

        # Dependency levels
        max_level = max(levels.values()) if levels else 0
        summary.append(f"Dependency Depth: {max_level} levels")
        level_counts = defaultdict(int)
        for level in levels.values():
            if level >= 0:
                level_counts[level] += 1
        for level in sorted(level_counts.keys()):
            summary.append(f"   Level {level}: {level_counts[level]} files")
        summary.append("")

        # Core files
        summary.append("Top 10 Core Files (most dependents):")
        for file, count in core_files:
            file_name = Path(file).name
            summary.append(f"   {file_name}: {count} dependents")
        summary.append("")

        summary.append("=" * 80)

        return "\n".join(summary)
