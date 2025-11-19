"""LangChain tool for building codebase-wide context index."""

import json
from pathlib import Path
from typing import Optional

from langchain.tools import BaseTool
from pydantic import BaseModel, Field

from core.module_resolver import ModuleResolver
from core.call_graph_builder import CallGraphBuilder
from core.dependency_analyzer import DependencyAnalyzer


class CodebaseIndexerInput(BaseModel):
    """Input for the codebase indexer tool."""

    repository_path: str = Field(
        description="Absolute path to the repository root directory to analyze"
    )
    output_dir: Optional[str] = Field(
        default="output",
        description="Directory to save index files (default: 'output')",
    )
    extensions: Optional[str] = Field(
        default=".js,.jsx,.ts,.tsx",
        description="Comma-separated file extensions to analyze (default: .js,.jsx,.ts,.tsx)",
    )


class CodebaseIndexerTool(BaseTool):
    """
    Tool for building a comprehensive codebase index.

    This tool analyzes an entire JavaScript/TypeScript repository and builds:
    1. Symbol table (imports/exports)
    2. Call graph (function calls across files)
    3. Dependency graph (module dependencies)

    The index is saved to files and a summary is returned to the agent.
    """

    name: str = "codebase_indexer"
    description: str = """Build a comprehensive index of a JavaScript/TypeScript codebase.

    Use this tool at the START of repository analysis to understand the codebase structure.

    Input:
    - repository_path: Absolute path to the repository root
    - output_dir: Where to save index files (optional, default: "output")
    - extensions: File extensions to analyze (optional, default: ".js,.jsx,.ts,.tsx")

    Output:
    - Summary of the codebase structure
    - File paths where detailed indexes are saved:
      * symbol_table.json: All imports/exports
      * call_graph.json: Function call relationships
      * dependency_graph.json: Module dependencies

    The agent can then use codebase_query tool to query specific information from these indexes.

    Example usage:
    {
        "repository_path": "/path/to/repo",
        "output_dir": "output",
        "extensions": ".js,.jsx,.ts,.tsx"
    }
    """
    args_schema: type[BaseModel] = CodebaseIndexerInput

    def _run(
        self,
        repository_path: str,
        output_dir: str = "output",
        extensions: str = ".js,.jsx,.ts,.tsx",
    ) -> str:
        """
        Build the codebase index.

        Args:
            repository_path: Path to repository root
            output_dir: Output directory for index files
            extensions: Comma-separated file extensions

        Returns:
            Summary of the indexing results
        """
        try:
            # Validate repository path
            repo_path = Path(repository_path).resolve()
            if not repo_path.exists():
                return f"❌ Error: Repository path does not exist: {repository_path}"
            if not repo_path.is_dir():
                return f"❌ Error: Path is not a directory: {repository_path}"

            # Create output directory
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)

            # Parse extensions
            ext_list = [ext.strip() for ext in extensions.split(",")]
            if not all(ext.startswith(".") for ext in ext_list):
                return f"❌ Error: Extensions must start with '.': {extensions}"

            print(f"\n{'=' * 80}")
            print(f"BUILDING CODEBASE INDEX: {repo_path.name}")
            print(f"{'=' * 80}\n")

            # Step 1: Build symbol table (imports/exports)
            print("📊 Step 1/3: Analyzing imports and exports...")
            resolver = ModuleResolver(str(repo_path))
            symbol_table = resolver.resolve_repository(ext_list)

            symbol_table_path = output_path / "symbol_table.json"
            resolver.save_symbol_table(str(symbol_table_path))

            # Step 2: Build call graph
            print("\n📊 Step 2/3: Building call graph...")
            call_graph_builder = CallGraphBuilder(str(repo_path), symbol_table)
            call_graph = call_graph_builder.build(ext_list)

            call_graph_path = output_path / "call_graph.json"
            call_graph_builder.save_call_graph(str(call_graph_path))

            # Step 3: Build dependency graph
            print("\n📊 Step 3/3: Analyzing dependencies...")
            dep_analyzer = DependencyAnalyzer(str(repo_path), symbol_table)
            dep_graph = dep_analyzer.analyze()

            dep_graph_path = output_path / "dependency_graph.json"
            dep_analyzer.save_dependency_graph(str(dep_graph_path))

            # Generate summary
            print(f"\n{'=' * 80}")
            print("INDEXING COMPLETE")
            print(f"{'=' * 80}\n")

            summary_text = self._generate_summary(
                symbol_table, call_graph, dep_graph, repo_path, output_path
            )

            return summary_text

        except Exception as e:
            return f"❌ Error during codebase indexing: {str(e)}\n{type(e).__name__}"

    def _generate_summary(
        self, symbol_table, call_graph, dep_graph, repo_path, output_path
    ) -> str:
        """Generate a human-readable summary of the indexing results."""
        summary = []

        summary.append("=" * 80)
        summary.append(f"CODEBASE INDEX SUMMARY: {repo_path.name}")
        summary.append("=" * 80)
        summary.append("")

        # File statistics
        summary.append(f"📁 Total Files Analyzed: {len(symbol_table.files)}")
        summary.append("")

        # Symbol table stats
        summary.append("📦 SYMBOL TABLE:")
        summary.append(f"   - Total Exported Symbols: {len(symbol_table.exports)}")
        summary.append(f"   - Total Import Statements: {len(symbol_table.imports)}")
        resolved_imports = sum(
            1 for imp in symbol_table.imports if imp.resolved_path is not None
        )
        summary.append(f"   - Resolved Imports: {resolved_imports}/{len(symbol_table.imports)}")
        summary.append("")

        # Call graph stats
        cg_stats = call_graph.to_dict()["stats"]
        summary.append("🔗 CALL GRAPH:")
        summary.append(f"   - Total Functions: {cg_stats['total_functions']}")
        summary.append(f"   - Total Function Calls: {cg_stats['total_calls']}")
        summary.append(
            f"   - Resolved Calls: {cg_stats['resolved_calls']}/{cg_stats['total_calls']}"
        )
        if cg_stats['total_calls'] > 0:
            resolve_rate = (cg_stats['resolved_calls'] / cg_stats['total_calls']) * 100
            summary.append(f"   - Resolution Rate: {resolve_rate:.1f}%")
        summary.append("")

        # Dependency graph stats
        dg_dict = dep_graph.to_dict()
        dg_stats = dg_dict["stats"]
        summary.append("🌐 DEPENDENCY GRAPH:")
        summary.append(f"   - Total Dependencies: {dg_stats['total_dependencies']}")
        summary.append(f"   - Leaf Files (no dependents): {dg_stats['leaf_files']}")

        if dg_stats["has_cycles"]:
            summary.append(f"   - ⚠️  Circular Dependencies: {dg_stats['num_cycles']} cycles found")
            for i, cycle in enumerate(dg_dict["cycles"][:3], 1):
                summary.append(f"      Cycle {i}: {' → '.join(cycle)}")
        else:
            summary.append("   - ✅ No Circular Dependencies")
        summary.append("")

        # Core files
        summary.append("🎯 TOP 5 CORE FILES (most dependents):")
        for i, core_file in enumerate(dg_dict["core_files"][:5], 1):
            summary.append(f"   {i}. {core_file['file']}: {core_file['dependents']} dependents")
        summary.append("")

        # Output files
        summary.append("💾 INDEX FILES SAVED TO:")
        summary.append(f"   - {output_path / 'symbol_table.json'}")
        summary.append(f"   - {output_path / 'call_graph.json'}")
        summary.append(f"   - {output_path / 'dependency_graph.json'}")
        summary.append("")

        summary.append("=" * 80)
        summary.append("")
        summary.append("💡 Next Steps:")
        summary.append("   Use the 'codebase_query' tool to query specific information:")
        summary.append("   - Find what imports a symbol")
        summary.append("   - Find what calls a function")
        summary.append("   - Find dependencies of a file")
        summary.append("   - Trace data flow across files")
        summary.append("")

        return "\n".join(summary)

    async def _arun(
        self,
        repository_path: str,
        output_dir: str = "output",
        extensions: str = ".js,.jsx,.ts,.tsx",
    ) -> str:
        """Async version - not implemented yet."""
        raise NotImplementedError("Async execution not supported yet")
