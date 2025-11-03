"""LangChain tool wrapper for the JavaScript CFG generator."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from langchain.tools import BaseTool
from pydantic import BaseModel, Field, PrivateAttr

from core.cfg import CFGGenerator


class CFGGeneratorToolInput(BaseModel):
    """Input schema for CFG generator tool."""

    files: List[str] = Field(
        ...,
        description="List of JavaScript file paths to analyze (e.g., ['/path/to/file.js'])"
    )
    language: str = Field(
        default="javascript",
        description="Programming language (default: javascript)"
    )
    options: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional CFG generation options (moduleType, parser, loopUnrollK, etc.)"
    )


class CFGGeneratorTool(BaseTool):
    _generator: CFGGenerator = PrivateAttr(default_factory=CFGGenerator)

    name: str = "cfg_generator"
    description: str = (
        "Generate control flow graphs (CFG) for JavaScript files to understand program execution paths and structure. "
        "Takes a file path and returns CFG artifacts (cfg.json, node_spans.json, line2node.json, paths.json). "
        "Use this to analyze code structure, data flow, and execution paths through JavaScript programs. "
        "Essential for understanding complex control flow and identifying security-relevant code paths."
    )
    args_schema: type[BaseModel] = CFGGeneratorToolInput

    def _run(
        self,
        files: List[str],
        language: str = "javascript",
        options: Optional[Dict[str, Any]] = None
    ) -> str:
        """Generate CFG for the specified JavaScript files."""
        payload = {
            "files": files,
            "language": language,
            "options": options or {}
        }
        output_paths = self._generator.generate(payload)
        return json.dumps({key: str(path) for key, path in output_paths.items()}, indent=2)

    async def _arun(self, *args: Any, **kwargs: Any) -> str:
        """Async execution not supported."""
        raise NotImplementedError("CFGGeneratorTool does not support async execution")


__all__ = ["CFGGeneratorTool"]
