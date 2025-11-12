import os
from langchain.tools import BaseTool
from pydantic import BaseModel, Field
from typing import Optional
from core.codeql_docker_executor import CodeQLDockerExecutor
from core.codeql_local_executor import CodeQLLocalExecutor


class CodeQLToolInput(BaseModel):
    """
    Input schema for running CodeQL static analysis on a local source file or repository.
    """

    source_file: Optional[str] = Field(
        default=None,
        description="Path to the local source file to analyze (use this OR repository_path, not both)",
    )
    repository_path: Optional[str] = Field(
        default=None,
        description="Path to the repository root directory to analyze (use this OR source_file, not both)",
    )
    query_suite: Optional[str] = Field(
        default="javascript-security-extended.qls",
        description="Optional CodeQL query suite to use (default: javascript-security-extended.qls)",
    )
    language: Optional[str] = Field(
        default="javascript",
        description="CodeQL language to analyze (default: javascript). Only used when repository_path is provided.",
    )


class CodeQLTool(BaseTool):
    """
    LangChain tool for executing CodeQL analysis.

    Automatically selects execution mode:
    - Local mode: If CODEQL_CLI_PATH environment variable is set
    - Docker mode: Otherwise, uses Docker container

    Handles database creation and returns a SARIF report path.
    Supports both single file and repository-level analysis.
    """

    name: str = "codeql_auto_analyze"
    description: str = (
        "Run CodeQL static analysis on a local JavaScript file or entire repository to detect known vulnerability patterns. "
        "Returns the file path to a SARIF report containing the findings. "
        "Use this as the first step in analysis to identify potential security issues like XSS, SQLi, "
        "command injection, path traversal, and other common vulnerabilities. "
        "The tool accepts either a single file path (source_file) or a repository root directory (repository_path). "
        "When analyzing a repository, it will scan all files in that directory. "
        "Automatically creates a CodeQL database for analysis. "
        "Execution mode (local vs Docker) is automatically determined by environment configuration."
    )
    args_schema: type[BaseModel] = CodeQLToolInput

    def _run(
        self,
        source_file: Optional[str] = None,
        repository_path: Optional[str] = None,
        query_suite: Optional[str] = "javascript-security-extended.qls",
        language: Optional[str] = "javascript",
    ):
        """
        Executes CodeQL analysis using local CLI or Docker based on configuration.

        Checks CODEQL_CLI_PATH environment variable:
        - If set: Uses local CodeQL CLI installation
        - If not set: Uses Docker-based execution

        Args:
            source_file: Path to a single file to analyze
            repository_path: Path to repository root directory to analyze
            query_suite: CodeQL query suite to use
            language: CodeQL language (only used for repository analysis)
        """
        # Validate input
        if not source_file and not repository_path:
            raise ValueError("Either source_file or repository_path must be provided")
        if source_file and repository_path:
            raise ValueError("Provide either source_file OR repository_path, not both")

        codeql_cli_path = os.getenv("CODEQL_CLI_PATH")

        if codeql_cli_path:
            # Use local CodeQL CLI
            print(f"Using local CodeQL CLI mode")
            executor = CodeQLLocalExecutor(codeql_path=codeql_cli_path)
        else:
            # Fall back to Docker mode
            print(f"Using Docker-based CodeQL mode")
            executor = CodeQLDockerExecutor()

        # Route to appropriate method
        if repository_path:
            sarif_path = executor.analyze_repository(
                repository_path=repository_path,
                query_suite=query_suite,
                language=language,
            )
        else:
            sarif_path = executor.analyze_file(
                source_file=source_file,
                query_suite=query_suite,
            )
        return sarif_path

    async def _arun(self, *args, **kwargs):
        raise NotImplementedError("Async not supported yet.")
