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
    """

    def __init__(
        self,
        docker_image: str = "ghcr.io/github/codeql-cli2:latest",
        docker_args: Optional[List[str]] = None,
    ):
        self.docker_image = docker_image
        self.docker_args = docker_args or []

    def analyze_file(
        self,
        source_file: str,
        query_suite: str = "javascript-security-extended.qls",
    ) -> str:
        src_path = Path(source_file).resolve()
        if not src_path.exists():
            raise FileNotFoundError(f"❌ Source file not found: {src_path}")

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
