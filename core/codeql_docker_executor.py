# vulnerability_analyzer/core/codeql_docker_executor.py
import os
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional


class CodeQLDockerExecutor:
    """
    Runs CodeQL static analysis using Microsoft's container image.
    Automatically handles DB creation and query execution.

    Supports two modes:
    1. Ephemeral containers (default): Creates new containers with docker run --rm
    2. Running container reuse: Uses docker exec on an existing container
    """

    def __init__(
        self,
        docker_image: str = "ghcr.io/github/codeql-cli2:latest",
        docker_args: Optional[List[str]] = None,
        container_id: Optional[str] = None,
    ):
        """
        Initialize CodeQL Docker executor.

        Args:
            docker_image: Docker image to use (default: ghcr.io/github/codeql-cli2:latest)
            docker_args: Additional docker run arguments (only used in ephemeral mode)
            container_id: ID or name of running container to reuse (if None, uses ephemeral mode)
                         Can also be set via CODEQL_CONTAINER_ID environment variable
        """
        self.docker_image = docker_image
        self.docker_args = docker_args or []

        # Check environment variable if container_id not provided
        self.container_id = container_id or os.getenv("CODEQL_CONTAINER_ID")

        # Validate container if specified
        if self.container_id:
            self._validate_container()

    def _validate_container(self) -> None:
        """Validate that the specified container exists and is running."""
        try:
            result = subprocess.run(
                ["docker", "inspect", "-f", "{{.State.Running}}", self.container_id],
                capture_output=True,
                text=True,
                check=True,
            )
            is_running = result.stdout.strip() == "true"
            if not is_running:
                raise RuntimeError(
                    f"Container '{self.container_id}' exists but is not running. "
                    f"Start it with: docker start {self.container_id}"
                )
            print(f"✓ Using running container: {self.container_id}")
        except subprocess.CalledProcessError:
            raise RuntimeError(
                f"Container '{self.container_id}' not found. "
                f"Available containers: {self._list_containers()}"
            )

    def _list_containers(self) -> str:
        """List available Docker containers."""
        try:
            result = subprocess.run(
                ["docker", "ps", "-a", "--format", "{{.Names}} ({{.ID}})"],
                capture_output=True,
                text=True,
            )
            return result.stdout.strip() or "No containers found"
        except Exception:
            return "Unable to list containers"

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
            query_suite: CodeQL query suite to use
            database_path: Optional path to existing CodeQL database. If provided, skips database creation.
                          If None, checks CODEQL_DATABASE_PATH environment variable, then creates new DB.

        Returns:
            Path to the generated SARIF report
        """
        src_path = Path(source_file).resolve()
        if not src_path.exists():
            raise FileNotFoundError(f"❌ Source file not found: {src_path}")

        # Check for existing database
        db_path_to_use = database_path or os.getenv("CODEQL_DATABASE_PATH")

        # Use different execution modes based on container_id
        if self.container_id:
            return self._analyze_with_running_container(src_path, query_suite, db_path_to_use)
        else:
            return self._analyze_with_ephemeral_container(src_path, query_suite, db_path_to_use)

    def _analyze_with_ephemeral_container(
        self,
        src_path: Path,
        query_suite: str,
        database_path: Optional[str] = None,
    ) -> str:
        """Analyze using ephemeral docker run --rm containers."""
        work_dir = Path(tempfile.mkdtemp())
        out_dir = work_dir / "out"
        out_dir.mkdir(parents=True, exist_ok=True)

        # Handle database path
        if database_path:
            db_dir = Path(database_path).resolve()
            if not db_dir.exists():
                raise FileNotFoundError(
                    f"❌ Specified CodeQL database not found: {db_dir}\n"
                    f"Please check the path or remove CODEQL_DATABASE_PATH to create a new database."
                )
            print(f"♻️  Using existing CodeQL database: {db_dir}")
            skip_db_creation = True
        else:
            db_dir = work_dir / "codeql-db"
            db_dir.mkdir(parents=True, exist_ok=True)
            skip_db_creation = False

        # Helper to run docker command and raise clearer error with output
        def run_cmd(cmd: List[str]) -> None:
            try:
                completed = subprocess.run(
                    cmd,
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    env=os.environ.copy(),
                )
            except subprocess.CalledProcessError as e:
                msg = (
                    f"Command failed (exit {e.returncode}).\n"
                    f"Command: {' '.join(e.cmd)}\n"
                    f"stdout:\n{e.stdout}\n\nstderr:\n{e.stderr}\n"
                )
                raise RuntimeError(msg) from e

        # [1/2] Create CodeQL database (if needed)
        if not skip_db_creation:
            print(f"[1/2] Creating CodeQL database for {src_path.name}...")
            create_cmd = [
                "docker",
                "run",
                "--rm",
                "--entrypoint",
                "codeql",  # IMPORTANT: override the container's startup script
                "-v",
                f"{src_path.parent}:/work/src",
                "-v",
                f"{db_dir}:/work/db",
            ]
            # extra docker args (resources, user, etc.)
            if self.docker_args:
                create_cmd.extend(self.docker_args)

            create_cmd.extend(
                [
                    self.docker_image,
                    "database",
                    "create",
                    "/work/db",
                    "--language=javascript",
                    "--source-root=/work/src",
                ]
            )

            run_cmd(create_cmd)
        else:
            print("[1/2] Skipping database creation (using existing database)")

        # [2/2] Analyze the database
        print("[2/2] Running CodeQL analysis...")
        sarif_path = out_dir / "codeql-results.sarif"
        analyze_cmd = [
            "docker",
            "run",
            "--rm",
            "--entrypoint",
            "codeql",  # override again
            "-v",
            f"{db_dir}:/work/db",
            "-v",
            f"{out_dir}:/work/out",
        ]
        if self.docker_args:
            analyze_cmd.extend(self.docker_args)

        analyze_cmd.extend(
            [
                self.docker_image,
                "database",
                "analyze",
                "/work/db",
                query_suite,
                "--format=sarifv2.1.0",
                "--output",
                f"/work/out/{sarif_path.name}",
            ]
        )

        run_cmd(analyze_cmd)

        print(f"✅ Analysis complete! SARIF saved at: {sarif_path}")
        return str(sarif_path)

    def _analyze_with_running_container(
        self,
        src_path: Path,
        query_suite: str,
        database_path: Optional[str] = None,
    ) -> str:
        """Analyze using an existing running container with docker exec."""
        work_dir = Path(tempfile.mkdtemp())
        out_dir = work_dir / "out"
        out_dir.mkdir(parents=True, exist_ok=True)

        # Handle database path
        if database_path:
            print(f"⚠️  Note: Running container mode with existing database not fully supported yet.")
            print(f"    Database path {database_path} will be ignored, creating new database in container.")
            skip_db_creation = False
        else:
            skip_db_creation = False

        # Container paths
        container_src_dir = "/work/src"
        container_db_dir = "/work/db"
        container_out_dir = "/work/out"
        container_src_file = f"{container_src_dir}/{src_path.name}"

        # Helper to run docker exec commands
        def run_exec(cmd: List[str]) -> None:
            try:
                completed = subprocess.run(
                    cmd,
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    env=os.environ.copy(),
                )
            except subprocess.CalledProcessError as e:
                msg = (
                    f"Command failed (exit {e.returncode}).\n"
                    f"Command: {' '.join(e.cmd)}\n"
                    f"stdout:\n{e.stdout}\n\nstderr:\n{e.stderr}\n"
                )
                raise RuntimeError(msg) from e

        # [0/3] Copy source file to container
        print(f"[0/3] Copying {src_path.name} to container...")
        copy_cmd = [
            "docker",
            "cp",
            str(src_path),
            f"{self.container_id}:{container_src_file}",
        ]
        run_exec(copy_cmd)

        # [1/3] Create CodeQL database inside the container
        print(f"[1/3] Creating CodeQL database in container {self.container_id}...")
        create_cmd = [
            "docker",
            "exec",
            self.container_id,
            "codeql",
            "database",
            "create",
            container_db_dir,
            "--language=javascript",
            f"--source-root={container_src_dir}",
            "--overwrite",  # Overwrite if exists from previous run
        ]
        run_exec(create_cmd)

        # [2/3] Analyze the database
        print("[2/3] Running CodeQL analysis...")
        sarif_name = "codeql-results.sarif"
        analyze_cmd = [
            "docker",
            "exec",
            self.container_id,
            "codeql",
            "database",
            "analyze",
            container_db_dir,
            query_suite,
            "--format=sarifv2.1.0",
            "--output",
            f"{container_out_dir}/{sarif_name}",
        ]
        run_exec(analyze_cmd)

        # [3/3] Copy SARIF result from container to host
        print("[3/3] Copying results from container...")
        sarif_path = out_dir / sarif_name
        copy_result_cmd = [
            "docker",
            "cp",
            f"{self.container_id}:{container_out_dir}/{sarif_name}",
            str(sarif_path),
        ]
        run_exec(copy_result_cmd)

        print(f"✅ Analysis complete! SARIF saved at: {sarif_path}")
        return str(sarif_path)
