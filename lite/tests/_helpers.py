"""Shared test utilities for Trellis Lite.

Each test gets an isolated tmpdir with the runtime installed and `init` run.
The harness invokes `trellis.py` as a subprocess (exactly as users do), so
tests cover the real CLI surface, not just internal functions.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

LITE_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = LITE_ROOT / ".trellis-lite/scripts/trellis.py"
INSTALL_SH = LITE_ROOT / "install.sh"
DIR_ARCHIVE = "archive"


def task_dirs(project_dir: Path) -> list[Path]:
    """List active task directories (excluding the archive container)."""
    tasks = project_dir / ".trellis-lite/tasks"
    return [p for p in tasks.iterdir() if p.is_dir() and p.name != DIR_ARCHIVE]


def find_task(project_dir: Path, slug_suffix: str) -> Path:
    """Find a task dir whose name ends with `-<slug_suffix>`."""
    matches = [p for p in task_dirs(project_dir) if p.name.endswith(f"-{slug_suffix}")]
    if len(matches) != 1:
        raise AssertionError(
            f"expected 1 task ending with '-{slug_suffix}', found {len(matches)}: "
            f"{[p.name for p in matches]}"
        )
    return matches[0]


class Harness:
    """Isolated project directory for one test."""

    def __init__(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp(prefix="trellis-test-"))
        # Initialize as a real user would
        r = self.run(["init", "tester"])
        assert r.returncode == 0, f"init failed: {r.stdout}\n{r.stderr}"

    def run(self, args: list[str]) -> subprocess.CompletedProcess:
        """Invoke trellis.py with given args; cwd = the test project."""
        return subprocess.run(
            ["python3", str(SCRIPT), *args],
            cwd=str(self.tmpdir),
            capture_output=True,
            text=True,
            timeout=30,
        )

    def cleanup(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)