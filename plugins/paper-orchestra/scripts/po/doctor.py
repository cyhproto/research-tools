"""Preflight checks for the environment. Reports problems in JSON; never prints key values."""
import os
import shutil
import sys
from pathlib import Path

from .cli import common_parent, emit
from .plotrun import default_probe, find_plot_python

NO_PLOT_MSG = ("No Python with matplotlib found: install matplotlib in this project's "
               "environment, or install uv")
NETWORK_PROBE_TITLE = "Attention Is All You Need"


def doctor(project_root: Path, env=os.environ, which=shutil.which, probe=default_probe,
           python_version=sys.version_info, network: bool = False, lookup=None) -> dict:
    ver = tuple(python_version)[:3]
    python_ok = ver >= (3, 10)
    plot = find_plot_python(Path(project_root), env=env, which=which, probe=probe)
    uv = bool(which("uv"))
    oa = bool(env.get("OPENALEX_API_KEY"))
    s2 = bool(env.get("SEMANTIC_SCHOLAR_API_KEY"))
    problems: list[str] = []
    steps: list[str] = []
    if not python_ok:
        problems.append("Python 3.10 or newer is required")
    if plot is None:
        problems.append(NO_PLOT_MSG)
    if not oa:
        steps.append("Optional: create a free OpenAlex API key and set OPENALEX_API_KEY")
    if not s2:
        steps.append("Optional: request a Semantic Scholar API key and set SEMANTIC_SCHOLAR_API_KEY")
    net = None
    if network:
        if lookup is None:
            from .scholar import Lookup
            lookup = Lookup()
        out = lookup.openalex_title(NETWORK_PROBE_TITLE)
        net = bool(not out.failed and out.records)
        if not net:
            problems.append("Network check failed: could not reach OpenAlex")
    return {"python_ok": python_ok, "python_version": ".".join(str(x) for x in ver),
            "plot_python": plot, "uv": uv, "openalex_key": oa, "s2_key": s2,
            "network": net, "problems": problems, "next_steps": steps}


def _cmd_doctor(args) -> int:
    paper = Path(args.paper).resolve()
    project = Path(args.project).resolve() if args.project else paper.parent
    r = doctor(project, network=args.network)
    emit(r)
    return 0 if r["python_ok"] else 2


def register(sub) -> None:
    p = sub.add_parser("doctor", parents=[common_parent()], help="check the environment")
    p.add_argument("--network", action="store_true", help="also check OpenAlex reachability")
    p.set_defaults(func=_cmd_doctor)
