"""Check stage: find citation, number, figure and venue problems, then merge the checker's rulings."""
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path

from .cli import common_parent, emit
from .library import load_library
from .numbers import unmatched
from .paper import H2_RE, LINE_RE, fence_tags, section_name, split_sections
from .references import BRACKET_RE, KEY_RE, cited_keys
from .settings import load_settings
from .sourcetags import mask_tags, parse_tags
from .style import find_style, load_style

STATUSES = ("pass", "fail", "warn", "needs_ruling")
COVERAGE_MIN = 0.9
TEXT_SUFFIXES = {".md", ".txt", ".csv", ".tsv", ".json", ".log"}

_HTML_COMMENT_RE = re.compile(r"<!--.*?(?:-->|\Z)", re.S)
_URL_RE = re.compile(r"<https?://[^>\s]*>|https?://\S+")
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_CAPTION_RE = re.compile(r"^\s*\*(Figure|Table)\s+(\d+)\s*:")
_MERMAID_RE = re.compile(r"^ {0,3}```mermaid[^\n]*\n(.*?)^ {0,3}```", re.S | re.M)
_SENT_RE = re.compile(r"(?<!\bal\.)(?<!\be\.g\.)(?<!\bi\.e\.)(?<![A-Z]\.)(?<=[.!?])\s+(?=[A-Z\[(])")


@dataclass
class CheckItem:
    id: str
    category: str
    status: str
    line: int | None
    message: str
    data: dict = field(default_factory=dict)


def _blank(text: str, pattern: re.Pattern) -> str:
    return pattern.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)


def _collapse(s: str) -> str:
    return " ".join(s.split())


def _prose_lines(md: str) -> list[tuple[int, str]]:
    """(line number, line) for lines outside fenced code and the References section."""
    lines = LINE_RE.findall(md)
    out, in_refs = [], False
    for n, (line, tag) in enumerate(zip(lines, fence_tags(lines)), 1):
        if tag is not None:
            continue
        h = H2_RE.match(line.rstrip("\r\n"))
        if h:
            in_refs = section_name(h.group(1)) == "References"
        if not in_refs:
            out.append((n, line.rstrip("\r\n")))
    return out


def _blocks(md: str) -> list[list[tuple[int, str]]]:
    blocks: list[list[tuple[int, str]]] = []
    cur: list[tuple[int, str]] = []
    prev = None
    for n, line in _prose_lines(md):
        if not line.strip() or (prev is not None and n != prev + 1):
            if cur:
                blocks.append(cur)
            cur = []
        if line.strip():
            cur.append((n, line))
        prev = n
    if cur:
        blocks.append(cur)
    return blocks


def _first_line(md: str, needle: str) -> int | None:
    for n, line in _prose_lines(md):
        if needle in line:
            return n
    return None


def _main_text(md: str) -> str:
    pre, secs = split_sections(md)
    keep = [pre]
    for s in secs:
        if s.name in ("References", "Appendix"):
            break
        keep.append(s.heading + s.text)
    lines = LINE_RE.findall("".join(keep))
    text = "".join(l for l, t in zip(lines, fence_tags(lines)) if t is None)
    return _HTML_COMMENT_RE.sub(" ", text)


def _mask_for_numbers(md: str) -> str:
    return _blank(mask_tags(md), _URL_RE)


def _materials_texts(paper_dir: Path) -> list[str]:
    root = paper_dir / "materials"
    if not root.is_dir():
        return []
    return [p.read_text(encoding="utf-8", errors="replace")
            for p in sorted(root.rglob("*")) if p.is_file() and p.suffix.lower() in TEXT_SUFFIXES]


class _Items:
    def __init__(self):
        self.raw: list[tuple[str, str, int | None, str, dict]] = []

    def add(self, category, status, line, message, data=None):
        self.raw.append((category, status, line, message, data or {}))

    def build(self) -> list[CheckItem]:
        order: dict[str, list] = {}
        for r in self.raw:
            order.setdefault(r[0], []).append(r)
        out = []
        for cat, rows in order.items():
            rows = sorted(rows, key=lambda r: (r[2] is None, r[2] or 0))
            out += [CheckItem(f"{cat}-{n:03d}", cat, st, ln, msg, data)
                    for n, (_, st, ln, msg, data) in enumerate(rows, 1)]
        return out


def _check_citations(md, lib, items: _Items) -> None:
    entries = {e.key: e for e in lib}
    cited = cited_keys(md)
    for k in cited:
        ln = _first_line(md, "@" + k)
        if k not in entries:
            items.add("citations", "fail", ln, f"citation key {k} is not in the library")
        elif not entries[k].verified_by:
            items.add("citations", "fail", ln, f"library entry {k} has no verified_by")
    for e in lib:
        if e.must_cite and e.key not in cited:
            items.add("citations", "fail", None, f"must-cite entry {e.key} is not cited")
    if lib:
        known = [k for k in dict.fromkeys(cited) if k in entries]
        coverage = len(known) / len(lib)
        if coverage < COVERAGE_MIN:
            items.add("citations", "warn", None,
                      f"only {len(known)} of {len(lib)} library entries are cited (coverage {coverage:.2f})")
        unused = [e.key for e in lib if e.key not in cited]
        if unused:
            items.add("citations", "warn", None, "unused library keys: " + ", ".join(unused))
    for block in _blocks(md):
        text = "\n".join(l for _, l in block)
        offs = [0]
        for _, l in block:
            offs.append(offs[-1] + len(l) + 1)
        spans, pos = [], 0
        for m in _SENT_RE.finditer(text):
            spans.append((pos, m.start()))
            pos = m.end()
        spans.append((pos, len(text)))
        seen = set()
        for g in BRACKET_RE.finditer(text):
            for key in KEY_RE.findall(g.group(1)):
                e = entries.get(key)
                if e is None or not e.title_only:
                    continue
                s, t = next((a, b) for a, b in spans if a <= g.start() <= b)
                if (key, s) in seen:
                    continue
                seen.add((key, s))
                line_idx = max(i for i, o in enumerate(offs[:-1]) if o <= g.start())
                items.add("citations", "needs_ruling", block[line_idx][0],
                          f"sentence cites title-only entry {key}",
                          {"sentence": text[s:t].strip(), "key": key, "title": e.title, "venue": e.venue})


def _check_numbers(md, paper_dir, lib, settings, items: _Items) -> None:
    for tag in parse_tags(md):
        items.add("numbers", "fail", tag.line_no, "source tag left in paper")
    years = {e.year for e in lib if e.year is not None} | {date.today().year}
    try:
        years.add(int(settings.cutoff[:4]))
    except ValueError:
        pass
    for h in unmatched(_mask_for_numbers(md), _materials_texts(paper_dir), years):
        items.add("numbers", "needs_ruling", h.line_no, f"number {h.num.token} not found in the materials",
                  {"token": h.num.token, "context": h.context, "line": h.line_no})


def _embedded(md: str, entry: dict, paper_dir: Path) -> bool:
    f = entry.get("file", "")
    if entry.get("kind") == "diagram" or str(f).endswith(".mmd"):
        path = paper_dir / f
        if not path.is_file():
            return False
        want = _collapse(path.read_text(encoding="utf-8", errors="replace"))
        return any(_collapse(m.group(1)) == want for m in _MERMAID_RE.finditer(md))
    return f"]({f})" in md


def _check_figures(md, paper_dir: Path, items: _Items) -> None:
    info_path = paper_dir / "figures" / "info.json"
    info = []
    if info_path.is_file():
        try:
            info = json.loads(info_path.read_text(encoding="utf-8"))
        except ValueError:
            items.add("figures", "fail", None, "figures/info.json is not valid JSON")
    for entry in info if isinstance(info, list) else []:
        f = entry.get("file", "")
        if not f or not (paper_dir / f).is_file():
            items.add("figures", "fail", None, f"figure file {f} is missing")
        if not _embedded(md, entry, paper_dir):
            items.add("figures", "fail", None, f"figure {entry.get('id')} ({f}) is never embedded in paper.md")
    lines = md.splitlines()
    for i, line in enumerate(lines, 1):
        m = _CAPTION_RE.match(line)
        if not m:
            continue
        kind, num = m.group(1), m.group(2)
        pat = (r"\b(?:Figure|Fig\.)\s*" if kind == "Figure" else r"\bTable\s*") + num + r"(?!\d)"
        own = re.compile(rf"^\s*\*{kind}\s+{num}\s*:")
        if not any(re.search(pat, l) for l in lines if not own.match(l)):
            items.add("figures", "fail", i, f"{kind} {num} is never referenced in the text")


def _check_venue(md, paper_dir, settings, items: _Items) -> None:
    style = load_style(find_style(settings.style, paper_dir))
    _, secs = split_sections(md)
    have = {s.name.casefold() for s in secs}
    for name in style.sections:
        if name.casefold() not in have:
            items.add("venue", "fail", None, f"missing section: {name}")
    low = md.casefold()
    for st in style.required_statements:
        if st.casefold() not in low:
            items.add("venue", "fail", None, f"missing required statement: {st}")
    words = len(_main_text(md).split())
    lo, hi = style.length_words
    if not lo <= words <= hi:
        items.add("venue", "fail", None, f"main text has {words} words, outside {lo}-{hi}")
    if settings.blind_review:
        for n, line in enumerate(md.splitlines(), 1):
            if _EMAIL_RE.search(line):
                items.add("venue", "fail", n, "email address in a blind-review paper")
            if re.match(r"^#{1,6}\s.*Acknowledg", line, re.I):
                items.add("venue", "fail", n, "Acknowledgments heading in a blind-review paper")
            for a in settings.authors:
                if a and a.casefold() in line.casefold():
                    items.add("venue", "fail", n, f"author name {a} in a blind-review paper")


def run_check(paper_dir: Path, project_root: Path) -> list[CheckItem]:
    paper_dir = Path(paper_dir)
    md = (paper_dir / "paper.md").read_text(encoding="utf-8")
    lib = load_library(paper_dir)
    settings = load_settings(paper_dir)
    items = _Items()
    _check_citations(md, lib, items)
    _check_numbers(md, paper_dir, lib, settings, items)
    _check_figures(md, paper_dir, items)
    _check_venue(md, paper_dir, settings, items)
    built = items.build()
    write_report(paper_dir, built)  # finalize reads check/report.json
    return built


def _counts(items: list[CheckItem]) -> dict:
    return {s: sum(1 for i in items if i.status == s) for s in STATUSES}


def write_report(paper_dir: Path, items: list[CheckItem]) -> Path:
    path = Path(paper_dir) / "check" / "report.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"counts": _counts(items), "items": [asdict(i) for i in items]},
                               ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _load_report(paper_dir: Path) -> list[CheckItem]:
    data = json.loads((Path(paper_dir) / "check" / "report.json").read_text(encoding="utf-8"))
    return [CheckItem(**d) for d in data["items"]]


def _where(i: CheckItem) -> str:
    return f"{i.id} (line {i.line})" if i.line is not None else i.id


def _write_check_section(paper_dir: Path, body: str) -> None:
    path = Path(paper_dir) / "review.md"
    section = "## Check\n\n" + body.strip("\n") + "\n"
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    m = re.search(r"^## Check[ \t]*\n.*?(?=^## |\Z)", text, re.S | re.M)
    if m:
        tail = text[m.end():]
        text = text[:m.start()] + section + ("\n" + tail if tail else "")
    else:
        text = (text.rstrip("\n") + "\n\n" if text.strip() else "") + section
    path.write_text(text, encoding="utf-8")


def finalize(paper_dir: Path, rulings: dict[str, dict]) -> dict:
    items = _load_report(paper_dir)
    rulings = rulings or {}
    problems, warns, allowed = [], [], []
    for i in items:
        if i.status == "needs_ruling":
            r = rulings.get(i.id) or {}
            if r.get("ruling") == "allow":
                allowed.append((i, r))
            else:
                problems.append((i, r))
        elif i.status == "fail":
            problems.append((i, {}))
        elif i.status == "warn":
            warns.append(i)

    def detail(r: dict) -> str:
        if not r:
            return ""
        s = f" Ruling: {r.get('ruling')}. Reason: {r.get('reason') or 'none given'}."
        return s + (f" Arithmetic: {r['arithmetic']}" if r.get("arithmetic") else "")

    status_line = "READY" if not problems else f"NOT READY: {len(problems)} problems"
    lines = [f"Status: {status_line}", ""]
    for i, r in problems:
        lines.append(f"- FAIL {_where(i)}: {i.message}.{detail(r)}"
                     + (" No ruling." if i.status == "needs_ruling" and not r else ""))
    lines += [f"- WARN {_where(i)}: {i.message}" for i in warns]
    lines += [f"- ALLOWED {_where(i)}: {i.message}.{detail(r)}" for i, r in allowed]
    if not (problems or warns or allowed):
        lines.append("No problems found.")
    _write_check_section(paper_dir, "\n".join(lines))
    return {"ready": not problems, "problems": len(problems), "status_line": status_line}


def _cmd_run(args) -> int:
    paper = Path(args.paper)
    project = Path(args.project) if args.project else paper.resolve().parent
    items = run_check(paper, project)
    path = write_report(paper, items)
    emit({**_counts(items), "report": str(path)})
    return 0


def _cmd_finalize(args) -> int:
    paper = Path(args.paper)
    rulings: dict = {}
    if args.rulings and Path(args.rulings).is_file():
        text = Path(args.rulings).read_text(encoding="utf-8")
        if text.strip():
            try:
                rulings = json.loads(text)
            except ValueError as e:
                emit({"error": f"rulings file is not valid JSON: {e}"})
                return 2
            if not isinstance(rulings, dict):
                emit({"error": "rulings file must hold a JSON object"})
                return 2
    try:
        out = finalize(paper, rulings)
    except FileNotFoundError:
        emit({"error": "check/report.json is missing; run `po check run` first"})
        return 2
    emit(out)
    return 0 if out["ready"] else 1


def register(sub) -> None:
    group = sub.add_parser("check", help="final checks before submission")
    cmds = group.add_subparsers(dest="check_command")
    r = cmds.add_parser("run", parents=[common_parent()], help="run all checks and write check/report.json")
    r.set_defaults(func=_cmd_run)
    f = cmds.add_parser("finalize", parents=[common_parent()], help="merge rulings and print READY or NOT READY")
    f.add_argument("--rulings", default=None, help="rulings JSON written by the checker")
    f.set_defaults(func=_cmd_finalize)
