"""Materials validation: required headings, results, source tags and figures."""
import re
from dataclasses import dataclass, field
from pathlib import Path

from .cli import common_parent, emit
from .numtok import find_numbers, is_trivial
from .sourcetags import Unreadable, _read_log, parse_tags, untagged_numbers, _verify_text

IDEA_HEADINGS = ["Problem Statement", "Core Hypothesis", "Proposed Methodology",
                 "Expected Contribution"]
LOG_HEADINGS = ["Experimental Setup", "Raw Numeric Data", "Qualitative Observations"]
FIGURE_EXTS = {".png", ".jpg", ".jpeg", ".svg"}

_HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
_NUMBERING = re.compile(r"^\d+(?:\.\d+)*\.?\s+")


@dataclass
class MaterialsReport:
    missing: dict[str, list[str]]
    has_results: bool
    untagged: int
    verify: dict | None
    figures: list[str]
    captions_missing: list[str]
    unreadable_log: str | None = None
    notes: list[str] = field(default_factory=list)


def _norm(text: str) -> str:
    return _NUMBERING.sub("", text.strip()).lower()


def _headings(text: str) -> list[tuple[int, str]]:
    out = []
    for i, line in enumerate(text.splitlines()):
        m = _HEADING.match(line)
        if m:
            out.append((i, _norm(m.group(2))))
    return out


def _missing(text: str, required: list[str]) -> list[str]:
    found = [h for _, h in _headings(text)]
    return [r for r in required if not any(h.startswith(r.lower()) for h in found)]


def _section(text: str, name: str) -> str:
    lines = text.splitlines()
    heads = _headings(text)
    for k, (i, h) in enumerate(heads):
        if h.startswith(name.lower()):
            end = heads[k + 1][0] if k + 1 < len(heads) else len(lines)
            return "\n".join(lines[i + 1:end])
    return ""


def _captioned(captions: str) -> set[str]:
    done = set()
    for line in captions.splitlines():
        m = re.match(r"^\s*[-*]\s+(.+?):\s*(\S.*)$", line)
        if m:
            done.add(m.group(1).strip())
    return done


def validate_materials(paper_dir: Path, project_root: Path) -> MaterialsReport:
    mats = Path(paper_dir) / "materials"
    missing: dict[str, list[str]] = {}
    idea = mats / "idea.md"
    missing["idea.md"] = (_missing(idea.read_text(encoding="utf-8", errors="replace"), IDEA_HEADINGS)
                          if idea.is_file() else list(IDEA_HEADINGS))
    log = mats / "experiment_log.md"
    has_results, untagged, verify, unreadable = False, 0, None, None
    if log.is_file():
        try:
            text = _read_log(log)
        except (Unreadable, OSError) as e:
            text, unreadable = None, str(e)
        if text is None:
            missing["experiment_log.md"] = []
        else:
            missing["experiment_log.md"] = _missing(text, LOG_HEADINGS)
            has_results = any(not is_trivial(n)
                              for n in find_numbers(_section(text, "Raw Numeric Data")))
            untagged = len(untagged_numbers(text))
            if parse_tags(text):
                res = _verify_text(text, Path(project_root))
                verify = {s: sum(1 for r in res if r.status == s)
                          for s in ("ok", "mismatch", "unreadable", "manual")}
    else:
        missing["experiment_log.md"] = list(LOG_HEADINGS)
    figdir = mats / "figures"
    figures = sorted(f.name for f in figdir.iterdir()
                     if f.is_file() and f.suffix.lower() in FIGURE_EXTS) if figdir.is_dir() else []
    cap = figdir / "captions.md"
    done = _captioned(cap.read_text(encoding="utf-8", errors="replace")) if cap.is_file() else set()
    return MaterialsReport(missing, has_results, untagged, verify, figures,
                           [f for f in figures if f not in done], unreadable)


def _cmd_validate(args) -> int:
    import sys
    paper = Path(args.paper)
    project = Path(args.project) if args.project else paper.resolve().parent
    r = validate_materials(paper, project)
    emit({"missing": r.missing, "has_results": r.has_results, "untagged": r.untagged,
          "verify": r.verify, "figures": r.figures, "captions_missing": r.captions_missing,
          "unreadable_log": r.unreadable_log})
    if r.unreadable_log:
        print(f"unreadable experiment log: {r.unreadable_log}", file=sys.stderr)
        return 2
    if not r.has_results:
        print("no results: Raw Numeric Data in experiment_log.md has no non-trivial number",
              file=sys.stderr)
        return 2
    bad = r.verify and (r.verify["mismatch"] or r.verify["unreadable"])
    return 1 if any(r.missing.values()) or bad else 0


def register(sub) -> None:
    group = sub.add_parser("materials", help="materials checks")
    cmds = group.add_subparsers(dest="materials_command")
    cmds.add_parser("validate", parents=[common_parent()],
                    help="check headings, results, tags and figures"
                    ).set_defaults(func=_cmd_validate)
