"""paper.md sections, ownership, hand-edit detection and versioned drafts."""
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from .cli import common_parent, emit

FENCE_OPEN_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
H2_RE = re.compile(r"^## +(.*?)\s*$")
ANY_HEADING_RE = re.compile(r"^#{1,6}\s")
NUMBERING_RE = re.compile(r"^\d+(\.\d+)*\.?\s+")
LINE_RE = re.compile(r"[^\n]*\n|[^\n]+")
BLANK_END_RE = re.compile(r"\n[ \t]*\r?\n\Z")
TITLE = "Title"


@dataclass
class Section:
    heading: str  # the full `## ...` line without its line ending
    name: str     # heading text with numbering stripped
    text: str     # everything after the heading text, starting with its line ending


class HandEditConflict(Exception):
    def __init__(self, sections: list[str]):
        super().__init__("hand-edited sections: " + ", ".join(sections))
        self.sections = sections


def fence_tags(lines: list[str]) -> list[str | None]:
    """Per line: 'open', 'in', 'close' for fenced code (CommonMark rules), else None.

    A closing fence uses the opening character and is at least as long; an
    unclosed fence runs to the end of the text."""
    tags: list[str | None] = []
    ch, size = None, 0
    for line in lines:
        m = FENCE_OPEN_RE.match(line.rstrip("\r\n"))
        if ch is None:
            if m and not (m.group(1)[0] == "`" and "`" in m.group(2)):
                ch, size = m.group(1)[0], len(m.group(1))
                tags.append("open")
            else:
                tags.append(None)
        elif m and m.group(1)[0] == ch and len(m.group(1)) >= size and not m.group(2).strip():
            tags.append("close")
            ch = None
        else:
            tags.append("in")
    return tags


def detect_eol(md: str) -> str:
    return "\r\n" if "\r\n" in md else "\n"


def ensure_blank(text: str, eol: str) -> str:
    """Make text end with a blank line; text that already does is returned unchanged."""
    if not text or BLANK_END_RE.search(text):
        return text
    return text.rstrip("\r\n") + eol * 2


def section_name(heading: str) -> str:
    return NUMBERING_RE.sub("", heading.strip())


def split_sections(md: str) -> tuple[str, list[Section]]:
    lines = LINE_RE.findall(md)
    pre: list[str] = []
    heads: list[tuple[str, list[str]]] = []
    for line, tag in zip(lines, fence_tags(lines)):
        if tag is None and H2_RE.match(line.rstrip("\r\n")):
            heads.append((line, [line]))
        elif heads:
            heads[-1][1].append(line)
        else:
            pre.append(line)
    sections = []
    for line, body in heads:
        bare = line.rstrip("\r\n")
        sections.append(Section(bare, section_name(H2_RE.match(bare).group(1)), "".join(body)[len(bare):]))
    return "".join(pre), sections


def assemble(preamble: str, sections: list[Section]) -> str:
    return preamble + "".join(s.heading + s.text for s in sections)


def owner_of(name: str, style) -> str:
    name = section_name(name)
    if name == "References":
        return "script"
    if name in style.literature_sections:
        return "literature-writer"
    return "section-writer"


def _collapse(s: str) -> str:
    return " ".join(s.split())


def paragraphs(md: str) -> list[str]:
    out: list[str] = []
    cur: list[str] = []

    def flush():
        if cur:
            out.append("\n".join(cur))
            cur.clear()

    lines = [l.rstrip("\r") for l in md.split("\n")]
    for line, tag in zip(lines, fence_tags(lines)):
        if tag == "open":
            flush()
            cur.append(line)
        elif tag == "in":
            cur.append(line)
        elif tag == "close":
            cur.append(line)
            flush()
        elif ANY_HEADING_RE.match(line) or not line.strip():
            flush()
        else:
            cur.append(line)
    flush()
    return out


def _without_references(md: str) -> str:
    pre, secs = split_sections(md)
    return assemble(pre, [s for s in secs if s.name != "References"])


def _is_edited(p: str, known: set[str], prot: set[str]) -> bool:
    c = _collapse(p)
    return c not in known or c in prot


def hand_edited_paragraphs(current_md: str, tool_md: str, protected: Sequence[str] = ()) -> list[str]:
    known = {_collapse(p) for p in paragraphs(tool_md)}
    prot = {_collapse(p) for p in protected}
    return [p for p in paragraphs(_without_references(current_md)) if _is_edited(p, known, prot)]


def sections_with_hand_edits(current_md: str, tool_md: str, protected: Sequence[str] = ()) -> list[str]:
    known = {_collapse(p) for p in paragraphs(tool_md)}
    prot = {_collapse(p) for p in protected}
    pre, secs = split_sections(current_md)
    out: list[str] = []
    if any(_is_edited(p, known, prot) for p in paragraphs(pre)):
        out.append(TITLE)
    for s in secs:
        if s.name != "References" and s.name not in out and any(
                _is_edited(p, known, prot) for p in paragraphs(s.text)):
            out.append(s.name)
    return out


def _order(style) -> list[str]:
    names = list(style.sections) + [o for o in style.optional_sections if o != "Appendix"]
    names += ["References", "Appendix"]
    return list(dict.fromkeys(names))


def _insert_pos(merged: list[Section], name: str, order: list[str]) -> int:
    tail = next((i for i, c in enumerate(merged) if c.name in ("References", "Appendix")), len(merged))
    if name not in order:
        return tail
    r = order.index(name)
    ranked = [(order.index(c.name), i) for i, c in enumerate(merged) if c.name in order]
    before = [(rk, i) for rk, i in ranked if rk < r]
    if before:
        best = max(rk for rk, _ in before)
        return min(i for rk, i in before if rk == best) + 1
    after = [i for rk, i in ranked if rk > r]
    return min(after) if after else tail


def _convert(s: Section, eol: str) -> Section:
    text = s.text.replace("\r\n", "\n")
    return Section(s.heading.rstrip("\r\n"), s.name, text.replace("\n", eol) if eol != "\n" else text)


def _tidy(text: str, last: bool, eol: str) -> str:
    return text.rstrip("\r\n") + eol * (1 if last else 2)


def replace_owned(current_md: str, new_md: str, owner: str, style, only: list[str] | None = None,
                  tool_md: str | None = None, force_sections: Sequence[str] = (),
                  protected: Sequence[str] = ()) -> tuple[str, list[str]]:
    warnings: list[str] = []
    eol = detect_eol(current_md)
    preamble, cur = split_sections(current_md)
    new_pre, new = split_sections(new_md)
    only_set = None if only is None else {section_name(o) for o in only}
    force = {section_name(f) for f in force_sections}
    title_owner = owner_of(TITLE, style)

    wanted: list[Section] = []
    for s in new:
        o = owner_of(s.name, style)
        if o != owner:
            warnings.append(f"ignored section {s.name}: owned by {o}, not {owner}")
        elif (only_set is None or s.name in only_set) and all(w.name != s.name for w in wanted):
            wanted.append(_convert(s, eol))
    replace_title = False
    if new_pre.strip():
        if owner != title_owner:
            warnings.append(f"ignored title and preamble: owned by {title_owner}, not {owner}")
        else:
            replace_title = only_set is None or TITLE in only_set

    if tool_md is not None:
        edited = set(sections_with_hand_edits(current_md, tool_md, protected))
        targets = {s.name for s in wanted if any(c.name == s.name for c in cur)}
        if replace_title:
            targets.add(TITLE)
        conflict = [n for n in dict.fromkeys([TITLE] + [c.name for c in cur])
                    if n in targets and n in edited and n not in force]
        if conflict:
            raise HandEditConflict(conflict)

    merged = list(cur)
    for s in wanted:
        idx = next((i for i, c in enumerate(merged) if c.name == s.name), None)
        if idx is not None:
            merged[idx] = s
        else:
            merged.insert(_insert_pos(merged, s.name, _order(style)), s)
    touched = {id(s) for s in wanted}

    if replace_title:
        preamble = new_pre.replace("\r\n", "\n").replace("\n", eol)
        preamble = ensure_blank(preamble, eol) if merged else preamble.rstrip("\r\n") + eol
    out: list[Section] = []
    for i, s in enumerate(merged):
        if id(s) in touched:
            if out:
                out[-1] = Section(out[-1].heading, out[-1].name, ensure_blank(out[-1].text, eol))
            else:
                preamble = ensure_blank(preamble, eol)
            s = Section(s.heading, s.name, _tidy(s.text, i == len(merged) - 1, eol))
        out.append(s)
    return assemble(preamble, out), warnings


def save_version(paper_dir, md: str, kind: str = "tool") -> Path:
    from .state import record_tool_version
    paper_dir = Path(paper_dir)
    drafts = paper_dir / "drafts"
    drafts.mkdir(parents=True, exist_ok=True)
    nums = [int(m.group(1)) for f in drafts.iterdir() if (m := re.match(r"v(\d+)(-user)?\.md$", f.name))]
    n = max(nums, default=0) + 1
    name = f"v{n}.md" if kind == "tool" else f"v{n}-user.md"
    path = drafts / name
    _write(path, md)
    if kind == "tool":
        record_tool_version(paper_dir, f"drafts/{name}")
    return path


# --- CLI -------------------------------------------------------------------

def _style(args):
    from .settings import SettingsError, load_settings
    from .style import StyleNotFound, find_style, load_style
    try:
        s = load_settings(Path(args.paper))
        return load_style(find_style(s.style, Path(args.paper)))
    except (SettingsError, StyleNotFound) as e:
        print(e, file=sys.stderr)
        return None


def _read(p: Path) -> str:
    with open(p, encoding="utf-8", newline="") as f:
        return f.read()


def _write(p: Path, text: str) -> None:
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def _read_paper(paper: Path, required: bool) -> str | None:
    p = paper / "paper.md"
    if p.is_file():
        return _read(p)
    if required:
        print(f"{p} not found", file=sys.stderr)
        return None
    return ""


def _tool_md(paper: Path) -> str | None:
    from .state import last_tool_version
    v = last_tool_version(paper)
    return _read(v) if v and v.is_file() else None


def _record_provenance(paper: Path, current: str, prev: str | None, new_md: str, prot: list[str]) -> None:
    """Remember hand-edited paragraphs before `new_md` becomes the tool version, so they stay protected."""
    from .state import set_protected
    keep = list(prot)
    if prev is not None:
        keep += hand_edited_paragraphs(current, prev, prot)
    present = {_collapse(p) for p in paragraphs(new_md)}
    out, seen = [], set()
    for p in keep:
        c = _collapse(p)
        if c in present and c not in seen:
            seen.add(c)
            out.append(p)
    set_protected(paper, out)


def _cmd_replace(args) -> int:
    from .state import get_protected
    paper = Path(args.paper)
    style = _style(args)
    src = Path(args.src)
    if style is None or not src.is_file():
        if style is not None:
            print(f"{src} not found", file=sys.stderr)
        return 2
    current = _read_paper(paper, False)
    prev, prot = _tool_md(paper), get_protected(paper)
    try:
        merged, warns = replace_owned(current, _read(src), args.owner, style, only=args.only,
                                      tool_md=prev, force_sections=args.force or [], protected=prot)
    except HandEditConflict as e:
        emit({"conflict": e.sections})
        return 1
    paper.mkdir(parents=True, exist_ok=True)
    _write(paper / "paper.md", merged)
    _record_provenance(paper, current, prev, merged, prot)
    v = save_version(paper, merged, "tool")
    emit({"written": str(paper / "paper.md"), "version": str(v), "warnings": warns})
    return 0


def late_hand_edits(current_md: str, tool_md: str | None, protected: Sequence[str], new_md: str) -> list[str]:
    """Hand edits made since the protected list was last set (e.g. during a review) that new_md lacks.

    Paragraphs already protected are left to `review restore` (keep) or `review changes` (revise)."""
    if tool_md is None:
        return []
    prot = {_collapse(p) for p in protected}
    kept = {_collapse(p) for p in paragraphs(new_md)}
    return [p for p in hand_edited_paragraphs(current_md, tool_md)
            if _collapse(p) not in prot and _collapse(p) not in kept]


def _user_copy(paper: Path, md: str) -> Path:
    """A user version holding md: an identical existing one, else a new one."""
    drafts = paper / "drafts"
    same = [f for f in sorted(drafts.glob("v*-user.md")) if _read(f) == md] if drafts.is_dir() else []
    return same[-1] if same else save_version(paper, md, "user")


def _cmd_accept(args) -> int:
    """Adopt a tool-made draft (an accepted review candidate) as paper.md and a tool version.

    Only the current paper.md's hand edits (vs the previous tool version) are recorded; the
    adopted draft's own changes are tool text and never count as hand edits. Hand edits the
    draft would drop (made after the last protect) stop the command unless --force; either
    way the current paper.md is first saved as a user version."""
    from .state import get_protected
    paper = Path(args.paper)
    src = Path(args.src)
    if not src.is_file():
        print(f"{src} not found", file=sys.stderr)
        return 2
    new_md = _read(src)
    current = _read_paper(paper, False)
    prev, prot = _tool_md(paper), get_protected(paper)
    late = late_hand_edits(current, prev, prot, new_md)
    saved = _user_copy(paper, current) if late else None
    if late and not args.force:
        emit({"hand_edits_after_review": late, "saved": str(saved)})
        return 1
    _record_provenance(paper, current, prev, new_md, prot)
    paper.mkdir(parents=True, exist_ok=True)
    _write(paper / "paper.md", new_md)
    v = save_version(paper, new_md, "tool")
    out = {"written": str(paper / "paper.md"), "version": str(v)}
    if saved is not None:
        out["saved"] = str(saved)
    emit(out)
    return 0


def _cmd_edits(args) -> int:
    from .state import get_protected
    paper = Path(args.paper)
    current = _read_paper(paper, False)
    tool = _tool_md(paper)
    if tool is None:
        emit({"sections": [], "paragraphs": 0})
    else:
        prot = get_protected(paper)
        emit({"sections": sections_with_hand_edits(current, tool, prot),
              "paragraphs": len(hand_edited_paragraphs(current, tool, prot))})
    return 0


def _cmd_references(args) -> int:
    from .library import load_library
    from .references import update_references
    paper = Path(args.paper)
    style = _style(args)
    if args.file:
        target = Path(args.file)
        if not target.is_file():
            print(f"{target} not found", file=sys.stderr)
            return 2
        current = _read(target)
    else:
        target, current = paper / "paper.md", _read_paper(paper, True)
    if style is None or current is None:
        return 2
    entries = {e.key: e for e in load_library(paper)}
    _write(target, update_references(current, entries, style.citation_style))
    emit({"written": str(target)})
    return 0


def _cmd_save_version(args) -> int:
    paper = Path(args.paper)
    current = _read_paper(paper, True)
    if current is None:
        return 2
    if args.kind == "tool":
        from .state import get_protected
        _record_provenance(paper, current, _tool_md(paper), current, get_protected(paper))
    emit({"version": str(save_version(paper, current, args.kind))})
    return 0


def register(sub) -> None:
    group = sub.add_parser("paper", help="paper.md sections, ownership and versions")
    cmds = group.add_subparsers(dest="paper_command")
    r = cmds.add_parser("replace", parents=[common_parent()], help="replace the sections an owner owns")
    r.add_argument("--owner", required=True, choices=["literature-writer", "section-writer", "script"])
    r.add_argument("--from", dest="src", required=True, help="file holding the new sections")
    r.add_argument("--only", nargs="+", default=None, metavar="NAME")
    r.add_argument("--force", nargs="+", default=None, metavar="NAME")
    r.set_defaults(func=_cmd_replace)
    a = cmds.add_parser("accept", parents=[common_parent()],
                        help="adopt a revised draft as paper.md and a tool version")
    a.add_argument("--from", dest="src", required=True, help="the draft to adopt")
    a.add_argument("--force", action="store_true",
                   help="adopt it even if it drops hand edits made after the last protect (they are saved first)")
    a.set_defaults(func=_cmd_accept)
    cmds.add_parser("edits", parents=[common_parent()], help="report hand edits").set_defaults(func=_cmd_edits)
    ref = cmds.add_parser("references", parents=[common_parent()], help="regenerate References")
    ref.add_argument("--file", default=None, help="rewrite this file's References instead of paper.md")
    ref.set_defaults(func=_cmd_references)
    s = cmds.add_parser("save-version", parents=[common_parent()], help="save paper.md as a draft version")
    s.add_argument("--kind", choices=["tool", "user"], default="tool")
    s.set_defaults(func=_cmd_save_version)
