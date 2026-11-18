"""Run a generated matplotlib script and report whether it produced its PNG."""
import dataclasses
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Mapping
from pathlib import Path

from .cli import common_parent, emit

UV_CMD = ["uv", "run", "--no-project", "--with", "matplotlib", "--with", "numpy", "python"]
NO_PYTHON_MSG = "install matplotlib in this project's environment, or install uv"


def default_probe(cmd: list[str]) -> bool:
    """True when `cmd` can import matplotlib and numpy."""
    try:
        r = subprocess.run(cmd + ["-c", "import matplotlib, numpy"], capture_output=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return False
    return r.returncode == 0


def find_plot_python(project_root: Path, env: Mapping[str, str] = os.environ,
                     which=shutil.which, probe=default_probe) -> list[str] | None:
    """First usable interpreter command, or None. Never installs anything itself."""
    root = Path(project_root)
    candidates: list[list[str]] = []
    if env.get("VIRTUAL_ENV"):
        candidates.append([f"{env['VIRTUAL_ENV']}/bin/python"])
    candidates += [[str(root / ".venv/bin/python")], [str(root / "venv/bin/python")], ["python3"]]
    if which("uv"):
        candidates.append(list(UV_CMD))
    for cmd in candidates:
        if probe(cmd):
            return cmd
    return None


@dataclasses.dataclass
class PlotRun:
    ok: bool
    png: Path | None
    stderr_tail: str


def run_plot(script: Path, paper_dir: Path, cmd: list[str], timeout_s: int = 120) -> PlotRun:
    paper_dir = Path(paper_dir)
    script = Path(script)
    png = paper_dir / "figures" / f"{script.stem}.png"
    before = png.stat().st_mtime_ns if png.exists() else None
    env = dict(os.environ, MPLBACKEND="Agg")
    try:
        r = subprocess.run(cmd + [str(script)], cwd=paper_dir, env=env, capture_output=True,
                           text=True, errors="replace", timeout=timeout_s)
    except subprocess.TimeoutExpired:
        return PlotRun(False, None, f"timed out after {timeout_s} s")
    except OSError as e:
        return PlotRun(False, None, f"could not start {cmd[0]}: {e}")
    tail = (r.stderr or "")[-2000:]
    fresh = png.exists() and (before is None or png.stat().st_mtime_ns != before)
    if r.returncode == 0 and fresh:
        return PlotRun(True, png, tail)
    if r.returncode == 0 and not tail:
        tail = f"script exited 0 but did not write {png.relative_to(paper_dir)}"
    return PlotRun(False, None, tail)


def _cmd_plot_run(args) -> int:
    paper = Path(args.paper).resolve()
    project = Path(args.project).resolve() if args.project else paper.parent
    script = (paper / args.script).resolve()
    if not script.is_relative_to(paper) or not script.is_file():
        print(f"script not found inside the paper directory: {args.script}", file=sys.stderr)
        return 1
    cmd = find_plot_python(project)
    if cmd is None:
        print(NO_PYTHON_MSG, file=sys.stderr)
        return 2
    r = run_plot(script, paper, cmd)
    if r.ok:
        emit({"ok": True, "png": str(r.png.relative_to(paper))})
        return 0
    emit({"ok": False, "png": None, "stderr_tail": r.stderr_tail})
    return 1


def register(sub) -> None:
    p = sub.add_parser("plot-run", parents=[common_parent()], help="run a figure script")
    p.add_argument("--script", required=True, help="script path relative to the paper dir")
    p.set_defaults(func=_cmd_plot_run)
