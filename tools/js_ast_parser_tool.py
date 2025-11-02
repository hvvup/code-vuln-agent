"""
LangChain Tool wrapper for JavaScript AST Parser
"""

from langchain.tools import BaseTool
from typing import Optional
import json
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.js_ast_parser import parse_javascript


class JavaScriptASTParserTool(BaseTool):
    name: str = "parse_javascript_ast"
    description: str = """
    Parse JavaScript/TypeScript source code and extract security-relevant structural information.

    Input: JavaScript/TypeScript source code as a string OR file path ending with .js/.ts/.jsx/.tsx

    Output: JSON object containing:
    - functions: List of functions with params, calls, assignments
    - variables: Global variable declarations
    - imports: Imported modules
    - vulnerabilities: Automatically detected security issues

    The tool automatically detects:
    - SQL injection patterns (template literals with SQL keywords)
    - XSS vulnerabilities (innerHTML, dangerouslySetInnerHTML, document.write)
    - Dangerous function calls (eval, Function constructor, setTimeout/setInterval with strings)
    - Hardcoded secrets in variables (API keys, passwords, tokens)

    Use this tool when you need to:
    - Understand the structure of JavaScript/TypeScript code
    - Find SQL injection vulnerabilities quickly
    - Identify XSS attack vectors
    - Detect dangerous function calls
    - Discover hardcoded credentials
    - Analyze function call patterns and data flow

    Example usage scenarios:
    - "What functions are defined in this JavaScript file?"
    - "Does this code have SQL injection vulnerabilities?"
    - "Are there any XSS risks with innerHTML?"
    - "Which functions use eval() or similar dangerous APIs?"
    - "Are there hardcoded API keys or secrets?"

    IMPORTANT FOR CONTEXT-AWARE ANALYSIS:
    - This tool provides structural information and basic pattern detection
    - For deeper analysis, combine results with code flow understanding
    - Consider how user input flows through the application
    - Check if sanitization/validation exists before risky operations
    - Look for missing error handling or security checks
    """

    def _run(self, code_or_path: str) -> str:
        """
        Execute the JavaScript AST parser

        Args:
            code_or_path: JavaScript source code or file path

        Returns:
            JSON string with analysis results
        """
        # Check if input is a file path
        file_extensions = ('.js', '.jsx', '.ts', '.tsx', '.mjs')
        if any(code_or_path.strip().endswith(ext) for ext in file_extensions):
            if os.path.exists(code_or_path):
                try:
                    with open(code_or_path, 'r', encoding='utf-8') as f:
                        code = f.read()
                except Exception as e:
                    return json.dumps({"error": f"Failed to read file: {e}"})
            else:
                code = code_or_path
        else:
            code = code_or_path

        # Parse the code
        results = parse_javascript(code)

        # Format output for LLM
        return json.dumps(results, indent=2)

    async def _arun(self, code_or_path: str) -> str:
        """Async version (calls sync version)"""
        return self._run(code_or_path)
