# py_mcmd_refactored/utils/subprocess_runner.py

"""
Subprocess execution adapter.

Why this exists
--------------
Legacy code used:
  - subprocess.Popen(..., shell=True)
  - os.wait4(pid, ...)
  - stdout redirection via '> out.dat'

Refactor needs:
  1) mockable interface (unit tests),
  2) explicit cwd (no 'cd ... &&'),
  3) explicit stdout redirection without shell.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional
import subprocess


@dataclass(frozen=True)
class Command:
    """A command to run without invoking a shell."""
    argv: list[str]
    cwd: Path
    stdout_path: Path


@dataclass
class ProcessHandle:
    """A handle to a started process."""
    pid: int
    command: Command
    started_at: datetime
    popen: Optional[subprocess.Popen] = None


class SubprocessRunner:
    """Runs commands and waits for completion."""

    def __init__(self, *, dry_run: bool = False):
        self.dry_run = bool(dry_run)

    def start(self, cmd: Command) -> ProcessHandle:
        """Start a subprocess.

        In dry-run mode, creates stdout file and returns a dummy handle.
        """
        cmd.cwd.mkdir(parents=True, exist_ok=True)
        cmd.stdout_path.parent.mkdir(parents=True, exist_ok=True)

        if self.dry_run:
            if not cmd.stdout_path.exists():
                cmd.stdout_path.write_text("[dry_run] subprocess not executed\n")
            return ProcessHandle(pid=0, command=cmd, started_at=datetime.now(), popen=None)

        out_fh = cmd.stdout_path.open("w", encoding="utf-8")
        p = subprocess.Popen(
            cmd.argv,
            cwd=str(cmd.cwd),
            stdout=out_fh,
            stderr=subprocess.STDOUT,
            text=True,
        )
        # keep handle alive until wait() closes it
        p._py_mcmd_out_fh = out_fh  # type: ignore[attr-defined]
        return ProcessHandle(pid=p.pid, command=cmd, started_at=datetime.now(), popen=p)

    def wait(self, handle: ProcessHandle) -> int:
        """Wait for completion and return exit code."""
        if handle.popen is None:
            return 0

        rc = int(handle.popen.wait())
        out_fh = getattr(handle.popen, "_py_mcmd_out_fh", None)
        if out_fh is not None:
            try:
                out_fh.close()
            except Exception:
                pass
        return rc

    def run_and_wait(self, cmd: Command) -> int:
        """Convenience helper for start+wait."""
        h = self.start(cmd)
        return self.wait(h)


class DryRunSubprocessRunner(SubprocessRunner):
    def __init__(self):
        super().__init__(dry_run=True)