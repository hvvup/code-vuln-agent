"""High-level orchestration for the JavaScript CFG component."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from ..parser import JavaScriptParser, ParsedFile, ParserOptions
from .builder import CFGBuilder
from .path_partition import PathOptions, enumerate_paths
from .sampler import SamplingPolicy, sample_blocks
from .structures import CFGNode, FileCFG, FunctionCFG


@dataclass
class SamplingConfig:
    enabled: bool = False
    policy: str = "head_tail_k"
    k: int = 5
    budget: int = 10


@dataclass
class CFGGenerationOptions:
    module_type: str = "auto"
    parser: str = "esprima"
    include_anonymous_functions: bool = True
    timeout_ms_per_file: int = 5000
    source_encoding: str = "utf-8"
    loop_unroll_k: int = 2
    max_paths: int = 256
    sampling: SamplingConfig = field(default_factory=SamplingConfig)
    output_dir: str = "output"
    generate_paths: bool = True
    generate_sampling: bool = True


@dataclass
class CFGGenerationInput:
    files: List[str]
    language: str = "javascript"
    options: CFGGenerationOptions = field(default_factory=CFGGenerationOptions)

    @staticmethod
    def from_dict(payload: Dict[str, Any]) -> "CFGGenerationInput":
        options_dict = payload.get("options", {})
        sampling_dict = options_dict.get("sampling", {})
        sampling = SamplingConfig(
            enabled=sampling_dict.get("enabled", False),
            policy=sampling_dict.get("policy", "head_tail_k"),
            k=sampling_dict.get("k", 5),
            budget=sampling_dict.get("budget", 10),
        )
        options = CFGGenerationOptions(
            module_type=options_dict.get("moduleType", "auto"),
            parser=options_dict.get("parser", "esprima"),
            include_anonymous_functions=options_dict.get("includeAnonymousFunctions", True),
            timeout_ms_per_file=options_dict.get("timeoutMsPerFile", 5000),
            source_encoding=options_dict.get("sourceEncoding", "utf-8"),
            loop_unroll_k=options_dict.get("loopUnrollK", 2),
            max_paths=options_dict.get("maxPaths", 256),
            sampling=sampling,
            output_dir=options_dict.get("outputDir", "output"),
            generate_paths=options_dict.get("generatePaths", True),
            generate_sampling=options_dict.get("generateSampling", True),
        )
        return CFGGenerationInput(
            files=payload.get("files", []),
            language=payload.get("language", "javascript"),
            options=options,
        )


class CFGGenerator:
    """End-to-end CFG generation workflow for JavaScript code."""

    def __init__(self, options: Optional[CFGGenerationOptions] = None) -> None:
        self.options = options or CFGGenerationOptions()
        parser_options = ParserOptions(
            module_type=self.options.module_type,
            parser=self.options.parser,
            include_anonymous_functions=self.options.include_anonymous_functions,
            timeout_ms_per_file=self.options.timeout_ms_per_file,
            source_encoding=self.options.source_encoding,
        )
        self.parser = JavaScriptParser(parser_options)

    def generate(self, payload: CFGGenerationInput | Dict[str, Any]) -> Dict[str, Path]:
        if isinstance(payload, dict):
            generation_input = CFGGenerationInput.from_dict(payload)
        else:
            generation_input = payload

        # Refresh options and parser for this invocation
        self.options = generation_input.options
        parser_options = ParserOptions(
            module_type=self.options.module_type,
            parser=self.options.parser,
            include_anonymous_functions=self.options.include_anonymous_functions,
            timeout_ms_per_file=self.options.timeout_ms_per_file,
            source_encoding=self.options.source_encoding,
        )
        self.parser = JavaScriptParser(parser_options)

        if generation_input.language.lower() != "javascript":
            raise ValueError("CFGGenerator only supports JavaScript inputs")

        file_cfgs = [self._process_file(file_path) for file_path in generation_input.files]

        output_dir = Path(self.options.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        cfg_output = output_dir / "cfg.json"
        node_span_output = output_dir / "node_spans.json"
        line2node_output = output_dir / "line2node.json"
        paths_output = output_dir / "paths.json"
        sampled_output = output_dir / "sampled_blocks.json"

        cfg_payload = {
            "language": generation_input.language.lower(),
            "files": [file_cfg.to_dict() for file_cfg in file_cfgs],
        }
        self._write_json(cfg_output, cfg_payload)

        node_spans = self._build_node_spans(file_cfgs)
        self._write_json(node_span_output, node_spans)

        line2node = self._build_line_to_node(node_spans)
        self._write_json(line2node_output, line2node)

        output_paths: Dict[str, Path] = {
            "cfg": cfg_output,
            "node_spans": node_span_output,
            "line2node": line2node_output,
        }

        if self.options.generate_paths:
            paths_payload = self._build_paths_payload(file_cfgs)
            self._write_json(paths_output, paths_payload)
            output_paths["paths"] = paths_output

        if self.options.generate_sampling:
            sampling_payload = self._build_sampling_payload(file_cfgs)
            self._write_json(sampled_output, sampling_payload)
            output_paths["sampled_blocks"] = sampled_output

        return output_paths

    # ------------------------------------------------------------------
    # Internal helpers

    def _process_file(self, file_path: str) -> FileCFG:
        parsed = self.parser.parse_file(file_path)
        builder = CFGBuilder(str(parsed.file_path), parsed.source, parsed.ast)
        file_cfg = builder.build()
        self._annotate_successors(file_cfg)
        return file_cfg

    def _annotate_successors(self, file_cfg: FileCFG) -> None:
        adjacency: Dict[str, List[str]] = {}
        for function in file_cfg.functions:
            for edge in function.edges:
                adjacency.setdefault(edge.source, []).append(edge.target)
        for function in file_cfg.functions:
            for node in function.nodes:
                node.meta.setdefault("successors", adjacency.get(node.id, []))

    def _build_node_spans(self, file_cfgs: Iterable[FileCFG]) -> Dict[str, Dict[str, Any]]:
        node_spans: Dict[str, Dict[str, Any]] = {}
        for file_cfg in file_cfgs:
            for function in file_cfg.functions:
                for node in function.nodes:
                    span = node.span
                    node_spans[node.id] = {
                        "startLine": span.start_line,
                        "startCol": span.start_col,
                        "endLine": span.end_line,
                        "endCol": span.end_col,
                        "ranges": span.ranges,
                    }
        return node_spans

    def _build_line_to_node(self, node_spans: Dict[str, Dict[str, Any]]) -> Dict[str, List[str]]:
        line_map: Dict[int, List[str]] = {}
        for node_id, span in node_spans.items():
            start = int(span["startLine"])
            end = int(span["endLine"])
            for line in range(start, end + 1):
                line_map.setdefault(line, []).append(node_id)

        # Sort node lists by identifier for determinism
        return {str(line): sorted(nodes) for line, nodes in sorted(line_map.items())}

    def _build_paths_payload(self, file_cfgs: Iterable[FileCFG]) -> List[Dict[str, Any]]:
        payload: List[Dict[str, Any]] = []
        path_options = PathOptions(loop_unroll_k=self.options.loop_unroll_k, max_paths=self.options.max_paths)
        for file_cfg in file_cfgs:
            for function in file_cfg.functions:
                paths = enumerate_paths(function, path_options)
                for index, path in enumerate(paths, start=1):
                    payload.append(
                        {
                            "filePath": file_cfg.file_path,
                            "funcId": function.func_id,
                            "partitionId": f"pi_{index}",
                            "nodeSeq": path.node_sequence,
                            "sliceSpans": [
                                {"startLine": start, "endLine": end} for start, end in path.slice_spans
                            ],
                            "assumedOut": path.assumed_out,
                        }
                    )
        return payload

    def _build_sampling_payload(self, file_cfgs: Iterable[FileCFG]) -> List[Dict[str, Any]]:
        policy = SamplingPolicy(
            enabled=self.options.sampling.enabled,
            policy=self.options.sampling.policy,
            k=self.options.sampling.k,
            budget=self.options.sampling.budget,
        )
        payload: List[Dict[str, Any]] = []
        for file_cfg in file_cfgs:
            for function in file_cfg.functions:
                sample = sample_blocks(function.nodes, policy)
                entry = {
                    "filePath": file_cfg.file_path,
                    "funcId": function.func_id,
                    "policy": sample.get("policy"),
                    "selectedNodes": sample.get("selectedNodes", []),
                    "tokenEstimate": sample.get("tokenEstimate", 0),
                }
                if "k" in sample:
                    entry["k"] = sample["k"]
                payload.append(entry)
        return payload

    def _write_json(self, path: Path, payload: Any) -> None:
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


__all__ = ["CFGGenerator", "CFGGenerationInput", "CFGGenerationOptions", "SamplingConfig"]

