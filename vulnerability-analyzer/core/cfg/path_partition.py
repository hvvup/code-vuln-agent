"""Enumerate control-flow paths to support token-aware slicing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from .structures import CFGEdge, CFGNode, FunctionCFG


@dataclass
class PathOptions:
    loop_unroll_k: int = 2
    max_paths: int = 256


@dataclass
class EnumeratedPath:
    node_sequence: List[str]
    slice_spans: List[Tuple[int, int]]
    assumed_out: List[str]


def enumerate_paths(function_cfg: FunctionCFG, options: Optional[PathOptions] = None) -> List[EnumeratedPath]:
    options = options or PathOptions()

    adjacency = _build_adjacency(function_cfg.edges)
    node_map = {node.id: node for node in function_cfg.nodes}

    entry = function_cfg.entry
    exits = set(function_cfg.exits)

    paths: List[EnumeratedPath] = []

    def dfs(current: str, sequence: List[str], visit_counts: Dict[str, int]) -> None:
        if len(paths) >= options.max_paths:
            return

        sequence.append(current)
        visit_counts[current] = visit_counts.get(current, 0) + 1

        if current in exits:
            spans = _collect_slice_spans(sequence, node_map)
            assumed_out = [node_id for node_id in node_map.keys() if node_id not in sequence]
            paths.append(EnumeratedPath(node_sequence=list(sequence), slice_spans=spans, assumed_out=assumed_out))
        else:
            for neighbor in adjacency.get(current, []):
                count = visit_counts.get(neighbor, 0)
                if count >= options.loop_unroll_k and neighbor not in exits:
                    continue
                dfs(neighbor, sequence, visit_counts)

        visit_counts[current] -= 1
        if visit_counts[current] <= 0:
            del visit_counts[current]
        sequence.pop()

    dfs(entry, [], {})
    return paths


def _build_adjacency(edges: Sequence[CFGEdge]) -> Dict[str, List[str]]:
    adjacency: Dict[str, List[str]] = {}
    for edge in edges:
        adjacency.setdefault(edge.source, []).append(edge.target)
    return adjacency


def _collect_slice_spans(node_sequence: Sequence[str], node_map: Dict[str, CFGNode]) -> List[Tuple[int, int]]:
    ranges: List[Tuple[int, int]] = []
    for node_id in node_sequence:
        node = node_map.get(node_id)
        if not node:
            continue
        start = node.span.start_line
        end = node.span.end_line
        if start == 0 and end == 0:
            continue
        ranges.append((start, end))

    if not ranges:
        return []

    ranges.sort()
    merged: List[Tuple[int, int]] = []
    current_start, current_end = ranges[0]
    for start, end in ranges[1:]:
        if start <= current_end + 1:
            current_end = max(current_end, end)
        else:
            merged.append((current_start, current_end))
            current_start, current_end = start, end
    merged.append((current_start, current_end))

    return merged


__all__ = ["enumerate_paths", "PathOptions", "EnumeratedPath"]

