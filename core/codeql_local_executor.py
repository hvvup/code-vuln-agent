# vulnerability_analyzer/core/codeql_local_executor.py
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
        database_path: Optional[str] = None,
    ) -> str:
        """
        Analyze a JavaScript file for vulnerabilities.

        Args:
            source_file: Path to the JavaScript file to analyze
            query_suite: CodeQL query suite to use (default: javascript-security-extended.qls)
            database_path: Optional path to existing CodeQL database. If provided, skips database creation.
                          If None, checks CODEQL_DATABASE_PATH environment variable, then creates new DB.

        Returns:
            Path to the generated SARIF report

        Raises:
            FileNotFoundError: If source file or database doesn't exist
            RuntimeError: If CodeQL commands fail
        """
        src_path = Path(source_file).resolve()
        if not src_path.exists():
            raise FileNotFoundError(f"❌ Source file not found: {src_path}")

        # Check for existing database
        db_path_to_use = database_path or os.getenv("CODEQL_DATABASE_PATH")

        # Create temporary directories for output (and database if needed)
        work_dir = Path(tempfile.mkdtemp())
        out_dir = work_dir / "out"
        out_dir.mkdir(parents=True, exist_ok=True)

        if db_path_to_use:
            # Use existing database
            db_dir = Path(db_path_to_use).resolve()
            if not db_dir.exists():
                raise FileNotFoundError(
                    f"❌ Specified CodeQL database not found: {db_dir}\n"
                    f"Please check the path or remove CODEQL_DATABASE_PATH to create a new database."
                )
            print(f"♻️  Using existing CodeQL database: {db_dir}")
            skip_db_creation = True
        else:
            # Create new database
            db_dir = work_dir / "codeql-db"
            skip_db_creation = False

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

        # [1/2] Create CodeQL database (if needed)
        if not skip_db_creation:
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
        else:
            print("[1/2] Skipping database creation (using existing database)")

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
