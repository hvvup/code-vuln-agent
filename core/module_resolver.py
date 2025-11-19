"""Module resolution and import/export tracking for JavaScript projects."""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
import esprima


@dataclass
class ResolvedImport:
    """Information about a resolved import statement."""

    source_file: str  # File that contains the import
    source_line: int  # Line number of import
    import_path: str  # Original import path (e.g., "./utils")
    resolved_path: Optional[str]  # Resolved absolute path (e.g., /path/to/utils.js)
    imported_symbols: List[str]  # List of imported symbols
    import_type: str  # "default", "namespace", "named"
    is_dynamic: bool = False  # True for require() or dynamic import()


@dataclass
class ExportedSymbol:
    """Information about an exported symbol."""

    symbol_name: str  # Name of the exported symbol
    file_path: str  # File that exports this symbol
    line: int  # Line number where exported
    export_type: str  # "default", "named", "namespace"
    is_re_export: bool = False  # True if re-exporting from another module
    original_source: Optional[str] = None  # For re-exports


@dataclass
class SymbolTable:
    """Symbol table mapping symbol names to their definitions."""

    exports: Dict[str, List[ExportedSymbol]] = field(default_factory=dict)
    imports: List[ResolvedImport] = field(default_factory=list)
    files: Set[str] = field(default_factory=set)

    def add_export(self, symbol: ExportedSymbol):
        """Add an exported symbol to the table."""
        if symbol.symbol_name not in self.exports:
            self.exports[symbol.symbol_name] = []
        self.exports[symbol.symbol_name].append(symbol)
        self.files.add(symbol.file_path)

    def add_import(self, resolved_import: ResolvedImport):
        """Add a resolved import to the table."""
        self.imports.append(resolved_import)
        self.files.add(resolved_import.source_file)

    def get_symbol_definition(self, symbol_name: str) -> List[ExportedSymbol]:
        """Get all definitions of a symbol."""
        return self.exports.get(symbol_name, [])

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "exports": {
                name: [
                    {
                        "symbol_name": sym.symbol_name,
                        "file_path": sym.file_path,
                        "line": sym.line,
                        "export_type": sym.export_type,
                        "is_re_export": sym.is_re_export,
                        "original_source": sym.original_source,
                    }
                    for sym in symbols
                ]
                for name, symbols in self.exports.items()
            },
            "imports": [
                {
                    "source_file": imp.source_file,
                    "source_line": imp.source_line,
                    "import_path": imp.import_path,
                    "resolved_path": imp.resolved_path,
                    "imported_symbols": imp.imported_symbols,
                    "import_type": imp.import_type,
                    "is_dynamic": imp.is_dynamic,
                }
                for imp in self.imports
            ],
            "files": list(self.files),
        }


class ModuleResolver:
    """Resolves JavaScript module imports and builds symbol tables."""

    def __init__(self, root_path: str):
        """
        Initialize the module resolver.

        Args:
            root_path: Root directory of the project
        """
        self.root_path = Path(root_path).resolve()
        self.symbol_table = SymbolTable()
        self._file_cache: Dict[str, Dict[str, Any]] = {}

    def resolve_repository(self, extensions: Optional[List[str]] = None) -> SymbolTable:
        """
        Resolve all modules in the repository.

        Args:
            extensions: File extensions to process (default: [".js", ".jsx", ".ts", ".tsx"])

        Returns:
            Complete symbol table for the repository
        """
        if extensions is None:
            extensions = [".js", ".jsx", ".ts", ".tsx"]

        # Find all JavaScript files
        js_files = []
        for ext in extensions:
            js_files.extend(self.root_path.rglob(f"*{ext}"))

        # Skip node_modules and common build directories
        js_files = [
            f for f in js_files
            if "node_modules" not in f.parts
            and "dist" not in f.parts
            and "build" not in f.parts
            and ".next" not in f.parts
        ]

        print(f"🔍 Found {len(js_files)} JavaScript files to analyze")

        # First pass: Extract all exports
        for file_path in js_files:
            try:
                self._extract_exports(file_path)
            except Exception as e:
                print(f"⚠️  Warning: Failed to extract exports from {file_path.name}: {e}")

        # Second pass: Resolve all imports
        for file_path in js_files:
            try:
                self._extract_and_resolve_imports(file_path)
            except Exception as e:
                print(f"⚠️  Warning: Failed to resolve imports in {file_path.name}: {e}")

        return self.symbol_table

    def _extract_exports(self, file_path: Path):
        """Extract all export statements from a file."""
        ast = self._parse_file(file_path)
        if not ast:
            return

        file_str = str(file_path.resolve())

        for node in self._walk_ast(ast):
            node_type = node.get("type")

            # Named export: export { foo, bar }
            if node_type == "ExportNamedDeclaration":
                self._handle_named_export(node, file_str)

            # Default export: export default foo
            elif node_type == "ExportDefaultDeclaration":
                self._handle_default_export(node, file_str)

            # Export all: export * from "./module"
            elif node_type == "ExportAllDeclaration":
                self._handle_export_all(node, file_str)

    def _extract_and_resolve_imports(self, file_path: Path):
        """Extract and resolve all import statements from a file."""
        ast = self._parse_file(file_path)
        if not ast:
            return

        file_str = str(file_path.resolve())

        for node in self._walk_ast(ast):
            node_type = node.get("type")

            # ES6 import: import { foo } from "./module"
            if node_type == "ImportDeclaration":
                self._handle_import_declaration(node, file_path, file_str)

            # CommonJS require: const foo = require("./module")
            elif node_type == "CallExpression":
                callee = node.get("callee", {})
                if callee.get("type") == "Identifier" and callee.get("name") == "require":
                    self._handle_require_call(node, file_path, file_str)

    def _handle_named_export(self, node: Dict[str, Any], file_path: str):
        """Handle named export declarations."""
        line = node.get("loc", {}).get("start", {}).get("line", 0)

        # export { foo, bar }
        if "specifiers" in node:
            for spec in node.get("specifiers", []):
                exported_name = spec.get("exported", {}).get("name")
                if exported_name:
                    symbol = ExportedSymbol(
                        symbol_name=exported_name,
                        file_path=file_path,
                        line=line,
                        export_type="named",
                    )
                    self.symbol_table.add_export(symbol)

        # export const foo = ...
        if "declaration" in node and node["declaration"]:
            decl = node["declaration"]
            if decl.get("type") == "VariableDeclaration":
                for declarator in decl.get("declarations", []):
                    name = declarator.get("id", {}).get("name")
                    if name:
                        symbol = ExportedSymbol(
                            symbol_name=name,
                            file_path=file_path,
                            line=line,
                            export_type="named",
                        )
                        self.symbol_table.add_export(symbol)
            elif decl.get("type") in ["FunctionDeclaration", "ClassDeclaration"]:
                name = decl.get("id", {}).get("name")
                if name:
                    symbol = ExportedSymbol(
                        symbol_name=name,
                        file_path=file_path,
                        line=line,
                        export_type="named",
                    )
                    self.symbol_table.add_export(symbol)

    def _handle_default_export(self, node: Dict[str, Any], file_path: str):
        """Handle default export declarations."""
        line = node.get("loc", {}).get("start", {}).get("line", 0)

        symbol = ExportedSymbol(
            symbol_name="default",
            file_path=file_path,
            line=line,
            export_type="default",
        )
        self.symbol_table.add_export(symbol)

    def _handle_export_all(self, node: Dict[str, Any], file_path: str):
        """Handle export all declarations (export * from ...)."""
        line = node.get("loc", {}).get("start", {}).get("line", 0)
        source = node.get("source", {}).get("value", "")

        if source:
            symbol = ExportedSymbol(
                symbol_name="*",
                file_path=file_path,
                line=line,
                export_type="namespace",
                is_re_export=True,
                original_source=source,
            )
            self.symbol_table.add_export(symbol)

    def _handle_import_declaration(self, node: Dict[str, Any], file_path: Path, file_str: str):
        """Handle ES6 import declarations."""
        line = node.get("loc", {}).get("start", {}).get("line", 0)
        source = node.get("source", {}).get("value", "")

        if not source:
            return

        # Resolve the import path
        resolved = self._resolve_import_path(source, file_path)

        # Extract imported symbols
        imported_symbols = []
        import_type = "named"

        for spec in node.get("specifiers", []):
            spec_type = spec.get("type")
            if spec_type == "ImportDefaultSpecifier":
                imported_symbols.append("default")
                import_type = "default"
            elif spec_type == "ImportNamespaceSpecifier":
                imported_symbols.append("*")
                import_type = "namespace"
            elif spec_type == "ImportSpecifier":
                imported_name = spec.get("imported", {}).get("name")
                if imported_name:
                    imported_symbols.append(imported_name)

        resolved_import = ResolvedImport(
            source_file=file_str,
            source_line=line,
            import_path=source,
            resolved_path=resolved,
            imported_symbols=imported_symbols,
            import_type=import_type,
        )
        self.symbol_table.add_import(resolved_import)

    def _handle_require_call(self, node: Dict[str, Any], file_path: Path, file_str: str):
        """Handle CommonJS require() calls."""
        line = node.get("loc", {}).get("start", {}).get("line", 0)

        # Get the require argument
        args = node.get("arguments", [])
        if not args:
            return

        arg = args[0]
        if arg.get("type") != "Literal":
            return  # Dynamic require

        source = arg.get("value", "")
        if not source:
            return

        # Resolve the import path
        resolved = self._resolve_import_path(source, file_path)

        resolved_import = ResolvedImport(
            source_file=file_str,
            source_line=line,
            import_path=source,
            resolved_path=resolved,
            imported_symbols=["*"],  # CommonJS imports entire module
            import_type="namespace",
            is_dynamic=True,
        )
        self.symbol_table.add_import(resolved_import)

    def _resolve_import_path(self, import_path: str, from_file: Path) -> Optional[str]:
        """
        Resolve an import path to an absolute file path.

        Args:
            import_path: The import path (e.g., "./utils", "../lib/foo")
            from_file: The file containing the import

        Returns:
            Absolute path to the imported file, or None if not found
        """
        # Skip npm packages (don't start with . or /)
        if not import_path.startswith(".") and not import_path.startswith("/"):
            return None  # External package

        # Resolve relative to the importing file's directory
        base_dir = from_file.parent

        # Try various extensions
        extensions = ["", ".js", ".jsx", ".ts", ".tsx", "/index.js", "/index.ts"]

        for ext in extensions:
            candidate = (base_dir / (import_path + ext)).resolve()
            if candidate.exists() and candidate.is_file():
                return str(candidate)

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

    def save_symbol_table(self, output_path: str):
        """Save the symbol table to a JSON file."""
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(self.symbol_table.to_dict(), f, indent=2)
        print(f"✅ Symbol table saved to {output_path}")
