"""
LangChain Tool wrapper for JavaScript AST Parser
"""

from langchain.tools import BaseTool
from typing import Optional
import json
import os
import sys
import re

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# [수정 1] parse_javascript 함수를 import 합니다.
from core.js_ast_parser import parse_javascript


class CustomJSONEncoder(json.JSONEncoder):
    """JSON으로 변환 불가능한 객체를 문자열로 처리하는 인코더"""

    def default(self, obj):
        try:
            if isinstance(obj, re.Pattern):
                return obj.pattern
            if isinstance(obj, set):
                return list(obj)
            return str(obj)
        except:
            return super().default(obj)


class JavaScriptASTParserTool(BaseTool):  # 클래스 이름도 명확하게 변경 추천
    name: str = "parse_javascript_ast"  # 에이전트가 인식할 도구 이름
    description: str = """
    Parse JavaScript/TypeScript source code and extract security-relevant structural information.

    Input: JavaScript source code as a string OR file path ending with .js or .ts

    Output: JSON object containing:
    - functions: List of functions with params, calls, assignments
    - variables: Global variable declarations
    - imports: Imported modules
    - vulnerabilities: Automatically detected security issues (hardcoded secrets, dangerous calls)
    """

    def _run(self, code_or_path: str) -> str:
        """
        Execute the AST parser

        Args:
            code_or_path: JavaScript source code or file path

        Returns:
            JSON string with analysis results
        """
        # [수정 2] .js 또는 .ts 파일인지 확인합니다.
        if (
            code_or_path.strip().endswith(".js") or code_or_path.strip().endswith(".ts")
        ) and os.path.exists(code_or_path):
            try:
                with open(code_or_path, "r", encoding="utf-8") as f:
                    code = f.read()
            except Exception as e:
                return json.dumps({"error": f"Failed to read file: {e}"})
        else:
            code = code_or_path

        # Parse the code
        try:
            # [수정 3] 가져온 parse_javascript 함수를 사용합니다.
            results = parse_javascript(code)

            # Format output for LLM using CustomJSONEncoder
            return json.dumps(results, indent=2, cls=CustomJSONEncoder)

        except Exception as e:
            return json.dumps({"error": f"Parsing failed: {str(e)}"})

    async def _arun(self, code_or_path: str) -> str:
        """Async version (calls sync version)"""
        return self._run(code_or_path)
