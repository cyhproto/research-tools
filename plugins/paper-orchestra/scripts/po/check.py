"""Check stage: find citation, number, figure and venue problems, then merge the checker's rulings."""
import hashlib
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path

from .cli import common_parent, emit
from .library import load_library
from .numbers import matches, materials_numbers, unmatched
from .paper import H2_RE, LINE_RE, fence_tags, section_name, split_sections
from .references import ENTRY_RE, bare_unknown_keys, cited_keys, citations
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
_SEP = r"(?:\s*,\s*(?:and\s+)?|\s+and\s+|\s*&\s*|\s*[\u2013\u2014-]\s*|\s+to\s+)"
_REF_RE = re.compile(rf"\b(Figures?|Figs?\.?|Tables?)\s*(\d+(?:{_SEP}\d+)*)(?!\d)")
_FIG_TARGET_RE = re.compile(r"\]\(\s*<?(figures/[^)\s>#]+)")
_SENT_RE = re.compile(r"(?<!\bal\.)(?<!\be\.g\.)(?<!\bi\.e\.)(?<![A-Z]\.)(?<=[.!?])\s+(?=[A-Z\[(])")


def _references(line: str) -> set[tuple[str, int]]:
    """(kind, number) pairs referenced in a line, expanding lists and ranges."""
    out = set()
    for m in _REF_RE.finditer(line):
        kind = "Table" if m.group(1).startswith("T") else "Figure"
        nums = re.split(rf"({_SEP})", m.group(2))
        vals = [int(x) for x in nums[0::2]]
        seps = nums[1::2]
        out.add((kind, vals[0]))
        for k, sep in enumerate(seps):
            a, b = vals[k], vals[k + 1]
            if re.search(r"[\u2013\u2014-]|\bto\b", sep) and a < b <= a + 1000:
                out.update((kind, v) for v in range(a, b + 1))
            out.add((kind, b))
    return out


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
    """(line number, line) for lines outside fenced code, the References heading and its entries.

    Other text under References is the user's (`paper references` keeps it), so it counts as prose."""
    lines = LINE_RE.findall(md)
    out, in_refs = [], False
    for n, (line, tag) in enumerate(zip(lines, fence_tags(lines)), 1):
        if tag is not None:
            continue
        h = H2_RE.match(line.rstrip("\r\n"))
        if h:
            in_refs = section_name(h.group(1)) == "References"
        if in_refs and (h or ENTRY_RE.match(line)):
            continue
        out.append((n, line.rstrip("\r\n")))
    return out


def _check_reference_text(md: str, items: "_Items") -> None:
    """One warn item for text under ## References that is not a reference entry."""
    lines = LINE_RE.findall(md)
    found, in_refs = [], False
    for n, (line, tag) in enumerate(zip(lines, fence_tags(lines)), 1):
        s = line.rstrip("\r\n")
        h = H2_RE.match(s) if tag is None else None
        if h:
            in_refs = section_name(h.group(1)) == "References"
        elif in_refs and s.strip() and not ENTRY_RE.match(s):
            found.append(n)
    if found:
        items.add("references", "warn", found[0],
                  f"text under ## References is not a reference entry "
                  f"(line{'s' if len(found) > 1 else ''} {', '.join(map(str, found))}); "
                  "give it its own ## heading. Check reads it as body text, and `paper references` keeps it "
                  "after the list", {"lines": found})


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


def _sentence_spans(text: str) -> list[tuple[int, int]]:
    """(start, end) of each sentence in a block of prose text."""
    spans, pos = [], 0
    for m in _SENT_RE.finditer(text):
        spans.append((pos, m.start()))
        pos = m.end()
    spans.append((pos, len(text)))
    return spans


def _sentence_index(md: str) -> dict[int, tuple[str, int, list[tuple[int, int]]]]:
    """Per prose line number: (its block's text, the line's offset in it, the block's sentence spans)."""
    index = {}
    for block in _blocks(md):
        text = "\n".join(l for _, l in block)
        spans = _sentence_spans(text)
        off = 0
        for n, l in block:
            index[n] = (text, off, spans)
            off += len(l) + 1
    return index


def _first_line(md: str, needle: str) -> int | None:
    for n, line in _prose_lines(md):
        if needle in line:
            return n
    return None


def _main_text(md: str) -> str:
    pre, secs = split_sections(md)
    keep = [pre]
    for s in secs:
        if s.name == "References" or s.name.startswith("Appendix"):
            break
        keep.append(s.heading + s.text)
    lines = LINE_RE.findall("".join(keep))
    text = "".join(l for l, t in zip(lines, fence_tags(lines)) if t is None)
    return _HTML_COMMENT_RE.sub(" ", text)


def _mask_for_numbers(md: str) -> str:
    return _blank(mask_tags(md), _URL_RE)


def _materials_texts(paper_dir: Path) -> list[str]:
    """The text files under materials/, except materials/references/: reference-manager exports hold
    other papers' abstracts, and a number from a cited abstract has its own check (_cited_abstract_with)."""
    root = paper_dir / "materials"
    if not root.is_dir():
        return []
    return [p.read_text(encoding="utf-8", errors="replace")
            for p in sorted(root.rglob("*")) if p.is_file() and p.suffix.lower() in TEXT_SUFFIXES
            and p.relative_to(root).parts[0] != "references"]


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
    cited = cited_keys(md, entries)  # bare @key narrative citations count when they are library keys
    for k in cited:
        ln = _first_line(md, "@" + k)
        if k not in entries:
            items.add("citations", "fail", ln, f"citation key {k} is not in the library")
        elif not entries[k].verified_by:
            items.add("citations", "fail", ln, f"library entry {k} has no verified_by")
    for k in bare_unknown_keys(md, entries):
        items.add("citations", "warn", _first_line(md, "@" + k),
                  f"@{k} is not a library key, so it is not read as a citation; "
                  "to cite a paper, use its key from references/library.json")
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
        spans = _sentence_spans(text)
        seen = set()
        for pos, key, _ in citations(text):
            e = entries.get(key)
            if e is None or not e.title_only:
                continue
            s, t = next((a, b) for a, b in spans if a <= pos <= b)
            if (key, s) in seen:
                continue
            seen.add((key, s))
            line_idx = max(i for i, o in enumerate(offs[:-1]) if o <= pos)
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
    entries = {e.key: e for e in lib}
    line_starts = [0]
    for line in LINE_RE.findall(md):
        line_starts.append(line_starts[-1] + len(line))
    index = _sentence_index(md)
    for h in unmatched(_mask_for_numbers(md), _materials_texts(paper_dir), years):
        data = {"token": h.num.token, "context": h.context, "line": h.line_no}
        key = _cited_abstract_with(h, line_starts, index, entries)
        if key is not None:
            items.add("numbers", "pass", h.line_no,
                      f"number {h.num.token} is from the abstract of [@{key}], cited in the same sentence",
                      {**data, "key": key})
        else:
            items.add("numbers", "needs_ruling", h.line_no, f"number {h.num.token} not found in the materials",
                      data)


def _cited_abstract_with(h, line_starts: list[int], index: dict, entries: dict) -> str | None:
    """Key of a library entry cited in the number's sentence whose abstract holds the same number."""
    if h.line_no not in index:
        return None
    text, off, spans = index[h.line_no]
    pos = off + h.num.start - line_starts[h.line_no - 1]
    sentence = next((text[s:t] for s, t in spans if s <= pos <= t), "")
    for _, key, _ in citations(sentence):
        e = entries.get(key)
        if e is not None and e.abstract and matches(h.num, materials_numbers([e.abstract])):
            return key
    return None


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
    reported = {str(e.get("file", "")) for e in (info if isinstance(info, list) else [])}
    lines = LINE_RE.findall(md)
    for n, (line, tag) in enumerate(zip(lines, fence_tags(lines)), 1):
        if tag is not None:
            continue
        for t in _FIG_TARGET_RE.findall(line):
            if t not in reported and not (paper_dir / t).is_file():
                reported.add(t)
                items.add("figures", "fail", n, f"figure file {t} is missing")
    prose = _prose_lines(md)
    refs = {n: _references(l) for n, l in prose}
    for i, line in prose:
        m = _CAPTION_RE.match(line)
        if not m:
            continue
        kind, num = m.group(1), int(m.group(2))
        own = re.compile(rf"^\s*\*{kind}\s+{num}\s*:")
        if not any((kind, num) in r for n, r in refs.items() if not own.match(dict(prose)[n])):
            items.add("figures", "fail", i, f"{kind} {num} is never referenced in the text")


def _check_venue(md, paper_dir, settings, items: _Items) -> None:
    style = load_style(find_style(settings.style, paper_dir))
    _, secs = split_sections(md)
    have = {s.name.casefold() for s in secs}
    for name in style.sections:
        if section_name(name).casefold() not in have:
            items.add("venue", "fail", None, f"missing section: {name}")
    for st in style.required_statements:
        if section_name(st).casefold() not in have:
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
        for n, line in _prose_lines(md):
            for a in settings.authors:
                if a.strip() and re.search(rf"(?<!\w){re.escape(a.strip())}(?!\w)", line, re.I):
                    items.add("venue", "fail", n, f"author name {a} in a blind-review paper")


def run_check(paper_dir: Path, project_root: Path) -> list[CheckItem]:
    """Check paper.md and write check/report.json. The old report is deleted first, so a run that
    fails leaves none for `finalize` to report from."""
    paper_dir = Path(paper_dir)
    report_path(paper_dir).unlink(missing_ok=True)
    raw = (paper_dir / "paper.md").read_bytes()
    md = raw.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")  # as read_text() reads it
    lib = load_library(paper_dir)
    settings = load_settings(paper_dir)
    items = _Items()
    _check_citations(md, lib, items)
    _check_numbers(md, paper_dir, lib, settings, items)
    _check_figures(md, paper_dir, items)
    _check_venue(md, paper_dir, settings, items)
    _check_reference_text(md, items)
    built = items.build()
    write_report(paper_dir, built, _sha256(raw))  # finalize reads check/report.json
    return built


def _counts(items: list[CheckItem]) -> dict:
    return {s: sum(1 for i in items if i.status == s) for s in STATUSES}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def report_path(paper_dir: Path) -> Path:
    return Path(paper_dir) / "check" / "report.json"


def write_report(paper_dir: Path, items: list[CheckItem], paper_sha256: str) -> Path:
    """paper_sha256 is the hash of the paper.md bytes the items were found in."""
    path = report_path(paper_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"counts": _counts(items), "paper_sha256": paper_sha256,
                                "items": [asdict(i) for i in items]}, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    return path


class StaleReport(Exception):
    """check/report.json is missing, unreadable, or was made from another paper.md."""


def _load_report(paper_dir: Path) -> list[CheckItem]:
    path, pm = report_path(paper_dir), Path(paper_dir) / "paper.md"
    if not path.is_file():
        raise StaleReport(f"{path} is missing; run `po check run` first")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        items = [CheckItem(**d) for d in data["items"]]
    except (ValueError, TypeError, KeyError) as e:
        raise StaleReport(f"{path} is not a Check report ({e}); run `po check run` again") from e
    if not pm.is_file() or data.get("paper_sha256") != _sha256(pm.read_bytes()):
        raise StaleReport(f"paper.md changed after `po check run` made {path}; run `po check run` again")
    return items


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
    rulings = rulings if isinstance(rulings, dict) else {}
    problems, warns, allowed, passed = [], [], [], []
    for i in items:
        if i.status == "pass":
            passed.append(i)
        elif i.status == "needs_ruling":
            r = rulings.get(i.id)
            r = r if isinstance(r, dict) else {}
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
        reason = _collapse(str(r.get("reason") or "")) or "none given"
        s = f" Ruling: {_collapse(str(r.get('ruling')))}. Reason: {reason}."
        return s + (f" Arithmetic: {_collapse(str(r['arithmetic']))}" if r.get("arithmetic") else "")

    status_line = "READY" if not problems else f"NOT READY: {len(problems)} problems"
    lines = [f"Status: {status_line}", ""]
    for i, r in problems:
        lines.append(f"- FAIL {_where(i)}: {i.message}.{detail(r)}"
                     + (" No ruling." if i.status == "needs_ruling" and not r else ""))
    lines += [f"- WARN {_where(i)}: {i.message}" for i in warns]
    lines += [f"- ALLOWED {_where(i)}: {i.message}.{detail(r)}" for i, r in allowed]
    if not (problems or warns or allowed):
        lines.append("No problems found.")
    lines += [f"- PASS {_where(i)}: {i.message}." for i in passed]
    _write_check_section(paper_dir, "\n".join(lines))
    return {"ready": not problems, "problems": len(problems), "status_line": status_line,
            "needs_ruling": sum(1 for i in items if i.status == "needs_ruling")}


def _cmd_run(args) -> int:
    paper = Path(args.paper)
    project = Path(args.project) if args.project else paper.resolve().parent
    items = run_check(paper, project)
    emit({**_counts(items), "report": str(report_path(paper))})
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
                print(f"check finalize: rulings file {args.rulings} is not valid JSON: {e}", file=sys.stderr)
                return 2
            if not isinstance(rulings, dict):
                print(f"check finalize: rulings file {args.rulings} must hold a JSON object", file=sys.stderr)
                return 2
    try:
        out = finalize(paper, rulings)
    except StaleReport as e:
        print(f"check finalize: {e}", file=sys.stderr)
        return 2
    # a wrong or empty rulings path must never pass silently
    out["rulings_missing"] = bool(out["needs_ruling"]) and not rulings
    if out["rulings_missing"]:
        print(f"check finalize: {out['needs_ruling']} item(s) need a ruling, but the rulings file "
              f"{args.rulings or '(none given)'} is missing or empty; they count as problems",
              file=sys.stderr)
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
