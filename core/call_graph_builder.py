"""Build call graphs across JavaScript files using module resolution."""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
import esprima

from .module_resolver import ModuleResolver, SymbolTable


@dataclass
class FunctionDefinition:
    """Information about a function definition."""

    name: str  # Function name
    file_path: str  # File containing the function
    line: int  # Line number where defined
    params: List[str]  # Parameter names
    is_async: bool = False
    is_exported: bool = False


@dataclass
class FunctionCall:
    """Information about a function call."""

    caller_file: str  # File making the call
    caller_function: Optional[str]  # Function making the call (None if top-level)
    caller_line: int  # Line number of the call
    callee_name: str  # Name of the called function
    callee_file: Optional[str] = None  # Resolved file (if found)
    callee_function: Optional[str] = None  # Resolved function (if found)
    is_resolved: bool = False  # Whether we found the definition


@dataclass
class CallGraph:
    """Complete call graph for a codebase."""

    functions: Dict[str, List[FunctionDefinition]] = field(default_factory=dict)
    calls: List[FunctionCall] = field(default_factory=list)
    files: Set[str] = field(default_factory=set)

    def add_function(self, func_def: FunctionDefinition):
        """Add a function definition to the graph."""
        if func_def.name not in self.functions:
            self.functions[func_def.name] = []
        self.functions[func_def.name].append(func_def)
        self.files.add(func_def.file_path)

    def add_call(self, call: FunctionCall):
        """Add a function call to the graph."""
        self.calls.append(call)
        self.files.add(call.caller_file)

    def get_function_definitions(self, name: str) -> List[FunctionDefinition]:
        """Get all definitions of a function by name."""
        return self.functions.get(name, [])

    def get_callers(self, function_name: str, file_path: Optional[str] = None) -> List[FunctionCall]:
        """Get all calls to a specific function."""
        callers = []
        for call in self.calls:
            if call.callee_name == function_name:
                if file_path is None or call.callee_file == file_path:
                    callers.append(call)
        return callers

    def get_callees(self, caller_function: str, caller_file: str) -> List[FunctionCall]:
        """Get all functions called by a specific function."""
        callees = []
        for call in self.calls:
            if call.caller_function == caller_function and call.caller_file == caller_file:
                callees.append(call)
        return callees

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "functions": {
                name: [
                    {
                        "name": func.name,
                        "file_path": func.file_path,
                        "line": func.line,
                        "params": func.params,
                        "is_async": func.is_async,
                        "is_exported": func.is_exported,
                    }
                    for func in funcs
                ]
                for name, funcs in self.functions.items()
            },
            "calls": [
                {
                    "caller_file": call.caller_file,
                    "caller_function": call.caller_function,
                    "caller_line": call.caller_line,
                    "callee_name": call.callee_name,
                    "callee_file": call.callee_file,
                    "callee_function": call.callee_function,
                    "is_resolved": call.is_resolved,
                }
                for call in self.calls
            ],
            "files": list(self.files),
            "stats": {
                "total_functions": sum(len(funcs) for funcs in self.functions.values()),
                "total_calls": len(self.calls),
                "resolved_calls": sum(1 for call in self.calls if call.is_resolved),
                "total_files": len(self.files),
            },
        }


class CallGraphBuilder:
    """Build call graphs from JavaScript codebases."""

    def __init__(self, root_path: str, symbol_table: Optional[SymbolTable] = None):
        """
        Initialize the call graph builder.

        Args:
            root_path: Root directory of the project
            symbol_table: Pre-built symbol table (optional, will build if not provided)
        """
        self.root_path = Path(root_path).resolve()
        self.symbol_table = symbol_table
        self.call_graph = CallGraph()
        self._file_cache: Dict[str, Dict[str, Any]] = {}
        self._import_map: Dict[str, Dict[str, str]] = {}  # file -> {symbol -> source_file}

    def build(self, extensions: Optional[List[str]] = None) -> CallGraph:
        """
        Build the call graph for the entire repository.

        Args:
            extensions: File extensions to process (default: [".js", ".jsx", ".ts", ".tsx"])

        Returns:
            Complete call graph
        """
        if extensions is None:
            extensions = [".js", ".jsx", ".ts", ".tsx"]

        # Build symbol table if not provided
        if self.symbol_table is None:
            print("📊 Building symbol table...")
            resolver = ModuleResolver(str(self.root_path))
            self.symbol_table = resolver.resolve_repository(extensions)

        # Build import map from symbol table
        print("🔗 Building import map...")
        self._build_import_map()

        # Find all JavaScript files
        js_files = []
        for ext in extensions:
            js_files.extend(self.root_path.rglob(f"*{ext}"))

        # Skip node_modules and build directories
        js_files = [
            f for f in js_files
            if "node_modules" not in f.parts
            and "dist" not in f.parts
            and "build" not in f.parts
            and ".next" not in f.parts
        ]

        print(f"🔍 Analyzing {len(js_files)} files for call graph...")

        # Extract function definitions and calls
        for file_path in js_files:
            try:
                self._process_file(file_path)
            except Exception as e:
                print(f"⚠️  Warning: Failed to process {file_path.name}: {e}")

        # Resolve function calls
        print("🔍 Resolving function calls...")
        self._resolve_calls()

        return self.call_graph

    def _build_import_map(self):
        """Build a map of imported symbols for each file."""
        for import_info in self.symbol_table.imports:
            file_path = import_info.source_file

            if file_path not in self._import_map:
                self._import_map[file_path] = {}

            # Map imported symbols to their source file
            for symbol in import_info.imported_symbols:
                if import_info.resolved_path:
                    self._import_map[file_path][symbol] = import_info.resolved_path

    def _process_file(self, file_path: Path):
        """Extract function definitions and calls from a file."""
        ast = self._parse_file(file_path)
        if not ast:
            return

        file_str = str(file_path.resolve())

        # Walk AST to find functions and calls
        self._extract_functions(ast, file_str)
        self._extract_calls(ast, file_str)

    def _extract_functions(self, ast: Dict[str, Any], file_path: str):
        """Extract all function definitions from an AST."""
        for node in self._walk_ast(ast):
            func_def = self._get_function_definition(node, file_path)
            if func_def:
                self.call_graph.add_function(func_def)

    def _extract_calls(self, ast: Dict[str, Any], file_path: str):
        """Extract all function calls from an AST."""
        current_function = None

        def walk_with_context(node: Any, parent_func: Optional[str] = None):
            """Walk AST while tracking current function context."""
            if isinstance(node, dict):
                # Track current function
                func_def = self._get_function_definition(node, file_path)
                if func_def:
                    parent_func = func_def.name

                # Extract calls
                if node.get("type") == "CallExpression":
                    call = self._get_function_call(node, file_path, parent_func)
                    if call:
                        self.call_graph.add_call(call)

                # Recurse
                for value in node.values():
                    walk_with_context(value, parent_func)

            elif isinstance(node, list):
                for item in node:
                    walk_with_context(item, parent_func)

        walk_with_context(ast)

    def _get_function_definition(self, node: Dict[str, Any], file_path: str) -> Optional[FunctionDefinition]:
        """Extract function definition from an AST node."""
        node_type = node.get("type")

        if node_type not in ["FunctionDeclaration", "FunctionExpression", "ArrowFunctionExpression"]:
            return None

        # Get function name
        name = None
        if node_type == "FunctionDeclaration":
            name = node.get("id", {}).get("name")
        elif "id" in node and node["id"]:
            name = node.get("id", {}).get("name")

        if not name:
            return None  # Anonymous function

        # Get parameters
        params = []
        for param in node.get("params", []):
            if param.get("type") == "Identifier":
                params.append(param.get("name", ""))
            elif param.get("type") == "AssignmentPattern":
                # Default parameter: name = value
                left = param.get("left", {})
                if left.get("type") == "Identifier":
                    params.append(left.get("name", ""))

        # Get line number
        line = node.get("loc", {}).get("start", {}).get("line", 0)

        # Check if async
        is_async = node.get("async", False)

        # Check if exported (simplified - would need parent context for accuracy)
        is_exported = False

        return FunctionDefinition(
            name=name,
            file_path=file_path,
            line=line,
            params=params,
            is_async=is_async,
            is_exported=is_exported,
        )

    def _get_function_call(
        self, node: Dict[str, Any], file_path: str, caller_function: Optional[str]
    ) -> Optional[FunctionCall]:
        """Extract function call from a CallExpression node."""
        callee = node.get("callee", {})
        line = node.get("loc", {}).get("start", {}).get("line", 0)

        # Get the called function name
        callee_name = self._get_callee_name(callee)
        if not callee_name:
            return None

        return FunctionCall(
            caller_file=file_path,
            caller_function=caller_function,
            caller_line=line,
            callee_name=callee_name,
        )

    def _get_callee_name(self, callee: Dict[str, Any]) -> Optional[str]:
        """Extract function name from a callee node."""
        callee_type = callee.get("type")

        if callee_type == "Identifier":
            return callee.get("name")
        elif callee_type == "MemberExpression":
            # obj.method() -> return "method"
            prop = callee.get("property", {})
            if prop.get("type") == "Identifier":
                return prop.get("name")
        return None

    def _resolve_calls(self):
        """Resolve function calls to their definitions using symbol table and import map."""
        for call in self.call_graph.calls:
            # Try to resolve the call
            resolved = self._resolve_single_call(call)
            if resolved:
                call.callee_file = resolved[0]
                call.callee_function = resolved[1]
                call.is_resolved = True

    def _resolve_single_call(self, call: FunctionCall) -> Optional[Tuple[str, str]]:
        """
        Resolve a single function call to its definition.

        Returns:
            (file_path, function_name) tuple if resolved, None otherwise
        """
        caller_file = call.caller_file
        callee_name = call.callee_name

        # 1. Check if it's a local function (defined in same file)
        local_defs = [
            func for func in self.call_graph.get_function_definitions(callee_name)
            if func.file_path == caller_file
        ]
        if local_defs:
            return (local_defs[0].file_path, local_defs[0].name)

        # 2. Check if it's imported
        if caller_file in self._import_map:
            import_map = self._import_map[caller_file]
            if callee_name in import_map:
                source_file = import_map[callee_name]
                # Find the function in that file
                defs = [
                    func for func in self.call_graph.get_function_definitions(callee_name)
                    if func.file_path == source_file
                ]
                if defs:
                    return (defs[0].file_path, defs[0].name)

        # 3. Check all definitions (last resort - might be wrong)
        all_defs = self.call_graph.get_function_definitions(callee_name)
        if len(all_defs) == 1:
            # Only one definition exists, assume it's the right one
            return (all_defs[0].file_path, all_defs[0].name)

        return None  # Could not resolve

    def _parse_file(self, file_path: Path) -> Optional[Dict[str, Any]]:
        """Parse a JavaScript file to AST."""
        file_str = str(file_path.resolve())

        # Check cache
        if file_str in self._file_cache:
            return self._file_cache[file_str]

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                source_code = f.read()

            # Parse with esprima
            ast = esprima.parseModule(source_code, {"loc": True, "tolerant": True})
            ast_dict = ast.toDict()

            # Cache result
            self._file_cache[file_str] = ast_dict
            return ast_dict

        except Exception as e:
            print(f"⚠️  Parse error in {file_path.name}: {e}")
            return None

    def _walk_ast(self, node: Any) -> Any:
        """Recursively walk the AST and yield all nodes."""
        if isinstance(node, dict):
            yield node
            for value in node.values():
                yield from self._walk_ast(value)
        elif isinstance(node, list):
            for item in node:
                yield from self._walk_ast(item)

    def save_call_graph(self, output_path: str):
        """Save the call graph to a JSON file."""
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(self.call_graph.to_dict(), f, indent=2)
        print(f"✅ Call graph saved to {output_path}")
