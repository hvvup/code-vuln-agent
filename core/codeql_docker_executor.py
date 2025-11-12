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
    ) -> str:
        """
        Analyze a JavaScript file for vulnerabilities.

        Args:
            source_file: Path to the JavaScript file to analyze
            query_suite: CodeQL query suite to use

        Returns:
            Path to the generated SARIF report
        """
        src_path = Path(source_file).resolve()
        if not src_path.exists():
            raise FileNotFoundError(f"❌ Source file not found: {src_path}")

        # Use different execution modes based on container_id
        if self.container_id:
            return self._analyze_with_running_container(src_path, query_suite)
        else:
            return self._analyze_with_ephemeral_container(src_path, query_suite)

    def _analyze_with_ephemeral_container(
        self,
        src_path: Path,
        query_suite: str,
    ) -> str:
        """Analyze using ephemeral docker run --rm containers."""
        work_dir = Path(tempfile.mkdtemp())
        db_dir = work_dir / "codeql-db"
        out_dir = work_dir / "out"
        db_dir.mkdir(parents=True, exist_ok=True)
        out_dir.mkdir(parents=True, exist_ok=True)

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

        # [1/2] Create CodeQL database (override entrypoint to codeql)
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
    ) -> str:
        """Analyze using an existing running container with docker exec."""
        work_dir = Path(tempfile.mkdtemp())
        out_dir = work_dir / "out"
        out_dir.mkdir(parents=True, exist_ok=True)

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
            query_suite: CodeQL query suite to use
            language: CodeQL language to analyze (default: javascript)

        Returns:
            Path to the generated SARIF report
        """
        repo_path = Path(repository_path).resolve()
        if not repo_path.exists():
            raise FileNotFoundError(f"❌ Repository path not found: {repo_path}")
        if not repo_path.is_dir():
            raise ValueError(f"❌ Path is not a directory: {repo_path}")

        # Use different execution modes based on container_id
        if self.container_id:
            return self._analyze_repository_with_running_container(
                repo_path, query_suite, language
            )
        else:
            return self._analyze_repository_with_ephemeral_container(
                repo_path, query_suite, language
            )

    def _analyze_repository_with_ephemeral_container(
        self,
        repo_path: Path,
        query_suite: str,
        language: str,
    ) -> str:
        """Analyze repository using ephemeral docker run --rm containers."""
        work_dir = Path(tempfile.mkdtemp())
        db_dir = work_dir / "codeql-db"
        out_dir = work_dir / "out"
        db_dir.mkdir(parents=True, exist_ok=True)
        out_dir.mkdir(parents=True, exist_ok=True)

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

        # [1/2] Create CodeQL database for the entire repository
        print(f"[1/2] Creating CodeQL database for repository at {repo_path}...")
        create_cmd = [
            "docker",
            "run",
            "--rm",
            "--entrypoint",
            "codeql",
            "-v",
            f"{repo_path}:/work/src",
            "-v",
            f"{db_dir}:/work/db",
        ]
        if self.docker_args:
            create_cmd.extend(self.docker_args)

        create_cmd.extend(
            [
                self.docker_image,
                "database",
                "create",
                "/work/db",
                f"--language={language}",
                "--source-root=/work/src",
            ]
        )

        run_cmd(create_cmd)

        # [2/2] Analyze the database
        print("[2/2] Running CodeQL analysis...")
        sarif_path = out_dir / "codeql-results.sarif"
        analyze_cmd = [
            "docker",
            "run",
            "--rm",
            "--entrypoint",
            "codeql",
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

        print(f"✅ Repository analysis complete! SARIF saved at: {sarif_path}")
        return str(sarif_path)

    def _analyze_repository_with_running_container(
        self,
        repo_path: Path,
        query_suite: str,
        language: str,
    ) -> str:
        """Analyze repository using an existing running container with docker exec."""
        work_dir = Path(tempfile.mkdtemp())
        out_dir = work_dir / "out"
        out_dir.mkdir(parents=True, exist_ok=True)

        # Container paths
        container_src_dir = "/work/src"
        container_db_dir = "/work/db"
        container_out_dir = "/work/out"

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

        # [0/3] Copy repository to container (using tar for directories)
        print(f"[0/3] Copying repository to container...")
        # Create a tar archive of the repository
        import tarfile

        repo_tar = work_dir / "repo.tar"
        with tarfile.open(repo_tar, "w") as tar:
            tar.add(repo_path, arcname=".")

        # Copy tar to container
        copy_cmd = [
            "docker",
            "cp",
            str(repo_tar),
            f"{self.container_id}:{container_src_dir}/repo.tar",
        ]
        run_exec(copy_cmd)

        # Extract in container
        extract_cmd = [
            "docker",
            "exec",
            self.container_id,
            "tar",
            "-xf",
            f"{container_src_dir}/repo.tar",
            "-C",
            container_src_dir,
        ]
        run_exec(extract_cmd)

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
            f"--language={language}",
            f"--source-root={container_src_dir}",
            "--overwrite",
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

        print(f"✅ Repository analysis complete! SARIF saved at: {sarif_path}")
        return str(sarif_path)
