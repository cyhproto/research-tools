#!/usr/bin/env python3
"""Acceptance checks for the TSAM end-to-end sample run (spec section 13, item 1).

Usage: python3 tests/e2e/assert_sample.py <paper_dir>

Exits 0 when every check holds. Otherwise prints every failure and exits 1.
Exit 2 is a usage error.
"""
import json
import re
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "plugins" / "paper-orchestra" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from po.paper import section_name, split_sections  # noqa: E402
from po.settings import SettingsError, load_settings  # noqa: E402
from po.style import StyleNotFound, find_style, load_style  # noqa: E402

MIN_REFERENCES = 30
MIN_PLOTS = 2
SUPPLIED_FIGURE = "tsam_overview.png"
OUTCOME_RE = re.compile(r"^(ACCEPTED|REJECTED)_[A-Z_]+$")
NUMBER_RE = re.compile(r"^-?\d+(\.\d+)?$")
MERMAID_RE = re.compile(r"^ {0,3}```mermaid[^\n]*\n(.*?)^ {0,3}```", re.S | re.M)


def _collapse(s: str) -> str:
    return " ".join(s.split())


def _read(path: Path, failures: list[str]) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        failures.append(f"{path}: missing")
    except (OSError, UnicodeDecodeError) as e:
        failures.append(f"{path}: unreadable ({e})")
    return None


def _json(path: Path, failures: list[str]):
    text = _read(path, failures)
    if text is None:
        return None
    try:
        return json.loads(text)
    except ValueError as e:
        failures.append(f"{path}: not valid JSON ({e})")
        return None


def _h2_section(md: str, name: str) -> str | None:
    """Body of the `## <name>` section, or None when the heading is absent."""
    m = re.search(rf"^## {re.escape(name)}[ \t]*\r?\n(.*?)(?=^## |\Z)", md, re.S | re.M)
    return m.group(1) if m else None


def check_sections(paper: Path, md: str, failures: list[str]) -> None:
    try:
        style = load_style(find_style(load_settings(paper).style, paper))
    except (SettingsError, StyleNotFound) as e:
        failures.append(f"style: cannot load the style guide ({e})")
        return
    have = {s.name.casefold() for s in split_sections(md)[1]}
    for name in style.sections:
        if section_name(name).casefold() not in have:
            failures.append(f"paper.md: style section missing: {name}")


def check_references(paper: Path, failures: list[str]) -> int:
    lib = _json(paper / "references" / "library.json", failures)
    if lib is None:
        return 0
    entries = [e for e in lib if isinstance(e, dict) and e.get("key")] if isinstance(lib, list) else []
    if len(entries) < MIN_REFERENCES:
        failures.append(f"references/library.json: {len(entries)} entries, need at least {MIN_REFERENCES}")
    return len(entries)


def _embedded(md: str, entry: dict, paper: Path) -> bool:
    f = str(entry.get("file", ""))
    if entry.get("kind") == "diagram" or f.endswith(".mmd"):
        path = paper / f
        if not path.is_file():
            return False
        want = _collapse(path.read_text(encoding="utf-8", errors="replace"))
        return any(_collapse(m.group(1)) == want for m in MERMAID_RE.finditer(md))
    return f"]({f})" in md


def check_figures(paper: Path, md: str, failures: list[str]) -> tuple[int, int]:
    info = _json(paper / "figures" / "info.json", failures)
    if info is None:
        return 0, 0
    if not isinstance(info, list):
        failures.append("figures/info.json: not a list")
        return 0, 0
    entries = [e for e in info if isinstance(e, dict)]
    plots = [e for e in entries if e.get("kind") == "plot" and (paper / str(e.get("file", ""))).is_file()]
    if len(plots) < MIN_PLOTS:
        failures.append(f"figures/info.json: {len(plots)} plot(s) with an existing file, need at least {MIN_PLOTS}")
    if not any(Path(str(e.get("file", ""))).name == SUPPLIED_FIGURE for e in entries):
        failures.append(f"figures/info.json: supplied figure {SUPPLIED_FIGURE} is not listed")
    for e in entries:
        if not _embedded(md, e, paper):
            failures.append(f"paper.md: figure {e.get('id')} ({e.get('file')}) is not embedded")
    return len(entries), len(plots)


def check_review(review_md: str, failures: list[str]) -> int:
    body = _h2_section(review_md, "Review rounds")
    if body is None:
        failures.append("review.md: no '## Review rounds' section")
        return 0
    rounds = 0
    for line in body.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 4 or not OUTCOME_RE.match(cells[-1]):
            continue  # header, separator, prose
        if NUMBER_RE.match(cells[-3]) and NUMBER_RE.match(cells[-2]):
            rounds += 1
    if rounds == 0:
        failures.append("review.md: no review round with Overall scores and an outcome")
    return rounds


def check_check(paper: Path, review_md: str, failures: list[str]) -> None:
    _json(paper / "check" / "report.json", failures)
    body = _h2_section(review_md, "Check")
    if body is None:
        failures.append("review.md: no '## Check' section")
    elif not body.strip() or body.strip() == "Not run yet.":
        failures.append("review.md: the '## Check' section is empty (check finalize did not run)")


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    paper = Path(argv[0])
    if not paper.is_dir():
        print(f"not a directory: {paper}", file=sys.stderr)
        return 2
    failures: list[str] = []
    md = _read(paper / "paper.md", failures) or ""
    review_md = _read(paper / "review.md", failures) or ""
    if md:
        check_sections(paper, md, failures)
    n_refs = check_references(paper, failures)
    n_figs, n_plots = check_figures(paper, md, failures)
    n_rounds = check_review(review_md, failures) if review_md else 0
    check_check(paper, review_md, failures)
    summary = (f"references={n_refs} figures={n_figs} plots={n_plots} "
               f"review_rounds_with_outcome={n_rounds}")
    if failures:
        for f in failures:
            print(f"FAIL: {f}")
        print(f"{len(failures)} failure(s); {summary}")
        return 1
    print(f"OK: all checks passed; {summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
