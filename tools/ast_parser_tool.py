"""
LangChain Tool wrapper for AST Parser
"""

from langchain.tools import BaseTool
from typing import Optional
import json
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.ast_parser import parse_code


class ASTParserTool(BaseTool):
    name: str = "parse_ast"
    description: str = """
    Parse Python source code and extract security-relevant structural information.

    Input: Python source code as a string OR file path ending with .py

    Output: JSON object containing:
    - functions: List of functions with params, calls, assignments, control flow
    - global_assigns: Global variables (useful for detecting hardcoded secrets)
    - imports: Imported modules

    The tool automatically detects:
    - SQL injection patterns (string concatenation and f-strings)
    - Dangerous function calls (eval, exec, etc.)
    - Hardcoded secrets in global variables
    - Function parameters used in string concatenation

    Use this tool when you need to:
    - Understand the structure of Python code
    - Find SQL injection vulnerabilities quickly
    - Identify dangerous function calls
    - Detect hardcoded credentials
    - Analyze function call patterns

    Example usage scenarios:
    - "What functions are defined in this file?"
    - "Does this code have SQL injection vulnerabilities?"
    - "Are there any hardcoded API keys?"
    - "Which functions call dangerous methods like eval()?"
    """

    def _run(self, code_or_path: str) -> str:
        """
        Execute the AST parser

        Args:
            code_or_path: Python source code or file path

        Returns:
            JSON string with analysis results
        """
        # Check if input is a file path
        if code_or_path.strip().endswith('.py') and os.path.exists(code_or_path):
            try:
                with open(code_or_path, 'r', encoding='utf-8') as f:
                    code = f.read()
            except Exception as e:
                return json.dumps({"error": f"Failed to read file: {e}"})
        else:
            code = code_or_path

        # Parse the code
        results = parse_code(code)

        # Format output for LLM
        return json.dumps(results, indent=2)

    async def _arun(self, code_or_path: str) -> str:
        """Async version (calls sync version)"""
        return self._run(code_or_path)
