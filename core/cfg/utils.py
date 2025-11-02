"""Utility helpers for working with CFG structures."""

from __future__ import annotations

import hashlib
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .structures import Span


def span_from_node(node: Dict[str, Any]) -> Optional[Span]:
    loc = node.get("loc")
    node_range = node.get("range")
    if not loc:
        return None

    start = loc.get("start", {})
    end = loc.get("end", {})
    ranges: List[List[int]] = []
    if isinstance(node_range, (list, tuple)) and len(node_range) == 2:
        ranges = [[int(node_range[0]), int(node_range[1])]]

    return Span(
        start_line=int(start.get("line", 0)),
        start_col=int(start.get("column", 0)),
        end_line=int(end.get("line", 0)),
        end_col=int(end.get("column", 0)),
        ranges=ranges,
    )


def merge_spans(spans: Iterable[Span]) -> Optional[Span]:
    spans = [span for span in spans if span is not None]
    if not spans:
        return None

    start_span = min(spans, key=lambda s: (s.start_line, s.start_col))
    end_span = max(spans, key=lambda s: (s.end_line, s.end_col))

    merged_ranges: List[List[int]] = []
    for span in spans:
        merged_ranges.extend(span.ranges)
    merged_ranges = merge_ranges(merged_ranges)

    return Span(
        start_line=start_span.start_line,
        start_col=start_span.start_col,
        end_line=end_span.end_line,
        end_col=end_span.end_col,
        ranges=merged_ranges,
    )


def merge_ranges(ranges: Iterable[Iterable[int]]) -> List[List[int]]:
    normalized: List[Tuple[int, int]] = []
    for rng in ranges:
        if isinstance(rng, (list, tuple)) and len(rng) == 2:
            normalized.append((int(rng[0]), int(rng[1])))
    if not normalized:
        return []

    normalized.sort()
    merged: List[List[int]] = []
    current_start, current_end = normalized[0]
    for start, end in normalized[1:]:
        if start <= current_end:
            current_end = max(current_end, end)
        else:
            merged.append([current_start, current_end])
            current_start, current_end = start, end
    merged.append([current_start, current_end])
    return merged


def compute_text_hash(source: str, span: Optional[Span]) -> Optional[str]:
    if span is None or not span.ranges:
        return None

    pieces: List[str] = []
    for start, end in span.ranges:
        pieces.append(source[start:end])

    hasher = hashlib.sha256()
    for piece in pieces:
        hasher.update(piece.encode("utf-8", errors="ignore"))
    return hasher.hexdigest()


def ensure_span(span: Optional[Span], fallback: Optional[Span]) -> Optional[Span]:
    if span is not None:
        return span
    return fallback


__all__ = [
    "span_from_node",
    "merge_spans",
    "merge_ranges",
    "compute_text_hash",
    "ensure_span",
]

