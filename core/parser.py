"""Utilities for parsing JavaScript source code into ESTree-compatible ASTs.

The parser layer is intentionally lightweight so that the downstream CFG
component can rely on consistent node structure and precise source locations.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import esprima


@dataclass
class ParserOptions:
    """Options that control how JavaScript is parsed into an AST."""

    module_type: str = "auto"  # "module", "script", or "auto"
    parser: str = "esprima"  # Reserved for future parser backends
    include_anonymous_functions: bool = True
    timeout_ms_per_file: int = 5000
    source_encoding: str = "utf-8"


@dataclass
class ParsedFile:
    """Container for the source text and AST of a JavaScript file."""

    file_path: Path
    source: str
    ast: Dict[str, Any]
    options: ParserOptions


class JavaScriptParser:
    """Parse JavaScript source into an ESTree AST with precise locations."""

    def __init__(self, options: Optional[ParserOptions] = None) -> None:
        self.options = options or ParserOptions()

    def parse_file(self, file_path: str | Path) -> ParsedFile:
        path = Path(file_path).resolve()
        source = path.read_text(encoding=self.options.source_encoding)
        ast = self._parse_source(source, module_hint=self.options.module_type)
        return ParsedFile(file_path=path, source=source, ast=ast, options=self.options)

    def parse_code(self, code: str, file_path: Optional[str] = None) -> ParsedFile:
        path = Path(file_path) if file_path else Path("<memory>")
        ast = self._parse_source(code, module_hint=self.options.module_type)
        return ParsedFile(file_path=path, source=code, ast=ast, options=self.options)

    def _parse_source(self, source: str, module_hint: str) -> Dict[str, Any]:
        """Parse JavaScript source using Esprima with ESTree output."""

        parse_as_module = self._should_parse_as_module(source, module_hint)
        parse_kwargs: Dict[str, Any] = {
            "loc": True,
            "range": True,
            "comment": True,
            "tokens": True,
            "tolerant": True,
        }

        try:
            if parse_as_module:
                parser_fn = getattr(esprima, "parse_module", None) or getattr(esprima, "parseModule")
            else:
                parser_fn = getattr(esprima, "parse_script", None) or getattr(esprima, "parseScript")

            program = parser_fn(source, **parse_kwargs)
            if hasattr(program, "toDict"):
                return program.toDict()
            if isinstance(program, dict):
                return program
            raise TypeError("Unexpected AST type returned by esprima parser")
        except Exception as e:
            # Provide more context about the parsing error
            error_msg = f"Failed to parse JavaScript: {str(e)}"
            if hasattr(e, 'description'):
                error_msg += f" - {e.description}"
            if hasattr(e, 'lineNumber'):
                error_msg += f" at line {e.lineNumber}"
            raise ValueError(error_msg) from e

    def _should_parse_as_module(self, source: str, module_hint: str) -> bool:
        if module_hint == "module":
            return True
        if module_hint == "script":
            return False

        # Heuristic for "auto": treat as module if we see import/export keywords
        lowered = source.lower()
        if "import" in lowered or "export" in lowered:
            return True
        return False


__all__ = ["ParserOptions", "ParsedFile", "JavaScriptParser"]

