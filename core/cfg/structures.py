"""Data structures that represent a control flow graph for JavaScript code."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Span:
    """Represents a source code span in terms of lines, columns, and byte ranges."""

    start_line: int
    start_col: int
    end_line: int
    end_col: int
    ranges: List[List[int]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "startLine": self.start_line,
            "startCol": self.start_col,
            "endLine": self.end_line,
            "endCol": self.end_col,
            "ranges": self.ranges,
        }


@dataclass
class CFGNode:
    id: str
    kind: str
    span: Span
    ast_nodes: List[Dict[str, Any]] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)
    text_hash: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "id": self.id,
            "kind": self.kind,
            "span": self.span.to_dict(),
        }
        if self.ast_nodes:
            data["astNodes"] = self.ast_nodes
        if self.meta:
            data["meta"] = self.meta
        if self.text_hash:
            data["textHash"] = self.text_hash
        return data


@dataclass
class CFGEdge:
    source: str
    target: str
    edge_type: str
    label: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "from": self.source,
            "to": self.target,
            "type": self.edge_type,
        }
        if self.label is not None:
            data["label"] = self.label
        return data


@dataclass
class FunctionCFG:
    func_id: str
    name: str
    entry: str
    exits: List[str]
    nodes: List[CFGNode]
    edges: List[CFGEdge]
    range: Optional[Span] = None
    file_path: Optional[str] = None
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "funcId": self.func_id,
            "name": self.name,
            "entry": self.entry,
            "exits": self.exits,
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
        }
        if self.range is not None:
            data["range"] = self.range.to_dict()
        if self.meta:
            data["meta"] = self.meta
        return data


@dataclass
class FileCFG:
    file_path: str
    functions: List[FunctionCFG]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "filePath": self.file_path,
            "functions": [function.to_dict() for function in self.functions],
        }


__all__ = [
    "Span",
    "CFGNode",
    "CFGEdge",
    "FunctionCFG",
    "FileCFG",
]

