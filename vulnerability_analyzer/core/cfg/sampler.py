"""Sampling policies for reducing CFG block counts to fit token budgets."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from .structures import CFGNode


@dataclass
class SamplingPolicy:
    enabled: bool = False
    policy: str = "head_tail_k"
    k: int = 5
    budget: int = 10


def sample_blocks(nodes: List[CFGNode], policy: Optional[SamplingPolicy] = None) -> Dict[str, object]:
    policy = policy or SamplingPolicy(enabled=False)
    if not policy.enabled or not nodes:
        return {
            "policy": policy.policy if policy else "none",
            "selectedNodes": [node.id for node in nodes],
            "tokenEstimate": _estimate_tokens(nodes),
        }

    if policy.policy == "head_tail_k":
        return _head_tail_policy(nodes, policy)
    if policy.policy == "importance":
        return _importance_policy(nodes, policy)

    return {
        "policy": "unknown",
        "selectedNodes": [node.id for node in nodes],
        "tokenEstimate": _estimate_tokens(nodes),
    }


def _head_tail_policy(nodes: List[CFGNode], policy: SamplingPolicy) -> Dict[str, object]:
    k = max(1, policy.k)
    if len(nodes) <= policy.budget:
        selected = [node.id for node in nodes]
    else:
        head = nodes[:k]
        tail = nodes[-k:]
        selected_ids = [node.id for node in head + tail]
        seen = set()
        selected = []
        for node_id in selected_ids:
            if node_id not in seen:
                selected.append(node_id)
                seen.add(node_id)

    return {
        "policy": "head_tail_k",
        "k": k,
        "selectedNodes": selected,
        "tokenEstimate": _estimate_tokens([node for node in nodes if node.id in selected]),
    }


def _importance_policy(nodes: List[CFGNode], policy: SamplingPolicy) -> Dict[str, object]:
    scores = []
    for node in nodes:
        score = 0
        degree = len(node.meta.get("successors", []))
        if degree:
            score += degree
        if node.kind in {"Branch", "Switch"}:
            score += 3
        if node.kind in {"Handler"}:
            score += 2
        if node.kind in {"Return", "Throw"}:
            score += 1
        score += node.meta.get("loopDepth", 0)
        scores.append((score, node))

    scores.sort(key=lambda item: item[0], reverse=True)
    selected_nodes = [node for _, node in scores[: policy.budget]]
    selected_ids = [node.id for node in selected_nodes]

    return {
        "policy": "importance",
        "selectedNodes": selected_ids,
        "tokenEstimate": _estimate_tokens(selected_nodes),
    }


def _estimate_tokens(nodes: List[CFGNode]) -> int:
    total_chars = 0
    for node in nodes:
        for rng in node.span.ranges:
            if isinstance(rng, (list, tuple)) and len(rng) == 2:
                total_chars += max(0, int(rng[1]) - int(rng[0]))
    return max(1, total_chars // 4) if total_chars else 0


__all__ = ["SamplingPolicy", "sample_blocks"]

