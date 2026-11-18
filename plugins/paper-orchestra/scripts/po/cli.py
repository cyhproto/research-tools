"""Command-line wiring shared by every po command group."""
import argparse
import importlib
import json
import sys

from . import __version__

# Names of po.<name> modules; each exposes register(subparsers).
COMMAND_MODULES: list[str] = []


def common_parent() -> argparse.ArgumentParser:
    """Parent parser holding options shared by subcommands."""
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--paper", default="paper", help="paper directory (default: paper)")
    p.add_argument("--project", default=None,
                   help="project root (default: parent of the paper directory)")
    return p


def emit(obj: dict) -> None:
    """Print exactly one JSON object."""
    print(json.dumps(obj, ensure_ascii=False))


def _cmd_version(args: argparse.Namespace) -> int:
    emit({"version": __version__})
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="po", description="paper-orchestra helper CLI")
    sub = parser.add_subparsers(dest="command")
    version = sub.add_parser("version", help="print the version")
    version.set_defaults(func=_cmd_version)
    for name in COMMAND_MODULES:
        importlib.import_module(f"po.{name}").register(sub)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 2
    func = getattr(args, "func", None)
    if func is None:
        parser.print_usage(sys.stderr)
        return 2
    return int(func(args) or 0)
