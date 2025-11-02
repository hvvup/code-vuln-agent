from langchain.tools import BaseTool
from pydantic import BaseModel, Field
from typing import Optional
from core.codeql_docker_executor import CodeQLDockerExecutor


class CodeQLToolInput(BaseModel):
    """
    Input schema for running CodeQL static analysis on a local source file.
    """

    source_file: str = Field(
        ..., description="Path to the local source file to analyze"
    )
    query_suite: Optional[str] = Field(
        default="javascript-security-extended.qls",
        description="Optional CodeQL query suite to use (default: javascript-security-extended.qls)",
    )


class CodeQLTool(BaseTool):
    """
    LangChain tool for executing CodeQL analysis inside Docker.
    This version automatically handles DB creation and returns a SARIF report path.
    """

    name: str = "codeql_auto_analyze"
    description: str = (
        "Run CodeQL static analysis on a local JavaScript file to detect known vulnerability patterns. "
        "Executes CodeQL in Docker and returns the file path to a SARIF report containing the findings. "
        "Use this as the first step in analysis to identify potential security issues like XSS, SQLi, "
        "command injection, path traversal, and other common vulnerabilities. "
        "The tool accepts an absolute file path and automatically creates a CodeQL database for analysis."
    )
    args_schema: type[BaseModel] = CodeQLToolInput

    def _run(
        self,
        source_file: str,
        query_suite: Optional[str] = "javascript-security-extended.qls",
    ):
        """
        Executes CodeQL analysis through the Docker-based executor.
        """
        executor = CodeQLDockerExecutor()
        sarif_path = executor.analyze_file(
            source_file=source_file,
            query_suite="javascript-security-extended.qls",
        )
        return sarif_path

    async def _arun(self, *args, **kwargs):
        raise NotImplementedError("Async not supported yet.")
