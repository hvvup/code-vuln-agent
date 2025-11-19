"""LangChain tool for querying codebase index."""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from langchain.tools import BaseTool
from pydantic import BaseModel, Field


class CodebaseQueryInput(BaseModel):
    """Input for the codebase query tool."""

    query_type: str = Field(
        description="""Type of query to perform. Options:
        - "find_symbol": Find where a symbol is defined
        - "find_callers": Find what calls a specific function
        - "find_callees": Find what a function calls
        - "find_dependencies": Find files that a file depends on
        - "find_dependents": Find files that depend on a specific file
        - "find_imports": Find what files import from a specific file
        - "trace_call_chain": Trace the call chain for a function
        """
    )
    target: str = Field(
        description="Target to search for (symbol name, function name, or file path)"
    )
    index_dir: Optional[str] = Field(
        default="output",
        description="Directory containing index files (default: 'output')",
    )
    max_results: Optional[int] = Field(
        default=20,
        description="Maximum number of results to return (default: 20)",
    )


class CodebaseQueryTool(BaseTool):
    """
    Tool for querying the codebase index built by codebase_indexer.

    This tool allows the agent to ask specific questions about the codebase structure:
    - Where is a symbol defined?
    - What calls this function?
    - What does this function call?
    - What files does this file depend on?
    - What files depend on this file?
    - What imports from this file?
    """

    name: str = "codebase_query"
    description: str = """Query the codebase index for specific information about code structure and relationships.

    IMPORTANT: You must run 'codebase_indexer' first to build the index before using this tool.

    Query Types:
    1. "find_symbol": Find where a symbol/function is defined
       Example: {"query_type": "find_symbol", "target": "authenticateUser"}

    2. "find_callers": Find all places that call a specific function
       Example: {"query_type": "find_callers", "target": "validateInput"}

    3. "find_callees": Find all functions that a specific function calls
       Example: {"query_type": "find_callees", "target": "processRequest"}

    4. "find_dependencies": Find files that a specific file depends on (imports from)
       Example: {"query_type": "find_dependencies", "target": "/path/to/file.js"}

    5. "find_dependents": Find files that depend on a specific file
       Example: {"query_type": "find_dependents", "target": "/path/to/utils.js"}

    6. "find_imports": Find all files that import from a specific file
       Example: {"query_type": "find_imports", "target": "/path/to/module.js"}

    7. "trace_call_chain": Trace the complete call chain for a function (who calls it, recursively)
       Example: {"query_type": "trace_call_chain", "target": "executeQuery"}

    Input:
    - query_type: One of the query types above
    - target: Symbol name, function name, or file path to search for
    - index_dir: Directory with index files (optional, default: "output")
    - max_results: Maximum results to return (optional, default: 20)

    Output:
    - Formatted results showing the requested relationships
    """
    args_schema: type[BaseModel] = CodebaseQueryInput

    def _run(
        self,
        query_type: str,
        target: str,
        index_dir: str = "output",
        max_results: int = 20,
    ) -> str:
        """
        Query the codebase index.

        Args:
            query_type: Type of query to perform
            target: What to search for
            index_dir: Directory containing index files
            max_results: Maximum results to return

        Returns:
            Query results as formatted text
        """
        try:
            # Load index files
            index_path = Path(index_dir)
            if not index_path.exists():
                return f"❌ Error: Index directory not found: {index_dir}\nPlease run 'codebase_indexer' first."

            # Dispatch to appropriate query handler
            query_handlers = {
                "find_symbol": self._find_symbol,
                "find_callers": self._find_callers,
                "find_callees": self._find_callees,
                "find_dependencies": self._find_dependencies,
                "find_dependents": self._find_dependents,
                "find_imports": self._find_imports,
                "trace_call_chain": self._trace_call_chain,
            }

            if query_type not in query_handlers:
                return f"❌ Error: Unknown query type '{query_type}'\nValid types: {', '.join(query_handlers.keys())}"

            handler = query_handlers[query_type]
            return handler(target, index_path, max_results)

        except Exception as e:
            return f"❌ Error during query: {str(e)}\n{type(e).__name__}"

    def _load_index(self, index_path: Path, index_name: str) -> Optional[Dict[str, Any]]:
        """Load an index file."""
        index_file = index_path / f"{index_name}.json"
        if not index_file.exists():
            return None

        with open(index_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def _find_symbol(self, symbol_name: str, index_path: Path, max_results: int) -> str:
        """Find where a symbol is defined."""
        symbol_table = self._load_index(index_path, "symbol_table")
        if not symbol_table:
            return "❌ Error: symbol_table.json not found"

        results = []
        results.append(f"🔍 Finding definitions of symbol: '{symbol_name}'\n")

        # Search in exports
        if symbol_name in symbol_table.get("exports", {}):
            definitions = symbol_table["exports"][symbol_name]
            results.append(f"Found {len(definitions)} definition(s):\n")

            for i, defin in enumerate(definitions[:max_results], 1):
                file_name = Path(defin["file_path"]).name
                results.append(f"{i}. {file_name}:{defin['line']}")
                results.append(f"   Full path: {defin['file_path']}")
                results.append(f"   Type: {defin['export_type']} export")
                if defin.get("is_re_export"):
                    results.append(f"   Re-exported from: {defin.get('original_source', 'unknown')}")
                results.append("")
        else:
            results.append(f"No definitions found for '{symbol_name}'")

        return "\n".join(results)

    def _find_callers(self, function_name: str, index_path: Path, max_results: int) -> str:
        """Find all places that call a function."""
        call_graph = self._load_index(index_path, "call_graph")
        if not call_graph:
            return "❌ Error: call_graph.json not found"

        results = []
        results.append(f"🔍 Finding callers of function: '{function_name}'\n")

        # Find all calls to this function
        callers = [
            call for call in call_graph.get("calls", [])
            if call["callee_name"] == function_name
        ]

        if callers:
            results.append(f"Found {len(callers)} caller(s):\n")

            for i, call in enumerate(callers[:max_results], 1):
                file_name = Path(call["caller_file"]).name
                caller_func = call.get("caller_function") or "<top-level>"

                results.append(f"{i}. Called from {file_name}:{call['caller_line']}")
                results.append(f"   Caller function: {caller_func}")
                results.append(f"   Full path: {call['caller_file']}")

                if call.get("is_resolved"):
                    callee_file = Path(call["callee_file"]).name if call.get("callee_file") else "unknown"
                    results.append(f"   ✅ Resolved to: {callee_file}")
                else:
                    results.append("   ⚠️  Not resolved (may be external or dynamic)")

                results.append("")
        else:
            results.append(f"No callers found for '{function_name}'")

        return "\n".join(results)

    def _find_callees(self, function_name: str, index_path: Path, max_results: int) -> str:
        """Find all functions called by a specific function."""
        call_graph = self._load_index(index_path, "call_graph")
        if not call_graph:
            return "❌ Error: call_graph.json not found"

        results = []
        results.append(f"🔍 Finding functions called by: '{function_name}'\n")

        # Find all calls made by this function
        callees = [
            call for call in call_graph.get("calls", [])
            if call.get("caller_function") == function_name
        ]

        if callees:
            results.append(f"Found {len(callees)} callee(s):\n")

            for i, call in enumerate(callees[:max_results], 1):
                results.append(f"{i}. Calls '{call['callee_name']}'")
                results.append(f"   At line: {call['caller_line']}")

                if call.get("is_resolved"):
                    callee_file = Path(call["callee_file"]).name if call.get("callee_file") else "unknown"
                    results.append(f"   ✅ Defined in: {callee_file}")
                else:
                    results.append("   ⚠️  Not resolved (may be external or dynamic)")

                results.append("")
        else:
            results.append(f"No callees found for '{function_name}'")

        return "\n".join(results)

    def _find_dependencies(self, file_path: str, index_path: Path, max_results: int) -> str:
        """Find files that a specific file depends on."""
        dep_graph = self._load_index(index_path, "dependency_graph")
        if not dep_graph:
            return "❌ Error: dependency_graph.json not found"

        results = []
        file_name = Path(file_path).name
        results.append(f"🔍 Finding dependencies of: {file_name}\n")

        # Find dependencies
        dependencies = [
            dep for dep in dep_graph.get("dependencies", [])
            if file_path in dep["source_file"] or file_name in dep["source_file"]
        ]

        if dependencies:
            results.append(f"Found {len(dependencies)} dependenc(ies):\n")

            for i, dep in enumerate(dependencies[:max_results], 1):
                target_name = Path(dep["target_file"]).name
                results.append(f"{i}. Imports from: {target_name}")
                results.append(f"   Full path: {dep['target_file']}")
                results.append(f"   Symbols: {', '.join(dep['imported_symbols'][:5])}")
                if len(dep["imported_symbols"]) > 5:
                    results.append(f"   ... and {len(dep['imported_symbols']) - 5} more")
                results.append(f"   At line: {dep['line']}")
                results.append("")
        else:
            results.append(f"No dependencies found for '{file_name}'")

        return "\n".join(results)

    def _find_dependents(self, file_path: str, index_path: Path, max_results: int) -> str:
        """Find files that depend on a specific file."""
        dep_graph = self._load_index(index_path, "dependency_graph")
        if not dep_graph:
            return "❌ Error: dependency_graph.json not found"

        results = []
        file_name = Path(file_path).name
        results.append(f"🔍 Finding dependents of: {file_name}\n")

        # Find dependents
        dependents = [
            dep for dep in dep_graph.get("dependencies", [])
            if file_path in dep["target_file"] or file_name in dep["target_file"]
        ]

        if dependents:
            results.append(f"Found {len(dependents)} dependent(s):\n")

            for i, dep in enumerate(dependents[:max_results], 1):
                source_name = Path(dep["source_file"]).name
                results.append(f"{i}. Imported by: {source_name}")
                results.append(f"   Full path: {dep['source_file']}")
                results.append(f"   Symbols: {', '.join(dep['imported_symbols'][:5])}")
                if len(dep["imported_symbols"]) > 5:
                    results.append(f"   ... and {len(dep['imported_symbols']) - 5} more")
                results.append(f"   At line: {dep['line']}")
                results.append("")
        else:
            results.append(f"No dependents found for '{file_name}'")

        return "\n".join(results)

    def _find_imports(self, file_path: str, index_path: Path, max_results: int) -> str:
        """Find all files that import from a specific file (alias for find_dependents)."""
        return self._find_dependents(file_path, index_path, max_results)

    def _trace_call_chain(self, function_name: str, index_path: Path, max_results: int) -> str:
        """Trace the complete call chain for a function."""
        call_graph = self._load_index(index_path, "call_graph")
        if not call_graph:
            return "❌ Error: call_graph.json not found"

        results = []
        results.append(f"🔍 Tracing call chain for: '{function_name}'\n")

        # Build call chain recursively
        visited = set()
        chain = []

        def trace_recursive(func_name: str, level: int = 0):
            if func_name in visited or level > 10:  # Prevent infinite loops
                return

            visited.add(func_name)
            indent = "  " * level

            # Find callers
            callers = [
                call for call in call_graph.get("calls", [])
                if call["callee_name"] == func_name
            ]

            if callers:
                for call in callers[:5]:  # Limit to 5 per level
                    caller_func = call.get("caller_function") or "<top-level>"
                    file_name = Path(call["caller_file"]).name

                    chain.append(f"{indent}← Called by: {caller_func} ({file_name}:{call['caller_line']})")

                    if call.get("caller_function"):
                        trace_recursive(call["caller_function"], level + 1)

        trace_recursive(function_name)

        if chain:
            results.append(f"Call chain (showing up to {max_results} levels):\n")
            results.append(f"🎯 {function_name}")
            results.extend(chain[:max_results])
        else:
            results.append(f"No callers found for '{function_name}'")

        return "\n".join(results)

    async def _arun(
        self,
        query_type: str,
        target: str,
        index_dir: str = "output",
        max_results: int = 20,
    ) -> str:
        """Async version - not implemented yet."""
        raise NotImplementedError("Async execution not supported yet")
