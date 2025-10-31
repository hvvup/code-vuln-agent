"""Build control flow graphs for JavaScript functions based on ESTree ASTs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from .structures import CFGEdge, CFGNode, FileCFG, FunctionCFG, Span
from .utils import compute_text_hash, merge_spans, span_from_node


@dataclass
class BuildResult:
    entry: Optional[str]
    fallthroughs: List[str]


@dataclass
class FunctionLike:
    node: Dict[str, Any]
    name: str
    span: Optional[Span]
    parent: Optional[str] = None


@dataclass
class LoopContext:
    break_targets: List[str]
    continue_targets: List[str]


@dataclass
class TryContext:
    catch_target: Optional[str]


@dataclass
class FinallyContext:
    entry: str
    exits: List[str]
    targets: Set[str]


class NodeFactory:
    def __init__(self) -> None:
        self._counter = 0

    def new_id(self) -> str:
        node_id = f"n{self._counter}"
        self._counter += 1
        return node_id


class CFGBuilder:
    """Convert a parsed JavaScript program into per-function CFGs."""

    def __init__(self, file_path: str, source: str, program: Dict[str, Any]) -> None:
        self.file_path = file_path
        self.source = source
        self.program = program
        self._function_counter = 0

    # ------------------------------------------------------------------
    # Public API

    def build(self) -> FileCFG:
        functions: List[FunctionCFG] = []
        functions.append(self._build_global_function())
        functions.extend(self._build_nested_functions())
        return FileCFG(file_path=self.file_path, functions=functions)

    # ------------------------------------------------------------------
    # Function discovery helpers

    def _build_global_function(self) -> FunctionCFG:
        program_span = span_from_node(self.program)
        function = FunctionLike(node=self.program, name="<global>", span=program_span)
        return self._build_function(function)

    def _build_nested_functions(self) -> List[FunctionCFG]:
        return [self._build_function(fn) for fn in self._collect_function_nodes(self.program)]

    def _collect_function_nodes(self, node: Dict[str, Any], parent_name: Optional[str] = None) -> List[FunctionLike]:
        functions: List[FunctionLike] = []
        node_type = node.get("type")
        if node_type in {"FunctionDeclaration", "FunctionExpression", "ArrowFunctionExpression"}:
            name = self._function_name(node, parent_name)
            functions.append(FunctionLike(node=node, name=name, span=span_from_node(node), parent=parent_name))
            parent_name = name

        for child in self._iter_child_nodes(node):
            if isinstance(child, dict):
                functions.extend(self._collect_function_nodes(child, parent_name))
            elif isinstance(child, list):
                for element in child:
                    if isinstance(element, dict):
                        functions.extend(self._collect_function_nodes(element, parent_name))
        return functions

    def _function_name(self, node: Dict[str, Any], parent: Optional[str]) -> str:
        identifier = node.get("id")
        if identifier and identifier.get("name"):
            return identifier["name"]
        if parent:
            return f"<anonymous:{parent}>"
        loc = node.get("loc", {}).get("start", {})
        line = loc.get("line", 0)
        column = loc.get("column", 0)
        return f"<anonymous@{line}:{column}>"

    def _iter_child_nodes(self, node: Dict[str, Any]) -> Iterable[Any]:
        for key, value in node.items():
            if key in {"type", "loc", "range", "start", "end"}:
                continue
            yield value

    # ------------------------------------------------------------------
    # Function level CFG construction

    def _build_function(self, function: FunctionLike) -> FunctionCFG:
        body = function.node.get("body")
        if function.node.get("type") == "Program":
            statements = function.node.get("body", [])
        elif isinstance(body, dict) and body.get("type") == "BlockStatement":
            statements = body.get("body", [])
        else:
            statements = [body] if body else []

        self.factory = NodeFactory()
        self.nodes: Dict[str, CFGNode] = {}
        self.edges: List[CFGEdge] = []
        self.edge_set: Set[Tuple[str, str, str, Optional[str]]] = set()

        self.exit_node_id: Optional[str] = None
        self.loop_stack: List[LoopContext] = []
        self.try_stack: List[TryContext] = []
        self.finally_stack: List[FinallyContext] = []
        self.finally_contexts: List[FinallyContext] = []
        self.break_stack: List[List[str]] = []
        self.continue_stack: List[List[str]] = []
        self.label_context_stack: List[Dict[str, Tuple[List[str], List[str]]]] = []
        self.pending_label: Optional[str] = None

        entry_node = self._create_node("Entry", [function.node], function.span)
        exit_node = self._create_node("Exit", [function.node], function.span)
        self.exit_node_id = exit_node.id

        body_result = self._build_statement_list(statements, [exit_node.id])

        if body_result.entry:
            self._add_edge(entry_node.id, body_result.entry, "Next")
        else:
            self._add_edge(entry_node.id, exit_node.id, "Next")

        self._finalize_finally_edges()

        function_span = function.span or merge_spans(node.span for node in self.nodes.values())
        self._function_counter += 1
        func_id = f"f_{self._function_counter}"

        return FunctionCFG(
            func_id=func_id,
            name=function.name,
            entry=entry_node.id,
            exits=[exit_node.id],
            nodes=list(self.nodes.values()),
            edges=self.edges,
            range=function_span,
            file_path=self.file_path,
            meta={
                "isAsync": bool(function.node.get("async")),
                "isGenerator": bool(function.node.get("generator")),
            },
        )

    # ------------------------------------------------------------------
    # Statement dispatch

    def _build_statement_list(self, statements: Sequence[Optional[Dict[str, Any]]], next_targets: List[str]) -> BuildResult:
        if not statements:
            return BuildResult(entry=None, fallthroughs=[])

        targets = list(next_targets)
        entry: Optional[str] = None
        fallthroughs: List[str] = []

        for statement in reversed(statements):
            result = self._build_statement(statement, targets)
            if result.entry:
                entry = result.entry
                targets = [result.entry]
            if not fallthroughs:
                fallthroughs = list(result.fallthroughs)

        if not fallthroughs:
            fallthroughs = list(targets)

        return BuildResult(entry=entry, fallthroughs=fallthroughs)

    def _build_statement(self, statement: Optional[Dict[str, Any]], next_targets: List[str]) -> BuildResult:
        if not statement:
            return BuildResult(entry=None, fallthroughs=[])

        node_type = statement.get("type")

        if node_type == "BlockStatement":
            return self._build_statement_list(statement.get("body", []), next_targets)

        if node_type in {
            "ExpressionStatement",
            "VariableDeclaration",
            "DebuggerStatement",
            "EmptyStatement",
            "ReturnStatement",
            "ThrowStatement",
            "BreakStatement",
            "ContinueStatement",
        }:
            return self._build_simple_statement(statement, next_targets)

        if node_type == "IfStatement":
            return self._build_if(statement, next_targets)

        if node_type in {"WhileStatement", "DoWhileStatement", "ForStatement", "ForInStatement", "ForOfStatement"}:
            return self._build_loop(statement, next_targets)

        if node_type == "SwitchStatement":
            return self._build_switch(statement, next_targets)

        if node_type == "TryStatement":
            return self._build_try(statement, next_targets)

        if node_type == "LabeledStatement":
            return self._build_labeled(statement, next_targets)

        if node_type == "WithStatement":
            return self._build_unknown(statement, next_targets, kind="Unknown")

        # Fallback for unsupported nodes (e.g., class declarations inside blocks)
        return self._build_unknown(statement, next_targets, kind="Linear")

    # ------------------------------------------------------------------
    # Simple statement handling

    def _build_simple_statement(self, statement: Dict[str, Any], next_targets: List[str]) -> BuildResult:
        node_type = statement.get("type")
        kind_map = {
            "ExpressionStatement": "Linear",
            "VariableDeclaration": "Linear",
            "DebuggerStatement": "Linear",
            "EmptyStatement": "Linear",
            "ReturnStatement": "Return",
            "ThrowStatement": "Throw",
            "BreakStatement": "Break",
            "ContinueStatement": "Continue",
        }
        kind = kind_map.get(node_type, "Linear")
        node = self._create_node(kind, [statement])

        if node_type == "ReturnStatement":
            targets = self._wrap_targets_with_finally([self.exit_node_id])
            self._connect_fallthroughs([node.id], targets, "Next")
            return BuildResult(entry=node.id, fallthroughs=[])

        if node_type == "ThrowStatement":
            catch_target = self._nearest_catch_target()
            if catch_target:
                self._add_edge(node.id, catch_target, "Except")
            else:
                targets = self._wrap_targets_with_finally([self.exit_node_id])
                self._connect_fallthroughs([node.id], targets, "Except")
            return BuildResult(entry=node.id, fallthroughs=[])

        if node_type == "BreakStatement":
            label = self._extract_label(statement)
            targets = self._label_break_targets(label) if label else self._nearest_break_targets()
            targets = targets or [self.exit_node_id]
            routed = self._wrap_targets_with_finally(targets)
            self._connect_fallthroughs([node.id], routed, "Next")
            return BuildResult(entry=node.id, fallthroughs=[])

        if node_type == "ContinueStatement":
            label = self._extract_label(statement)
            targets = self._label_continue_targets(label) if label else self._nearest_continue_targets()
            targets = targets or [self.exit_node_id]
            routed = self._wrap_targets_with_finally(targets)
            self._connect_fallthroughs([node.id], routed, "Next")
            return BuildResult(entry=node.id, fallthroughs=[])

        routed_targets = self._wrap_targets_with_finally(next_targets)
        self._connect_fallthroughs([node.id], routed_targets, "Next")
        return BuildResult(entry=node.id, fallthroughs=[node.id])

    def _extract_label(self, statement: Dict[str, Any]) -> Optional[str]:
        label = statement.get("label")
        if isinstance(label, dict):
            return label.get("name")
        return None

    # ------------------------------------------------------------------
    # Conditionals

    def _build_if(self, statement: Dict[str, Any], next_targets: List[str]) -> BuildResult:
        meta = {"op": "IfStatement", "cond": self._snippet(statement.get("test"))}
        branch_node = self._create_node("Branch", [statement], meta)

        true_result = self._build_statement(statement.get("consequent"), next_targets)
        false_result = self._build_statement(statement.get("alternate"), next_targets)

        if true_result.entry:
            self._add_edge(branch_node.id, true_result.entry, "True", "cond:true")
        else:
            routed = self._wrap_targets_with_finally(next_targets)
            self._connect_fallthroughs([branch_node.id], routed, "True")

        if false_result.entry:
            self._add_edge(branch_node.id, false_result.entry, "False", "cond:false")
        else:
            routed = self._wrap_targets_with_finally(next_targets)
            self._connect_fallthroughs([branch_node.id], routed, "False", "cond:false")

        fallthroughs: List[str] = []
        fallthroughs.extend(true_result.fallthroughs)
        fallthroughs.extend(false_result.fallthroughs)
        if not statement.get("alternate"):
            fallthroughs.append(branch_node.id)

        return BuildResult(entry=branch_node.id, fallthroughs=fallthroughs)

    # ------------------------------------------------------------------
    # Loops

    def _build_loop(self, statement: Dict[str, Any], next_targets: List[str]) -> BuildResult:
        node_type = statement.get("type")
        if node_type == "WhileStatement":
            return self._build_while(statement, next_targets)
        if node_type == "DoWhileStatement":
            return self._build_do_while(statement, next_targets)
        if node_type == "ForStatement":
            return self._build_for(statement, next_targets)
        if node_type in {"ForInStatement", "ForOfStatement"}:
            return self._build_for_in_of(statement, next_targets)
        return BuildResult(entry=None, fallthroughs=list(next_targets))

    def _build_while(self, statement: Dict[str, Any], next_targets: List[str]) -> BuildResult:
        meta = {"op": "WhileStatement", "cond": self._snippet(statement.get("test"))}
        header = self._create_node("While", [statement], meta)

        break_targets = list(next_targets)
        continue_targets = [header.id]
        self._register_pending_label(break_targets, continue_targets)

        self.loop_stack.append(LoopContext(break_targets=break_targets, continue_targets=continue_targets))
        self.break_stack.append(break_targets)
        self.continue_stack.append(continue_targets)

        body_result = self._build_statement(statement.get("body"), continue_targets)

        if body_result.entry:
            self._add_edge(header.id, body_result.entry, "True", "cond:true")
        else:
            self._add_edge(header.id, header.id, "True", "cond:true")

        false_targets = self._wrap_targets_with_finally(next_targets)
        self._connect_fallthroughs([header.id], false_targets, "False", "cond:false")

        self.loop_stack.pop()
        self.break_stack.pop()
        self.continue_stack.pop()

        return BuildResult(entry=header.id, fallthroughs=false_targets)

    def _build_do_while(self, statement: Dict[str, Any], next_targets: List[str]) -> BuildResult:
        meta = {"op": "DoWhileStatement", "cond": self._snippet(statement.get("test"))}
        header = self._create_node("DoWhile", [statement], meta)

        break_targets = list(next_targets)
        continue_targets = [header.id]
        self._register_pending_label(break_targets, continue_targets)

        self.loop_stack.append(LoopContext(break_targets=break_targets, continue_targets=continue_targets))
        self.break_stack.append(break_targets)
        self.continue_stack.append(continue_targets)

        body_result = self._build_statement(statement.get("body"), continue_targets)
        loop_entry = body_result.entry or header.id

        if body_result.entry:
            self._add_edge(header.id, body_result.entry, "True", "cond:true")
        else:
            self._add_edge(header.id, header.id, "True", "cond:true")

        false_targets = self._wrap_targets_with_finally(next_targets)
        self._connect_fallthroughs([header.id], false_targets, "False", "cond:false")

        self.loop_stack.pop()
        self.break_stack.pop()
        self.continue_stack.pop()

        return BuildResult(entry=loop_entry, fallthroughs=false_targets)

    def _build_for(self, statement: Dict[str, Any], next_targets: List[str]) -> BuildResult:
        meta = {"op": "ForStatement", "cond": self._snippet(statement.get("test"))}
        header = self._create_node("For", [statement], meta)

        update = statement.get("update")
        if update:
            update_result = self._build_expression_as_statement(update, [header.id])
            continue_targets = [update_result.entry] if update_result.entry else [header.id]
        else:
            continue_targets = [header.id]

        break_targets = list(next_targets)
        self._register_pending_label(break_targets, continue_targets)

        self.loop_stack.append(LoopContext(break_targets=break_targets, continue_targets=continue_targets))
        self.break_stack.append(break_targets)
        self.continue_stack.append(continue_targets)

        body_result = self._build_statement(statement.get("body"), continue_targets)

        if body_result.entry:
            self._add_edge(header.id, body_result.entry, "True", "cond:true")
        else:
            self._add_edge(header.id, continue_targets[0], "True", "cond:true")

        false_targets = self._wrap_targets_with_finally(next_targets)
        self._connect_fallthroughs([header.id], false_targets, "False", "cond:false")

        init = statement.get("init")
        if init:
            init_result = (
                self._build_statement(init, [header.id])
                if isinstance(init, dict)
                else self._build_expression_as_statement(init, [header.id])
            )
            entry = init_result.entry or header.id
        else:
            entry = header.id

        self.loop_stack.pop()
        self.break_stack.pop()
        self.continue_stack.pop()

        return BuildResult(entry=entry, fallthroughs=false_targets)

    def _build_for_in_of(self, statement: Dict[str, Any], next_targets: List[str]) -> BuildResult:
        op = statement.get("type")
        meta = {
            "op": op,
            "left": self._snippet(statement.get("left")),
            "right": self._snippet(statement.get("right")),
        }
        header = self._create_node("ForEach", [statement], meta)

        break_targets = list(next_targets)
        continue_targets = [header.id]
        self._register_pending_label(break_targets, continue_targets)

        self.loop_stack.append(LoopContext(break_targets=break_targets, continue_targets=continue_targets))
        self.break_stack.append(break_targets)
        self.continue_stack.append(continue_targets)

        body_result = self._build_statement(statement.get("body"), continue_targets)

        if body_result.entry:
            self._add_edge(header.id, body_result.entry, "True")
        else:
            self._add_edge(header.id, header.id, "True")

        false_targets = self._wrap_targets_with_finally(next_targets)
        self._connect_fallthroughs([header.id], false_targets, "False")

        self.loop_stack.pop()
        self.break_stack.pop()
        self.continue_stack.pop()

        return BuildResult(entry=header.id, fallthroughs=false_targets)

    # ------------------------------------------------------------------
    # Switch

    def _build_switch(self, statement: Dict[str, Any], next_targets: List[str]) -> BuildResult:
        meta = {"op": "SwitchStatement", "discriminant": self._snippet(statement.get("discriminant"))}
        switch_node = self._create_node("Switch", [statement], meta)

        break_targets = list(next_targets)
        self._register_pending_label(break_targets, [])
        self.break_stack.append(break_targets)

        cases: List[Dict[str, Any]] = statement.get("cases", [])
        fallthrough_targets = list(next_targets)
        case_entries: List[Tuple[Dict[str, Any], BuildResult]] = []

        for case in reversed(cases):
            case_result = self._build_statement_list(case.get("consequent", []), fallthrough_targets)
            case_entries.append((case, case_result))
            if case_result.entry:
                fallthrough_targets = [case_result.entry]
        case_entries.reverse()

        for index, (case, result) in enumerate(case_entries):
            test = case.get("test")
            label = f"case:{self._snippet(test) if test else 'default'}"
            edge_type = "Case" if test else "Default"
            if result.entry:
                self._add_edge(switch_node.id, result.entry, edge_type, label)
            else:
                routed = self._wrap_targets_with_finally(next_targets)
                self._connect_fallthroughs([switch_node.id], routed, edge_type, label)

        self.break_stack.pop()
        fallthroughs = self._wrap_targets_with_finally(next_targets)
        return BuildResult(entry=switch_node.id, fallthroughs=fallthroughs)

    # ------------------------------------------------------------------
    # Try/Catch/Finally

    def _build_try(self, statement: Dict[str, Any], next_targets: List[str]) -> BuildResult:
        final_context: Optional[FinallyContext] = None
        final_targets = self._wrap_targets_with_finally(next_targets)

        finalizer = statement.get("finalizer")
        if finalizer:
            final_result = self._build_statement_list(finalizer.get("body", []), final_targets)
            final_node = self._create_node("Handler", [finalizer], {"op": "Finally"})
            if final_result.entry:
                self._add_edge(final_node.id, final_result.entry, "Next")
                exits = final_result.fallthroughs or [final_result.entry]
            else:
                exits = [final_node.id]
            final_context = FinallyContext(entry=final_node.id, exits=list(exits), targets=set(final_targets))
            self.finally_stack.append(final_context)
            self.finally_contexts.append(final_context)
            final_targets = [final_node.id]

        handler = statement.get("handler")
        catch_entry: Optional[str] = None
        if handler:
            catch_meta = {"op": "Catch", "param": self._catch_param(handler)}
            catch_node = self._create_node("Handler", [handler], catch_meta)
            catch_targets = final_targets if final_context else final_targets
            body_result = self._build_statement(handler.get("body"), catch_targets)
            if body_result.entry:
                self._add_edge(catch_node.id, body_result.entry, "Next")
            catch_entry = catch_node.id

        self.try_stack.append(TryContext(catch_target=catch_entry))

        try_body_targets = final_targets if final_context else self._wrap_targets_with_finally(next_targets)
        if final_context:
            try_body_targets = [final_context.entry]

        block = statement.get("block")
        body_result = self._build_statement(block, try_body_targets)

        try_node = self._create_node("Handler", [statement], {"op": "Try"})
        if body_result.entry:
            self._add_edge(try_node.id, body_result.entry, "Next")
        else:
            self._connect_fallthroughs([try_node.id], try_body_targets, "Next")

        if catch_entry:
            self._add_edge(try_node.id, catch_entry, "Except")

        if final_context:
            self._add_edge(try_node.id, final_context.entry, "Finally")

        self.try_stack.pop()

        if final_context:
            self.finally_stack.pop()

        return BuildResult(entry=try_node.id, fallthroughs=list(final_targets))

    # ------------------------------------------------------------------
    # Labeled / Unknown

    def _build_labeled(self, statement: Dict[str, Any], next_targets: List[str]) -> BuildResult:
        label = statement.get("label", {}).get("name")
        self.label_context_stack.append({})
        prev_pending = self.pending_label
        self.pending_label = label
        body_result = self._build_statement(statement.get("body"), next_targets)
        self.pending_label = prev_pending
        scope = self.label_context_stack.pop()
        if label and scope.get(label) and self.label_context_stack:
            # propagate label mapping to outer scope
            self.label_context_stack[-1][label] = scope[label]

        meta = {"op": "LabeledStatement", "label": label}
        label_node = self._create_node("Linear", [statement], meta)
        if body_result.entry:
            self._add_edge(label_node.id, body_result.entry, "Next")
            fallthroughs = list(body_result.fallthroughs)
        else:
            fallthroughs = [label_node.id]
            self._connect_fallthroughs([label_node.id], next_targets, "Next")
        return BuildResult(entry=label_node.id, fallthroughs=fallthroughs)

    def _build_unknown(self, statement: Dict[str, Any], next_targets: List[str], kind: str) -> BuildResult:
        node = self._create_node(kind, [statement], meta={"op": statement.get("type", "Unknown")})
        routed = self._wrap_targets_with_finally(next_targets)
        self._connect_fallthroughs([node.id], routed, "Next")
        return BuildResult(entry=node.id, fallthroughs=[node.id])

    # ------------------------------------------------------------------
    # Expression helper

    def _build_expression_as_statement(self, expression: Dict[str, Any], next_targets: List[str]) -> BuildResult:
        expr_node = {"type": "ExpressionStatement", "expression": expression, "loc": expression.get("loc"), "range": expression.get("range")}
        return self._build_simple_statement(expr_node, next_targets)

    # ------------------------------------------------------------------
    # Context helpers

    def _register_pending_label(self, break_targets: List[str], continue_targets: List[str]) -> None:
        if self.pending_label is None or not self.label_context_stack:
            return
        scope = self.label_context_stack[-1]
        scope[self.pending_label] = (list(break_targets), list(continue_targets))
        self.pending_label = None

    def _nearest_break_targets(self) -> Optional[List[str]]:
        if not self.break_stack:
            return None
        return list(self.break_stack[-1])

    def _nearest_continue_targets(self) -> Optional[List[str]]:
        if not self.continue_stack:
            return None
        return list(self.continue_stack[-1])

    def _nearest_catch_target(self) -> Optional[str]:
        for context in reversed(self.try_stack):
            if context.catch_target:
                return context.catch_target
        return None

    def _label_break_targets(self, label: str) -> Optional[List[str]]:
        for scope in reversed(self.label_context_stack):
            if label in scope:
                break_targets, _ = scope[label]
                return list(break_targets)
        return None

    def _label_continue_targets(self, label: str) -> Optional[List[str]]:
        for scope in reversed(self.label_context_stack):
            if label in scope:
                _, continue_targets = scope[label]
                return list(continue_targets)
        return None

    # ------------------------------------------------------------------
    # Node / edge helpers

    def _create_node(self, kind: str, ast_nodes: Optional[Iterable[Dict[str, Any]]], span: Optional[Span] = None, meta: Optional[Dict[str, Any]] = None) -> CFGNode:
        node_id = self.factory.new_id()
        ast_list = [node for node in (ast_nodes or []) if node]
        if span is None:
            span = merge_spans(span_from_node(node) for node in ast_list if node)
        text_hash = compute_text_hash(self.source, span) if span else None
        cfg_node = CFGNode(
            id=node_id,
            kind=kind,
            span=span or Span(0, 0, 0, 0, []),
            ast_nodes=ast_list,
            meta=meta or {},
            text_hash=text_hash,
        )
        self.nodes[node_id] = cfg_node
        return cfg_node

    def _add_edge(self, source: Optional[str], target: Optional[str], edge_type: str, label: Optional[str] = None) -> None:
        if not source or not target:
            return
        key = (source, target, edge_type, label)
        if key in self.edge_set:
            return
        self.edge_set.add(key)
        self.edges.append(CFGEdge(source=source, target=target, edge_type=edge_type, label=label))

    def _connect_fallthroughs(self, sources: Iterable[str], targets: Iterable[str], edge_type: str = "Next", label: Optional[str] = None) -> None:
        targets_list = [t for t in targets if t]
        if not targets_list:
            return
        for source in sources:
            for target in targets_list:
                self._add_edge(source, target, edge_type, label)

    def _wrap_targets_with_finally(self, targets: Iterable[str]) -> List[str]:
        current = [t for t in targets if t]
        for context in reversed(self.finally_stack):
            context.targets.update(current)
            current = [context.entry]
        return current

    def _finalize_finally_edges(self) -> None:
        for context in self.finally_contexts:
            targets = [t for t in context.targets if t]
            if not targets:
                continue
            for exit_node in context.exits:
                self._connect_fallthroughs([exit_node], targets, "Next")

    # ------------------------------------------------------------------
    # Utility helpers

    def _catch_param(self, handler: Dict[str, Any]) -> Optional[str]:
        param = handler.get("param")
        if isinstance(param, dict) and param.get("type") == "Identifier":
            return param.get("name")
        return None

    def _snippet(self, node: Optional[Dict[str, Any]], max_len: int = 80) -> str:
        if not node:
            return ""
        node_range = node.get("range")
        if not node_range:
            return node.get("type", "")
        start, end = node_range
        snippet = self.source[start:end]
        snippet = " ".join(snippet.split())
        if len(snippet) > max_len:
            snippet = snippet[: max_len - 3] + "..."
        return snippet


__all__ = ["CFGBuilder"]
"""Build control flow graphs for JavaScript functions based on ESTree ASTs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .structures import CFGEdge, CFGNode, FileCFG, FunctionCFG, Span
from .utils import compute_text_hash, merge_spans, span_from_node


@dataclass
class FunctionLike:
    node: Dict[str, Any]
    name: str
    span: Optional[Span]
    parent: Optional[str] = None


@dataclass
class LoopContext:
    continue_target: str
    break_target: str


@dataclass
class TryContext:
    catch_target: Optional[str]
    finally_entry: Optional[str]


class NodeFactory:
    def __init__(self) -> None:
        self._counter = 0

    def new_id(self) -> str:
        node_id = f"n{self._counter}"
        self._counter += 1
        return node_id


class CFGBuilder:
    """Convert a parsed JavaScript program into per-function CFGs."""

    def __init__(self, file_path: str, source: str, program: Dict[str, Any]) -> None:
        self.file_path = file_path
        self.source = source
        self.program = program

    def build(self) -> FileCFG:
        functions = [self._build_global_function()] + self._build_nested_functions()
        return FileCFG(file_path=self.file_path, functions=functions)

    # ------------------------------------------------------------------
    # Function discovery

    def _build_global_function(self) -> FunctionCFG:
        program_span = span_from_node(self.program)
        function = FunctionLike(node=self.program, name="<global>", span=program_span)
        return self._build_function(function)

    def _build_nested_functions(self) -> List[FunctionCFG]:
        functions: List[FunctionCFG] = []
        for fn in self._collect_function_nodes(self.program):
            functions.append(self._build_function(fn))
        return functions

    def _collect_function_nodes(self, node: Dict[str, Any], parent_name: Optional[str] = None) -> List[FunctionLike]:
        functions: List[FunctionLike] = []
        node_type = node.get("type")

        if node_type in {
            "FunctionDeclaration",
            "FunctionExpression",
            "ArrowFunctionExpression",
        }:
            name = self._extract_function_name(node, parent_name)
            functions.append(
                FunctionLike(
                    node=node,
                    name=name,
                    span=span_from_node(node),
                    parent=parent_name,
                )
            )

        for child in self._iter_child_nodes(node):
            if isinstance(child, dict):
                functions.extend(self._collect_function_nodes(child, parent_name))
            elif isinstance(child, list):
                for element in child:
                    if isinstance(element, dict):
                        functions.extend(self._collect_function_nodes(element, parent_name))
        return functions

    def _extract_function_name(self, node: Dict[str, Any], parent_name: Optional[str]) -> str:
        identifier = node.get("id")
        if identifier and identifier.get("name"):
            return identifier["name"]

        if parent_name:
            return f"<anonymous:{parent_name}>"

        loc = node.get("loc", {}).get("start", {})
        line = loc.get("line", 0)
        column = loc.get("column", 0)
        return f"<anonymous@{line}:{column}>"

    def _iter_child_nodes(self, node: Dict[str, Any]) -> Iterable[Any]:
        for key, value in node.items():
            if key in {"loc", "range", "type", "start", "end"}:
                continue
            yield value

    # ------------------------------------------------------------------
    # Function level CFG

    def _build_function(self, function: FunctionLike) -> FunctionCFG:
        body = function.node.get("body")
        if function.node.get("type") == "Program":
            statements = function.node.get("body", [])
        elif isinstance(body, dict) and body.get("type") == "BlockStatement":
            statements = body.get("body", [])
        else:
            # Arrow function single expression
            statements = [body] if body else []

        self.factory = NodeFactory()
        self.nodes: Dict[str, CFGNode] = {}
        self.edges: List[CFGEdge] = []
        self.loop_stack: List[LoopContext] = []
        self.finally_stack: List[str] = []  # store finally entry node IDs
        self.try_stack: List[TryContext] = []
        self.break_stack: List[str] = []
        self.continue_stack: List[str] = []

        entry_node = self._create_node(
            kind="Entry",
            ast_nodes=[function.node],
            span=function.span,
        )
        exit_node = self._create_node(
            kind="Exit",
            ast_nodes=[function.node],
            span=function.span,
        )
        self.exit_node_id = exit_node.id

        entry_id = entry_node.id
        body_entry = self._build_statement_list(statements, exit_node.id)
        if body_entry:
            self._add_edge(entry_id, body_entry, "Next")
        else:
            self._add_edge(entry_id, exit_node.id, "Next")

        function_span = function.span or merge_spans(node.span for node in self.nodes.values())
        return FunctionCFG(
            func_id=self._new_func_id(function.name),
            name=function.name,
            entry=entry_node.id,
            exits=[exit_node.id],
            nodes=list(self.nodes.values()),
            edges=self.edges,
            range=function_span,
            file_path=self.file_path,
            meta={"isAsync": bool(function.node.get("async")), "isGenerator": bool(function.node.get("generator"))},
        )

    def _new_func_id(self, name: str) -> str:
        safe = name.replace("<", "").replace(">", "").replace(":", "_")
        if not safe:
            safe = "fn"
        return f"f_{hash(safe) & 0xFFFF:X}"

    # ------------------------------------------------------------------
    # Statement handling

    def _build_statement_list(self, statements: Sequence[Dict[str, Any]], next_entry: Optional[str]) -> Optional[str]:
        current_next = next_entry
        entry: Optional[str] = None

        for statement in reversed(statements):
            entry = self._build_statement(statement, current_next)
            current_next = entry

        return entry

    def _build_statement(self, statement: Optional[Dict[str, Any]], next_entry: Optional[str]) -> Optional[str]:
        if not statement:
            return next_entry

        node_type = statement.get("type")

        if node_type == "BlockStatement":
            return self._build_statement_list(statement.get("body", []), next_entry)

        if node_type in {"ExpressionStatement", "VariableDeclaration", "ReturnStatement", "ThrowStatement", "BreakStatement", "ContinueStatement", "DebuggerStatement", "EmptyStatement"}:
            return self._build_simple_statement(statement, next_entry)

        if node_type == "IfStatement":
            return self._build_if(statement, next_entry)

        if node_type in {"WhileStatement", "DoWhileStatement", "ForStatement", "ForInStatement", "ForOfStatement"}:
            return self._build_loop(statement, next_entry)

        if node_type == "SwitchStatement":
            return self._build_switch(statement, next_entry)

        if node_type == "TryStatement":
            return self._build_try(statement, next_entry)

        if node_type == "WithStatement":
            return self._build_unknown(statement, next_entry, kind="Unknown")

        if node_type == "LabeledStatement":
            return self._build_labeled(statement, next_entry)

        # Fallback: treat as linear node
        return self._build_unknown(statement, next_entry, kind="Linear")

    # ------------------------------------------------------------------
    # Node helpers

    def _create_node(
        self,
        kind: str,
        ast_nodes: Optional[Iterable[Dict[str, Any]]] = None,
        span: Optional[Span] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> CFGNode:
        node_id = self.factory.new_id()
        ast_list = list(ast_nodes or [])
        if span is None:
            span = merge_spans(span_from_node(node) for node in ast_list if node)
        text_hash = compute_text_hash(self.source, span) if span else None
        cfg_node = CFGNode(
            id=node_id,
            kind=kind,
            span=span or Span(0, 0, 0, 0, []),
            ast_nodes=ast_list,
            meta=meta or {},
            text_hash=text_hash,
        )
        self.nodes[node_id] = cfg_node
        return cfg_node

    def _add_edge(self, source: Optional[str], target: Optional[str], edge_type: str, label: Optional[str] = None) -> None:
        if not source or not target:
            return
        self.edges.append(CFGEdge(source=source, target=target, edge_type=edge_type, label=label))

    # ------------------------------------------------------------------
    # Simple statements

    def _build_simple_statement(self, statement: Dict[str, Any], next_entry: Optional[str]) -> Optional[str]:
        node_type = statement.get("type")
        kind_map = {
            "ExpressionStatement": "Linear",
            "VariableDeclaration": "Linear",
            "DebuggerStatement": "Linear",
            "EmptyStatement": "Linear",
            "ReturnStatement": "Return",
            "ThrowStatement": "Throw",
            "BreakStatement": "Break",
            "ContinueStatement": "Continue",
        }
        kind = kind_map.get(node_type, "Linear")
        node = self._create_node(kind=kind, ast_nodes=[statement])

        if node_type == "ReturnStatement":
            target = self._wrap_with_finally(self.exit_node_id)
            self._add_edge(node.id, target, "Next")
            return node.id

        if node_type == "ThrowStatement":
            catch_target = self._nearest_catch_target()
            if catch_target:
                self._add_edge(node.id, catch_target, "Except")
            else:
                target = self._wrap_with_finally(self.exit_node_id)
                self._add_edge(node.id, target, "Except")
            return node.id

        if node_type == "BreakStatement":
            target = self._wrap_with_finally(self._nearest_break_target())
            self._add_edge(node.id, target, "Next")
            return node.id

        if node_type == "ContinueStatement":
            target = self._wrap_with_finally(self._nearest_continue_target())
            self._add_edge(node.id, target, "Next")
            return node.id

        # Default fall-through
        target = self._wrap_with_finally(next_entry)
        self._add_edge(node.id, target, "Next")
        return node.id

    # ------------------------------------------------------------------
    # Control structures

    def _build_if(self, statement: Dict[str, Any], next_entry: Optional[str]) -> Optional[str]:
        test = statement.get("test")
        meta = {"op": "IfStatement", "cond": self._extract_snippet(test)}
        branch_node = self._create_node(kind="Branch", ast_nodes=[statement], meta=meta)

        consequent_entry = self._build_statement(statement.get("consequent"), next_entry)
        alternate_entry = self._build_statement(statement.get("alternate"), next_entry)

        if consequent_entry:
            self._add_edge(branch_node.id, consequent_entry, "True", "cond:true")
        else:
            self._add_edge(branch_node.id, self._wrap_with_finally(next_entry), "True", "cond:true")

        if alternate_entry:
            self._add_edge(branch_node.id, alternate_entry, "False", "cond:false")
        else:
            self._add_edge(branch_node.id, self._wrap_with_finally(next_entry), "False", "cond:false")

        return branch_node.id

    def _build_loop(self, statement: Dict[str, Any], next_entry: Optional[str]) -> Optional[str]:
        node_type = statement.get("type")

        if node_type == "WhileStatement":
            return self._build_while(statement, next_entry)
        if node_type == "DoWhileStatement":
            return self._build_do_while(statement, next_entry)
        if node_type == "ForStatement":
            return self._build_for(statement, next_entry)
        if node_type in {"ForInStatement", "ForOfStatement"}:
            return self._build_for_in_of(statement, next_entry)
        return next_entry

    def _build_while(self, statement: Dict[str, Any], next_entry: Optional[str]) -> Optional[str]:
        meta = {"op": "WhileStatement", "cond": self._extract_snippet(statement.get("test"))}
        header = self._create_node("While", [statement], meta=meta)

        loop_context = LoopContext(continue_target=header.id, break_target=next_entry or self.exit_node_id)
        self.loop_stack.append(loop_context)
        self.break_stack.append(loop_context.break_target)
        self.continue_stack.append(loop_context.continue_target)

        body_entry = self._build_statement(statement.get("body"), header.id)

        if body_entry:
            self._add_edge(header.id, body_entry, "True", "cond:true")
        else:
            self._add_edge(header.id, header.id, "True", "cond:true")

        false_target = self._wrap_with_finally(next_entry)
        self._add_edge(header.id, false_target, "False", "cond:false")

        self.loop_stack.pop()
        self.break_stack.pop()
        self.continue_stack.pop()

        return header.id

    def _build_do_while(self, statement: Dict[str, Any], next_entry: Optional[str]) -> Optional[str]:
        meta = {"op": "DoWhileStatement", "cond": self._extract_snippet(statement.get("test"))}
        header = self._create_node("DoWhile", [statement], meta=meta)

        loop_context = LoopContext(continue_target=header.id, break_target=next_entry or self.exit_node_id)
        self.loop_stack.append(loop_context)
        self.break_stack.append(loop_context.break_target)
        self.continue_stack.append(loop_context.continue_target)

        body_entry = self._build_statement(statement.get("body"), header.id)
        if body_entry:
            self._add_edge(header.id, body_entry, "Next")

        false_target = self._wrap_with_finally(next_entry)
        self._add_edge(header.id, false_target, "False", "cond:false")

        self.loop_stack.pop()
        self.break_stack.pop()
        self.continue_stack.pop()

        return header.id

    def _build_for(self, statement: Dict[str, Any], next_entry: Optional[str]) -> Optional[str]:
        init = statement.get("init")
        test = statement.get("test")
        update = statement.get("update")

        test_meta = {"op": "ForStatement", "cond": self._extract_snippet(test)}
        header = self._create_node("For", [statement], meta=test_meta)

        loop_context = LoopContext(continue_target=header.id, break_target=next_entry or self.exit_node_id)
        self.loop_stack.append(loop_context)
        self.break_stack.append(loop_context.break_target)
        self.continue_stack.append(loop_context.continue_target)

        body_entry = self._build_statement(statement.get("body"), header.id)

        if body_entry:
            self._add_edge(header.id, body_entry, "True", "cond:true")
        else:
            self._add_edge(header.id, header.id, "True", "cond:true")

        false_target = self._wrap_with_finally(next_entry)
        self._add_edge(header.id, false_target, "False", "cond:false")

        if update:
            update_entry = self._build_statement(update, header.id)
            if body_entry:
                self._add_edge(body_entry, update_entry, "Next")

        if init:
            init_entry = self._build_statement(init, header.id)
            self.loop_stack.pop()
            self.break_stack.pop()
            self.continue_stack.pop()
            return init_entry

        self.loop_stack.pop()
        self.break_stack.pop()
        self.continue_stack.pop()
        return header.id

    def _build_for_in_of(self, statement: Dict[str, Any], next_entry: Optional[str]) -> Optional[str]:
        op = statement.get("type")
        await_meta = {"op": op, "left": self._extract_snippet(statement.get("left")), "right": self._extract_snippet(statement.get("right"))}
        header = self._create_node("ForEach", [statement], meta=await_meta)

        loop_context = LoopContext(continue_target=header.id, break_target=next_entry or self.exit_node_id)
        self.loop_stack.append(loop_context)
        self.break_stack.append(loop_context.break_target)
        self.continue_stack.append(loop_context.continue_target)

        body_entry = self._build_statement(statement.get("body"), header.id)
        if body_entry:
            self._add_edge(header.id, body_entry, "True")
        self._add_edge(header.id, self._wrap_with_finally(next_entry), "False")

        self.loop_stack.pop()
        self.break_stack.pop()
        self.continue_stack.pop()

        return header.id

    def _build_switch(self, statement: Dict[str, Any], next_entry: Optional[str]) -> Optional[str]:
        meta = {"op": "SwitchStatement", "discriminant": self._extract_snippet(statement.get("discriminant"))}
        switch_node = self._create_node("Switch", [statement], meta=meta)

        break_target = next_entry or self.exit_node_id
        self.break_stack.append(break_target)

        cases: List[Dict[str, Any]] = statement.get("cases", [])
        fallthrough_target = self._wrap_with_finally(next_entry)

        for index, case in enumerate(cases):
            test = case.get("test")
            label = f"case:{self._extract_snippet(test) if test else 'default'}"
            case_entry = self._build_statement_list(case.get("consequent", []), fallthrough_target)
            edge_type = "Case" if test else "Default"
            self._add_edge(switch_node.id, case_entry or fallthrough_target, edge_type, label)

            # Fall-through to next case if no break
            if index < len(cases) - 1 and case_entry:
                next_case_entry = self._build_statement_list(cases[index + 1].get("consequent", []), fallthrough_target)
                if next_case_entry:
                    self._add_edge(case_entry, next_case_entry, "Next", "fall-through")

        self.break_stack.pop()
        return switch_node.id

    def _build_try(self, statement: Dict[str, Any], next_entry: Optional[str]) -> Optional[str]:
        meta = {"op": "Try"}
        try_node = self._create_node("Handler", [statement], meta=meta)

        handler = statement.get("handler")
        finalizer = statement.get("finalizer")

        final_next = self._wrap_with_finally(next_entry)
        finally_entry: Optional[str] = None
        if finalizer:
            finally_entry = self._build_statement(finalizer, final_next)

        catch_entry: Optional[str] = None
        if handler:
            catch_meta = {"op": "Catch", "param": self._extract_catch_param(handler)}
            catch_node = self._create_node("Handler", [handler], meta=catch_meta)
            catch_entry = self._build_statement(handler.get("body"), finally_entry or final_next)
            if catch_entry:
                self._add_edge(catch_node.id, catch_entry, "Next")
            catch_entry = catch_node.id

        self.try_stack.append(TryContext(catch_target=catch_entry, finally_entry=finally_entry))
        if finalizer and finally_entry:
            self.finally_stack.append(finally_entry)

        try_entry = self._build_statement(statement.get("block"), finally_entry or final_next)
        if try_entry:
            self._add_edge(try_node.id, try_entry, "Next")

        if catch_entry:
            self._add_edge(try_node.id, catch_entry, "Except")

        self.try_stack.pop()
        if finalizer and finally_entry and self.finally_stack:
            self.finally_stack.pop()

        if finally_entry:
            self._add_edge(try_node.id, finally_entry, "Finally")

        return try_node.id

    def _build_unknown(self, statement: Dict[str, Any], next_entry: Optional[str], kind: str) -> Optional[str]:
        node = self._create_node(kind=kind, ast_nodes=[statement], meta={"op": statement.get("type", "Unknown")})
        target = self._wrap_with_finally(next_entry)
        self._add_edge(node.id, target, "Next")
        return node.id

    def _build_labeled(self, statement: Dict[str, Any], next_entry: Optional[str]) -> Optional[str]:
        label = statement.get("label", {}).get("name")
        meta = {"op": "LabeledStatement", "label": label}
        node = self._create_node(kind="Linear", ast_nodes=[statement], meta=meta)
        body_entry = self._build_statement(statement.get("body"), next_entry)
        if body_entry:
            self._add_edge(node.id, body_entry, "Next")
        else:
            self._add_edge(node.id, self._wrap_with_finally(next_entry), "Next")
        return node.id

    # ------------------------------------------------------------------
    # Context helpers

    def _wrap_with_finally(self, target: Optional[str]) -> Optional[str]:
        if not target:
            return target
        if not self.finally_stack:
            return target
        # Connect through the innermost finally handler
        finally_entry = self.finally_stack[-1]
        self._add_edge(finally_entry, target, "Next")
        return finally_entry

    def _nearest_catch_target(self) -> Optional[str]:
        for context in reversed(self.try_stack):
            if context.catch_target:
                return context.catch_target
        return None

    def _nearest_break_target(self) -> Optional[str]:
        if not self.break_stack:
            return self.exit_node_id
        return self.break_stack[-1]

    def _nearest_continue_target(self) -> Optional[str]:
        if not self.continue_stack:
            return self.exit_node_id
        return self.continue_stack[-1]

    # ------------------------------------------------------------------
    # Misc helpers

    def _extract_snippet(self, node: Optional[Dict[str, Any]], max_len: int = 80) -> str:
        if not node:
            return ""
        node_range = node.get("range")
        if not node_range:
            return node.get("type", "")
        start, end = node_range
        snippet = self.source[start:end]
        snippet = " ".join(snippet.split())
        if len(snippet) > max_len:
            snippet = snippet[: max_len - 3] + "..."
        return snippet

    def _extract_catch_param(self, handler: Dict[str, Any]) -> Optional[str]:
        param = handler.get("param")
        if isinstance(param, dict) and param.get("type") == "Identifier":
            return param.get("name")
        return None


__all__ = ["CFGBuilder"]

