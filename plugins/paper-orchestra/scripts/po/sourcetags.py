"""Verifiable source tags for experiment_log.md (grammar: docs/source-tags.md)."""
import csv
import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

from .cli import common_parent, emit
from .numtok import Num, find_numbers, is_trivial, values_match

_OPEN_RE = re.compile(r"\[(src(?:#([A-Za-z0-9_-]+))?|calc|manual):")
_UNSUPPORTED = {".ipynb", ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg", ".pdf"}
_FNS = {"mean", "std", "pstd", "min", "max", "sum", "sub", "div"}


class Unreadable(Exception):
    pass


@dataclass
class Tag:
    kind: str
    id: str | None
    path: str | None
    locator: dict
    fn: str | None
    args: list
    text: str | None
    line_no: int
    written: Num | None
    span: tuple = field(default=(0, 0), repr=False)


@dataclass
class TagResult:
    tag: Tag
    status: str
    source_value: float | None
    reason: str


def _find_close(line: str, start: int) -> int:
    """Index of the ']' closing the tag opened before `start`, or -1."""
    depth = 1
    for i in range(start, len(line)):
        if line[i] == "[":
            depth += 1
        elif line[i] == "]":
            depth -= 1
            if depth == 0:
                return i
    return -1


def _line_tags(line: str) -> list[tuple[int, int, str, str | None, str]]:
    found, pos = [], 0
    while True:
        m = _OPEN_RE.search(line, pos)
        if not m:
            return found
        close = _find_close(line, m.end())
        if close < 0:
            return found
        kind = "src" if m.group(1).startswith("src") else m.group(1)
        found.append((m.start(), close + 1, kind, m.group(2), line[m.end():close].strip()))
        pos = close + 1


def _mask(line: str, tags) -> str:
    chars = list(line)
    for s, e, *_ in tags:
        chars[s:e] = " " * (e - s)
    return "".join(chars)


def parse_tags(markdown: str) -> list[Tag]:
    out: list[Tag] = []
    for ln, line in enumerate(markdown.splitlines(), 1):
        tags = _line_tags(line)
        if not tags:
            continue
        nums = find_numbers(_mask(line, tags))
        for s, e, kind, tid, body in tags:
            written = None
            for n in nums:
                if n.end <= s:
                    written = n
            tag = Tag(kind, tid, None, {}, None, [], None, ln, written, (s, e))
            if kind == "manual":
                tag.text = body
            elif kind == "calc":
                m = re.fullmatch(r"(\w+)\((.*)\)", body, re.S)
                if m:
                    tag.fn = m.group(1)
                    tag.args = [a.strip() for a in m.group(2).split(",") if a.strip()]
            else:
                parts = re.split(r"\s+\|\s+", body)
                tag.path = parts[0].strip()
                for p in parts[1:]:
                    k, _, v = p.partition("=")
                    tag.locator[k.strip()] = v.strip()
            out.append(tag)
    return out


def _to_float(s: str) -> float:
    t = s.strip().replace(",", "")
    if t.endswith("%"):
        t = t[:-1]
    try:
        return float(t)
    except ValueError:
        raise Unreadable(f"not a number: {s.strip()!r}")


def _table_cell(path: Path, loc: dict) -> float:
    delim = "\t" if path.suffix.lower() == ".tsv" else ","
    with path.open(newline="", encoding="utf-8-sig") as f:
        rows = [r for r in csv.reader(f, delimiter=delim) if any(c.strip() for c in r)]
    if not rows:
        raise Unreadable("empty table")
    header, data = rows[0], rows[1:]
    col = loc.get("col")
    if col is None or "row" not in loc:
        raise Unreadable("table tag needs row= and col=")
    if col not in header:
        raise Unreadable(f"no column {col!r}")
    ci = header.index(col)
    sel = loc["row"]
    row = None
    if sel == "last":
        row = data[-1] if data else None
    elif sel.startswith("#"):
        try:
            idx = int(sel[1:])
        except ValueError:
            raise Unreadable(f"bad row selector {sel!r}")
        row = data[idx - 1] if 1 <= idx <= len(data) else None
    else:
        row = next((r for r in data if r and r[0] == sel), None)
    if row is None:
        raise Unreadable(f"no row {sel!r}")
    if ci >= len(row):
        raise Unreadable("missing cell")
    return _to_float(row[ci])


def _json_cell(path: Path, loc: dict) -> float:
    if "path" not in loc:
        raise Unreadable("json tag needs path=")
    try:
        cur = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as e:
        raise Unreadable(f"invalid json: {e}")
    for key in loc["path"].split("."):
        try:
            if isinstance(cur, list):
                cur = cur[int(key)]
            else:
                cur = cur[key]
        except (KeyError, IndexError, ValueError, TypeError):
            raise Unreadable(f"no value at path {loc['path']!r}")
    if isinstance(cur, bool) or not isinstance(cur, (int, float, str)):
        raise Unreadable(f"value at {loc['path']!r} is not a number")
    return _to_float(str(cur))


def _text_cell(path: Path, loc: dict) -> float:
    try:
        n = int(loc.get("line", ""))
    except ValueError:
        raise Unreadable("text tag needs line=<n>")
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if not 1 <= n <= len(lines):
        raise Unreadable(f"no line {n}")
    line = lines[n - 1]
    pat = loc.get("pattern")
    if pat is None:
        return _to_float(line)
    try:
        m = re.search(pat, line)
    except re.error as e:
        raise Unreadable(f"bad pattern: {e}")
    if not m or not m.groups():
        raise Unreadable("pattern did not match")
    if m.group(1) is None:
        raise Unreadable("pattern group did not match")
    return _to_float(m.group(1))


def resolve_src(tag: Tag, project_root: Path) -> float:
    if not tag.path:
        raise Unreadable("no path")
    if "|" in tag.path:
        raise Unreadable("fields must be separated by ' | ' (with spaces)")
    path = Path(project_root) / tag.path
    suffix = path.suffix.lower()
    if suffix in _UNSUPPORTED:
        raise Unreadable(f"unsupported file type {suffix}")
    if not path.is_file():
        raise Unreadable(f"missing file {tag.path}")
    try:
        if suffix in (".csv", ".tsv"):
            value = _table_cell(path, tag.locator)
        elif suffix == ".json":
            value = _json_cell(path, tag.locator)
        else:
            value = _text_cell(path, tag.locator)
    except (OSError, UnicodeDecodeError, csv.Error) as e:
        raise Unreadable(f"cannot read {tag.path}: {e}")
    if "scale" in tag.locator:
        value *= _to_float(tag.locator["scale"])
    return value


def _calc(tag: Tag, values: dict) -> float:
    if tag.fn not in _FNS:
        raise Unreadable(f"unknown calc function {tag.fn!r}")
    if not tag.args:
        raise Unreadable("calc has no arguments")
    xs = []
    for a in tag.args:
        if a not in values:
            raise Unreadable(f"unknown id {a!r}")
        if values[a] is None:
            raise Unreadable(f"id {a!r} is unreadable")
        xs.append(values[a])
    fn = tag.fn
    if fn in ("sub", "div"):
        if len(xs) != 2:
            raise Unreadable(f"{fn} takes exactly 2 arguments")
        if fn == "sub":
            return xs[0] - xs[1]
        if xs[1] == 0:
            raise Unreadable("division by zero")
        return xs[0] / xs[1]
    if fn == "mean":
        return sum(xs) / len(xs)
    if fn == "sum":
        return sum(xs)
    if fn == "min":
        return min(xs)
    if fn == "max":
        return max(xs)
    mu = sum(xs) / len(xs)
    ss = sum((x - mu) ** 2 for x in xs)
    if fn == "pstd":
        return math.sqrt(ss / len(xs))
    if len(xs) < 2:
        raise Unreadable("std needs at least 2 values")
    return math.sqrt(ss / (len(xs) - 1))


def _read_log(log_path: Path) -> str:
    try:
        return Path(log_path).read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise Unreadable(f"{log_path} is not valid UTF-8")


def read_log(log_path: Path) -> str:
    """Read a log as UTF-8; raises Unreadable if it cannot be decoded."""
    return _read_log(log_path)


def verify_text(text: str, project_root: Path) -> list[TagResult]:
    return _verify_text(text, project_root)


def summarize(results: list[TagResult]) -> dict:
    return {s: sum(1 for r in results if r.status == s)
            for s in ("ok", "mismatch", "unreadable", "manual")}


def verify_log(log_path: Path, project_root: Path) -> list[TagResult]:
    """Raises Unreadable if the log itself cannot be decoded."""
    return _verify_text(_read_log(log_path), project_root)


def _verify_text(text: str, project_root: Path) -> list[TagResult]:
    values: dict = {}
    results: list[TagResult] = []
    for tag in parse_tags(text):
        if tag.kind == "manual":
            results.append(TagResult(tag, "manual", None, tag.text or ""))
            continue
        try:
            if tag.kind == "src":
                value = resolve_src(tag, Path(project_root))
            else:
                value = _calc(tag, values)
        except Unreadable as e:
            if tag.id:
                values[tag.id] = None
            results.append(TagResult(tag, "unreadable", None, str(e)))
            continue
        if tag.id:
            values[tag.id] = value
        if tag.written is None:
            results.append(TagResult(tag, "unreadable", value, "no number before the tag"))
        elif values_match(tag.written.value, tag.written.decimals, value):
            results.append(TagResult(tag, "ok", value, ""))
        else:
            results.append(TagResult(tag, "mismatch", value,
                                     f"written {tag.written.token}, source {value:g}"))
    return results


_HEADING_NUM = re.compile(r"^\s{0,3}#+\s+\d+(?:\.\d+)*\.?(?=\s|$)")
_LIST_MARK = re.compile(r"^\s*\d+[.)](?=\s)")


def untagged_numbers(markdown: str) -> list[tuple[int, str]]:
    out = []
    for ln, line in enumerate(markdown.splitlines(), 1):
        tags = _line_tags(line)
        masked = _mask(line, tags)
        skip_to = 0
        m = _HEADING_NUM.match(masked) or _LIST_MARK.match(masked)
        if m:
            skip_to = m.end()
        last_tag_start = max((t[0] for t in tags), default=-1)
        for n in find_numbers(masked):
            if n.start < skip_to or is_trivial(n):
                continue
            if last_tag_start >= n.end:
                continue
            out.append((ln, n.token))
    return out


def _cmd_verify(args) -> int:
    paper = Path(args.paper)
    project = Path(args.project) if args.project else paper.resolve().parent
    log = paper / "materials" / "experiment_log.md"
    if not log.is_file():
        emit({"error": f"missing {log}"})
        return 2
    try:
        text = _read_log(log)
    except (Unreadable, OSError) as e:
        emit({"error": str(e)})
        return 2
    results = _verify_text(text, project)
    counts = summarize(results)
    untagged = untagged_numbers(text)
    items = [{"line": r.tag.line_no, "kind": r.tag.kind, "id": r.tag.id,
              "status": r.status, "written": r.tag.written.token if r.tag.written else None,
              "source_value": r.source_value, "reason": r.reason} for r in results]
    emit({**counts, "untagged": len(untagged),
          "untagged_items": [{"line": a, "token": b} for a, b in untagged], "items": items})
    return 1 if counts["mismatch"] or counts["unreadable"] else 0


def register(sub) -> None:
    group = sub.add_parser("log", help="experiment log checks")
    cmds = group.add_subparsers(dest="log_command")
    v = cmds.add_parser("verify", parents=[common_parent()],
                        help="check every tagged number against its source file")
    v.set_defaults(func=_cmd_verify)
