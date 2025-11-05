import os
from langchain.tools import BaseTool
from pydantic import BaseModel, Field
from typing import Optional
from core.codeql_docker_executor import CodeQLDockerExecutor
from core.codeql_local_executor import CodeQLLocalExecutor


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
    database_path: Optional[str] = Field(
        default=None,
        description="Optional path to existing CodeQL database. If provided, skips database creation for faster analysis. "
        "If not provided, checks CODEQL_DATABASE_PATH environment variable, then creates a new database.",
    )


class CodeQLTool(BaseTool):
    """
    LangChain tool for executing CodeQL analysis.

    Automatically selects execution mode:
    - Local mode: If CODEQL_CLI_PATH environment variable is set
    - Docker mode: Otherwise, uses Docker container

    Handles database creation and returns a SARIF report path.
    """

    name: str = "codeql_auto_analyze"
    description: str = (
        "Run CodeQL static analysis on a local JavaScript file to detect known vulnerability patterns. "
        "Returns the file path to a SARIF report containing the findings. "
        "Use this as the first step in analysis to identify potential security issues like XSS, SQLi, "
        "command injection, path traversal, and other common vulnerabilities. "
        "The tool accepts an absolute file path and automatically creates a CodeQL database for analysis. "
        "Execution mode (local vs Docker) is automatically determined by environment configuration."
    )
    args_schema: type[BaseModel] = CodeQLToolInput

    def _run(
        self,
        source_file: str,
        query_suite: Optional[str] = "javascript-security-extended.qls",
        database_path: Optional[str] = None,
    ):
        """
        Executes CodeQL analysis using local CLI or Docker based on configuration.

        Checks CODEQL_CLI_PATH environment variable:
        - If set: Uses local CodeQL CLI installation
        - If not set: Uses Docker-based execution

        If database_path is provided or CODEQL_DATABASE_PATH is set, uses existing database.
        """
        codeql_cli_path = os.getenv("CODEQL_CLI_PATH")

        if codeql_cli_path:
            # Use local CodeQL CLI
            print(f"Using local CodeQL CLI mode")
            executor = CodeQLLocalExecutor(codeql_path=codeql_cli_path)
        else:
            # Fall back to Docker mode
            print(f"Using Docker-based CodeQL mode")
            executor = CodeQLDockerExecutor()

        sarif_path = executor.analyze_file(
            source_file=source_file,
            query_suite=query_suite,
            database_path=database_path,
        )
        return sarif_path

    async def _arun(self, *args, **kwargs):
        raise NotImplementedError("Async not supported yet.")
