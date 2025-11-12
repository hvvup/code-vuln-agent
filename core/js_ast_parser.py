"""JavaScript AST parser for extracting security-relevant information."""

import json
import re
from typing import Dict, Any, List, Optional

from .parser import JavaScriptParser, ParserOptions


def parse_javascript(code: str) -> Dict[str, Any]:
    """
    Parse JavaScript code and extract security-relevant structural information.
    
    Args:
        code: JavaScript source code as string
        
    Returns:
        Dictionary containing:
        - functions: List of functions with params, calls, assignments
        - variables: Global variable declarations
        - imports: Imported modules
        - vulnerabilities: Automatically detected security issues
    """
    parser = JavaScriptParser(ParserOptions())
    
    try:
        parsed = parser.parse_code(code)
        ast = parsed.ast
        
        result = {
            "functions": [],
            "variables": [],
            "imports": [],
            "vulnerabilities": [],
        }
        
        # Extract information from AST
        _extract_from_ast(ast, result, code)
        
        return result
        
    except Exception as e:
        return {
            "error": str(e),
            "functions": [],
            "variables": [],
            "imports": [],
            "vulnerabilities": [],
        }


def _extract_from_ast(ast: Dict[str, Any], result: Dict[str, Any], source_code: str):
    """Extract functions, variables, imports, and vulnerabilities from AST."""
    if not isinstance(ast, dict):
        return
    
    body = ast.get("body", [])
    
    for node in body:
        node_type = node.get("type", "")
        
        # Extract imports
        if node_type == "ImportDeclaration":
            _extract_import(node, result)
        
        # Extract variable declarations
        elif node_type == "VariableDeclaration":
            _extract_variables(node, result, source_code)
        
        # Extract function declarations
        elif node_type == "FunctionDeclaration":
            _extract_function(node, result, source_code)
        
        # Extract export declarations
        elif node_type == "ExportNamedDeclaration" or node_type == "ExportDefaultDeclaration":
            declaration = node.get("declaration")
            if declaration:
                decl_type = declaration.get("type", "")
                if decl_type == "FunctionDeclaration":
                    _extract_function(declaration, result, source_code)
                elif decl_type == "VariableDeclaration":
                    _extract_variables(declaration, result, source_code)


def _extract_import(node: Dict[str, Any], result: Dict[str, Any]):
    """Extract import information."""
    source = node.get("source", {})
    if source:
        import_path = source.get("value", "")
        specifiers = node.get("specifiers", [])
        
        imported_items = []
        for spec in specifiers:
            if spec.get("type") == "ImportSpecifier":
                imported_items.append(spec.get("imported", {}).get("name", ""))
        
        result["imports"].append({
            "path": import_path,
            "items": imported_items,
        })


def _extract_variables(node: Dict[str, Any], result: Dict[str, Any], source_code: str):
    """Extract variable declarations and check for hardcoded secrets."""
    declarations = node.get("declarations", [])
    
    for decl in declarations:
        var_id = decl.get("id", {})
        var_name = var_id.get("name", "")
        init = decl.get("init")
        
        var_info = {
            "name": var_name,
            "type": node.get("kind", "var"),  # var, let, const
        }
        
        # Check for hardcoded secrets
        if init:
            init_type = init.get("type", "")
            if init_type == "Literal":
                value = init.get("value", "")
                if _is_secret(var_name, value):
                    result["vulnerabilities"].append({
                        "type": "hardcoded_secret",
                        "variable": var_name,
                        "line": init.get("loc", {}).get("start", {}).get("line"),
                        "message": f"Potential hardcoded secret in variable '{var_name}'",
                    })
                var_info["value"] = str(value)[:100]  # Truncate long values
        
        result["variables"].append(var_info)


def _extract_function(node: Dict[str, Any], result: Dict[str, Any], source_code: str):
    """Extract function information and detect vulnerabilities."""
    func_id = node.get("id", {})
    func_name = func_id.get("name", "") if func_id else "anonymous"
    
    params = []
    for param in node.get("params", []):
        param_type = param.get("type", "")
        if param_type == "Identifier":
            params.append(param.get("name", ""))
        elif param_type == "RestElement":
            params.append("..." + param.get("argument", {}).get("name", ""))
    
    func_body = node.get("body", {})
    calls = []
    assignments = []
    
    # Extract function body information
    _extract_from_body(func_body, calls, assignments, source_code, result, func_name)
    
    func_info = {
        "name": func_name,
        "params": params,
        "calls": calls,
        "assignments": assignments,
        "line": node.get("loc", {}).get("start", {}).get("line"),
    }
    
    result["functions"].append(func_info)


def _extract_from_body(
    body: Dict[str, Any],
    calls: List[str],
    assignments: List[str],
    source_code: str,
    result: Dict[str, Any],
    func_name: str,
):
    """Recursively extract calls and assignments from function body."""
    if not isinstance(body, dict):
        return
    
    body_type = body.get("type", "")
    
    if body_type == "BlockStatement":
        statements = body.get("body", [])
        for stmt in statements:
            _extract_from_statement(stmt, calls, assignments, source_code, result, func_name)
    else:
        _extract_from_statement(body, calls, assignments, source_code, result, func_name)


def _extract_from_statement(
    stmt: Dict[str, Any],
    calls: List[str],
    assignments: List[str],
    source_code: str,
    result: Dict[str, Any],
    func_name: str,
):
    """Extract information from a statement."""
    if not isinstance(stmt, dict):
        return
    
    stmt_type = stmt.get("type", "")
    
    # Extract function calls
    if stmt_type == "ExpressionStatement":
        expr = stmt.get("expression", {})
        expr_type = expr.get("type", "")
        
        if expr_type == "CallExpression":
            callee = expr.get("callee", {})
            call_name = _get_call_name(callee)
            if call_name:
                calls.append(call_name)
                # Check for dangerous calls
                _check_dangerous_call(call_name, expr, result, func_name, stmt)
        
        elif expr_type == "AssignmentExpression":
            left = expr.get("left", {})
            if left.get("type") == "Identifier":
                assignments.append(left.get("name", ""))
    
    # Recursively process nested structures
    elif stmt_type == "IfStatement":
        _extract_from_body(stmt.get("consequent", {}), calls, assignments, source_code, result, func_name)
        alternate = stmt.get("alternate")
        if alternate:
            _extract_from_body(alternate, calls, assignments, source_code, result, func_name)
    
    elif stmt_type == "ForStatement" or stmt_type == "WhileStatement" or stmt_type == "DoWhileStatement":
        _extract_from_body(stmt.get("body", {}), calls, assignments, source_code, result, func_name)
    
    elif stmt_type == "ReturnStatement":
        argument = stmt.get("argument", {})
        if argument.get("type") == "CallExpression":
            callee = argument.get("callee", {})
            call_name = _get_call_name(callee)
            if call_name:
                calls.append(call_name)
                _check_dangerous_call(call_name, argument, result, func_name, stmt)


def _get_call_name(callee: Dict[str, Any]) -> Optional[str]:
    """Extract function/method name from callee."""
    if not isinstance(callee, dict):
        return None
    
    callee_type = callee.get("type", "")
    
    if callee_type == "Identifier":
        return callee.get("name", "")
    elif callee_type == "MemberExpression":
        obj = callee.get("object", {})
        prop = callee.get("property", {})
        
        obj_name = _get_call_name(obj) if obj.get("type") == "MemberExpression" else obj.get("name", "")
        prop_name = prop.get("name", "")
        
        if obj_name and prop_name:
            return f"{obj_name}.{prop_name}"
        return prop_name
    
    return None


def _check_dangerous_call(
    call_name: str,
    call_expr: Dict[str, Any],
    result: Dict[str, Any],
    func_name: str,
    stmt: Dict[str, Any],
):
    """Check if a function call is potentially dangerous."""
    call_lower = call_name.lower()
    
    # Dangerous function patterns
    dangerous_patterns = {
        "eval": "Code injection via eval()",
        "function(": "Code injection via Function constructor",
        "settimeout": "Code injection via setTimeout with string",
        "setinterval": "Code injection via setInterval with string",
        "innerhtml": "XSS via innerHTML",
        "dangerouslysetinnerhtml": "XSS via dangerouslySetInnerHTML",
        "document.write": "XSS via document.write",
        "document.writeln": "XSS via document.writeln",
    }
    
    for pattern, message in dangerous_patterns.items():
        if pattern in call_lower:
            result["vulnerabilities"].append({
                "type": "dangerous_call",
                "function": func_name,
                "call": call_name,
                "line": stmt.get("loc", {}).get("start", {}).get("line"),
                "message": message,
            })
            break
    
    # Check for SQL injection patterns
    args = call_expr.get("arguments", [])
    for arg in args:
        if arg.get("type") == "TemplateLiteral":
            # Check if template contains SQL keywords
            quasis = arg.get("quasis", [])
            for quasi in quasis:
                value = quasi.get("value", {}).get("raw", "")
                if _contains_sql_keywords(value):
                    result["vulnerabilities"].append({
                        "type": "sql_injection",
                        "function": func_name,
                        "call": call_name,
                        "line": stmt.get("loc", {}).get("start", {}).get("line"),
                        "message": "Potential SQL injection in template literal",
                    })
                    break


def _contains_sql_keywords(text: str) -> bool:
    """Check if text contains SQL keywords."""
    sql_keywords = [
        "select", "insert", "update", "delete", "drop", "create",
        "alter", "exec", "execute", "union", "where", "from",
    ]
    text_lower = text.lower()
    return any(keyword in text_lower for keyword in sql_keywords)


def _is_secret(var_name: str, value: Any) -> bool:
    """Check if a variable might contain a hardcoded secret."""
    var_lower = var_name.lower()
    secret_indicators = ["key", "secret", "password", "token", "api", "auth", "credential"]
    
    if any(indicator in var_lower for indicator in secret_indicators):
        value_str = str(value)
        # Check if it looks like a secret (long string, contains special chars, etc.)
        if len(value_str) > 10 and not value_str.startswith("http"):
            return True
    
    return False


__all__ = ["parse_javascript"]

