"""Local CodeQL executor for running CodeQL analysis without Docker."""

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional


class CodeQLLocalExecutor:
    """
    Runs CodeQL static analysis using a locally installed CodeQL CLI.
    Automatically handles database creation and query execution.

    Requires CODEQL_CLI_PATH environment variable to be set.
    """

    def __init__(self, codeql_path: Optional[str] = None):
        """
        Initialize CodeQL local executor.

        Args:
            codeql_path: Path to CodeQL CLI executable. If None, reads from CODEQL_CLI_PATH env var.

        Raises:
            RuntimeError: If CodeQL CLI path is not provided or not found.
        """
        self.codeql_path = codeql_path or os.getenv("CODEQL_CLI_PATH")

        if not self.codeql_path:
            raise RuntimeError(
                "CodeQL CLI path not specified. Set CODEQL_CLI_PATH environment variable "
                "or pass codeql_path parameter."
            )

        self.codeql_path = Path(self.codeql_path).resolve()

        if not self.codeql_path.exists():
            raise RuntimeError(
                f"CodeQL CLI not found at: {self.codeql_path}\n"
                f"Please install CodeQL CLI or update CODEQL_CLI_PATH."
            )

        # Verify it's executable
        self._verify_codeql()

    def _verify_codeql(self) -> None:
        """Verify that CodeQL CLI is accessible and working."""
        try:
            result = subprocess.run(
                [str(self.codeql_path), "version"],
                capture_output=True,
                text=True,
                check=True,
            )
            version = result.stdout.strip().split('\n')[0]
            print(f"✓ Using local CodeQL: {version}")
        except subprocess.CalledProcessError as e:
            raise RuntimeError(
                f"Failed to execute CodeQL CLI at {self.codeql_path}:\n{e.stderr}"
            )
        except FileNotFoundError:
            raise RuntimeError(
                f"CodeQL CLI not found or not executable: {self.codeql_path}"
            )

    def analyze_file(
        self,
        source_file: str,
        query_suite: str = "javascript-security-extended.qls",
    ) -> str:
        """
        Analyze a JavaScript file for vulnerabilities.

        Args:
            source_file: Path to the JavaScript file to analyze
            query_suite: CodeQL query suite to use (default: javascript-security-extended.qls)

        Returns:
            Path to the generated SARIF report

        Raises:
            FileNotFoundError: If source file doesn't exist
            RuntimeError: If CodeQL commands fail
        """
        src_path = Path(source_file).resolve()
        if not src_path.exists():
            raise FileNotFoundError(f"❌ Source file not found: {src_path}")

        # Create temporary directories for database and output
        work_dir = Path(tempfile.mkdtemp())
        db_dir = work_dir / "codeql-db"
        out_dir = work_dir / "out"
        out_dir.mkdir(parents=True, exist_ok=True)

        # Helper to run commands with better error reporting
        def run_cmd(cmd: list[str], step_name: str) -> None:
            try:
                completed = subprocess.run(
                    cmd,
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    env=os.environ.copy(),
                )
                # Show stdout if there's useful info
                if completed.stdout.strip():
                    print(completed.stdout.strip())
            except subprocess.CalledProcessError as e:
                # Check for missing extractor error
                if "no CodeQL extractor named" in e.stderr.lower():
                    raise RuntimeError(
                        f"❌ CodeQL extractor for JavaScript not found.\n\n"
                        f"You downloaded CodeQL CLI only, but extractors are needed to create databases.\n\n"
                        f"SOLUTION: Download CodeQL Bundle (includes CLI + extractors + queries):\n"
                        f"  1. Visit: https://github.com/github/codeql-action/releases\n"
                        f"  2. Download: codeql-bundle-win64.tar.gz (or your platform)\n"
                        f"  3. Extract to a folder (e.g., D:\\codeql-bundle\\)\n"
                        f"  4. Update .env: CODEQL_CLI_PATH=D:\\codeql-bundle\\codeql\\codeql.exe\n\n"
                        f"ALTERNATIVE: Use Docker mode (no installation required):\n"
                        f"  - Comment out CODEQL_CLI_PATH in .env file\n"
                        f"  - Ensure Docker is running\n"
                    ) from e

                # Generic error message
                msg = (
                    f"{step_name} failed (exit code {e.returncode}).\n"
                    f"Command: {' '.join(cmd)}\n"
                    f"stdout:\n{e.stdout}\n"
                    f"stderr:\n{e.stderr}"
                )
                raise RuntimeError(msg) from e

        # [1/2] Create CodeQL database
        print(f"[1/2] Creating CodeQL database for {src_path.name}...")
        create_cmd = [
            str(self.codeql_path),
            "database",
            "create",
            str(db_dir),
            "--language=javascript",
            f"--source-root={src_path.parent}",
        ]
        run_cmd(create_cmd, "Database creation")

        # [2/2] Analyze the database
        print("[2/2] Running CodeQL analysis...")
        sarif_path = out_dir / "codeql-results.sarif"
        analyze_cmd = [
            str(self.codeql_path),
            "database",
            "analyze",
            str(db_dir),
            query_suite,
            "--format=sarifv2.1.0",
            f"--output={sarif_path}",
        ]
        run_cmd(analyze_cmd, "Database analysis")

        print(f"✅ Analysis complete! SARIF saved at: {sarif_path}")
        return str(sarif_path)

    def analyze_repository(
        self,
        repository_path: str,
        query_suite: str = "javascript-security-extended.qls",
        language: str = "javascript",
    ) -> str:
        """
        Analyze an entire repository for vulnerabilities.

        Args:
            repository_path: Path to the repository root directory to analyze
            query_suite: CodeQL query suite to use (default: javascript-security-extended.qls)
            language: CodeQL language to analyze (default: javascript)

        Returns:
            Path to the generated SARIF report

        Raises:
            FileNotFoundError: If repository path doesn't exist
            RuntimeError: If CodeQL commands fail
        """
        repo_path = Path(repository_path).resolve()
        if not repo_path.exists():
            raise FileNotFoundError(f"❌ Repository path not found: {repo_path}")
        if not repo_path.is_dir():
            raise ValueError(f"❌ Path is not a directory: {repo_path}")

        # Create temporary directories for database and output
        work_dir = Path(tempfile.mkdtemp())
        db_dir = work_dir / "codeql-db"
        out_dir = work_dir / "out"
        out_dir.mkdir(parents=True, exist_ok=True)

        # Helper to run commands with better error reporting
        def run_cmd(cmd: list[str], step_name: str) -> None:
            try:
                completed = subprocess.run(
                    cmd,
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    env=os.environ.copy(),
                )
                # Show stdout if there's useful info
                if completed.stdout.strip():
                    print(completed.stdout.strip())
            except subprocess.CalledProcessError as e:
                # Check for missing extractor error
                if "no CodeQL extractor named" in e.stderr.lower():
                    raise RuntimeError(
                        f"❌ CodeQL extractor for {language} not found.\n\n"
                        f"You downloaded CodeQL CLI only, but extractors are needed to create databases.\n\n"
                        f"SOLUTION: Download CodeQL Bundle (includes CLI + extractors + queries):\n"
                        f"  1. Visit: https://github.com/github/codeql-action/releases\n"
                        f"  2. Download: codeql-bundle-win64.tar.gz (or your platform)\n"
                        f"  3. Extract to a folder (e.g., D:\\codeql-bundle\\)\n"
                        f"  4. Update .env: CODEQL_CLI_PATH=D:\\codeql-bundle\\codeql\\codeql.exe\n\n"
                        f"ALTERNATIVE: Use Docker mode (no installation required):\n"
                        f"  - Comment out CODEQL_CLI_PATH in .env file\n"
                        f"  - Ensure Docker is running\n"
                    ) from e

                # Generic error message
                msg = (
                    f"{step_name} failed (exit code {e.returncode}).\n"
                    f"Command: {' '.join(cmd)}\n"
                    f"stdout:\n{e.stdout}\n"
                    f"stderr:\n{e.stderr}"
                )
                raise RuntimeError(msg) from e

        # [1/2] Create CodeQL database for the entire repository
        print(f"[1/2] Creating CodeQL database for repository at {repo_path}...")
        create_cmd = [
            str(self.codeql_path),
            "database",
            "create",
            str(db_dir),
            f"--language={language}",
            f"--source-root={repo_path}",
        ]
        run_cmd(create_cmd, "Database creation")

        # [2/2] Analyze the database
        print("[2/2] Running CodeQL analysis...")
        sarif_path = out_dir / "codeql-results.sarif"
        analyze_cmd = [
            str(self.codeql_path),
            "database",
            "analyze",
            str(db_dir),
            query_suite,
            "--format=sarifv2.1.0",
            f"--output={sarif_path}",
        ]
        run_cmd(analyze_cmd, "Database analysis")

        print(f"✅ Repository analysis complete! SARIF saved at: {sarif_path}")
        return str(sarif_path)

