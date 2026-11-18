"""paper.md sections, ownership, hand-edit detection and versioned drafts."""
import json
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from .cli import common_parent, emit

FENCE_RE = re.compile(r"^\s*(```|~~~)")
H2_RE = re.compile(r"^## +(.*?)\s*$")
ANY_HEADING_RE = re.compile(r"^#{1,6}\s")
NUMBERING_RE = re.compile(r"^\d+(\.\d+)*\.?\s+")
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


def section_name(heading: str) -> str:
    return NUMBERING_RE.sub("", heading.strip())


def split_sections(md: str) -> tuple[str, list[Section]]:
    pre: list[str] = []
    heads: list[tuple[str, list[str]]] = []
    in_fence = False
    for line in md.splitlines(keepends=True):
        if FENCE_RE.match(line):
            in_fence = not in_fence
        m = None if in_fence or FENCE_RE.match(line) else H2_RE.match(line.rstrip("\r\n"))
        if m:
            heads.append((line, [line]))
        elif heads:
            heads[-1][1].append(line)
        else:
            pre.append(line)
    sections = []
    for line, lines in heads:
        bare = line.rstrip("\r\n")
        sections.append(Section(bare, section_name(H2_RE.match(bare).group(1)), "".join(lines)[len(bare):]))
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
    in_fence = False

    def flush():
        if cur:
            out.append("\n".join(cur))
            cur.clear()

    for line in md.splitlines():
        if FENCE_RE.match(line):
            if not in_fence:
                flush()
            cur.append(line)
            if in_fence:
                flush()
            in_fence = not in_fence
        elif in_fence:
            cur.append(line)
        elif ANY_HEADING_RE.match(line):
            flush()
        elif not line.strip():
            flush()
        else:
            cur.append(line)
    flush()
    return out


def _without_references(md: str) -> str:
    pre, secs = split_sections(md)
    return assemble(pre, [s for s in secs if s.name != "References"])


def hand_edited_paragraphs(current_md: str, tool_md: str) -> list[str]:
    known = {_collapse(p) for p in paragraphs(tool_md)}
    return [p for p in paragraphs(_without_references(current_md)) if _collapse(p) not in known]


def sections_with_hand_edits(current_md: str, tool_md: str) -> list[str]:
    known = {_collapse(p) for p in paragraphs(tool_md)}
    pre, secs = split_sections(current_md)
    out = []
    if any(_collapse(p) not in known for p in paragraphs(pre)):
        out.append(TITLE)
    for s in secs:
        if s.name != "References" and any(_collapse(p) not in known for p in paragraphs(s.text)):
            out.append(s.name)
    return out


def _order(style) -> list[str]:
    names = list(style.sections) + [o for o in style.optional_sections if o != "Appendix"]
    names += ["References", "Appendix"]
    return list(dict.fromkeys(names))


def _tidy(text: str, last: bool) -> str:
    return text.rstrip("\n") + ("\n" if last else "\n\n")


def replace_owned(current_md: str, new_md: str, owner: str, style, only: list[str] | None = None,
                  tool_md: str | None = None, force_sections: Sequence[str] = ()) -> tuple[str, list[str]]:
    warnings: list[str] = []
    cur_pre, cur = split_sections(current_md)
    new_pre, new = split_sections(new_md)
    only_set = None if only is None else {section_name(o) for o in only}
    force = {section_name(f) for f in force_sections}

    wanted: list[Section] = []
    for s in new:
        o = owner_of(s.name, style)
        if o != owner:
            warnings.append(f"ignored section {s.name}: owned by {o}, not {owner}")
        elif only_set is None or s.name in only_set:
            wanted.append(s)
    replace_title = (owner == owner_of(TITLE, style) and bool(new_pre.strip())
                     and (only_set is None or TITLE in only_set))

    if tool_md is not None:
        edited = set(sections_with_hand_edits(current_md, tool_md))
        targets = {s.name for s in wanted if any(c.name == s.name for c in cur)}
        if replace_title:
            targets.add(TITLE)
        conflict = [n for n in ([TITLE] + [c.name for c in cur])
                    if n in targets and n in edited and n not in force]
        if conflict:
            raise HandEditConflict(conflict)

    preamble = cur_pre
    if replace_title:
        preamble = new_pre.rstrip("\n") + "\n\n" if cur or wanted else new_pre
    touched: set[str] = set()
    order = _order(style)
    unknown_rank = order.index("References") - 0.5

    def rank(n: str) -> float:
        return order.index(n) if n in order else unknown_rank

    merged = list(cur)
    for s in wanted:
        touched.add(s.name)
        idx = next((i for i, c in enumerate(merged) if c.name == s.name), None)
        if idx is not None:
            merged[idx] = s
            continue
        pos = next((i for i, c in enumerate(merged) if rank(c.name) > rank(s.name)), len(merged))
        merged.insert(pos, s)
    for i, s in enumerate(merged):
        prev_touched = i > 0 and merged[i - 1].name in touched
        if s.name in touched or prev_touched:
            merged[i] = Section(s.heading, s.name, _tidy(s.text, i == len(merged) - 1))
    if merged and preamble and not preamble.endswith("\n\n") and (merged[0].name in touched):
        preamble = preamble.rstrip("\n") + "\n\n"
    return assemble(preamble, merged), warnings


def save_version(paper_dir, md: str, kind: str = "tool") -> Path:
    from .state import record_tool_version
    paper_dir = Path(paper_dir)
    drafts = paper_dir / "drafts"
    drafts.mkdir(parents=True, exist_ok=True)
    nums = [int(m.group(1)) for f in drafts.iterdir() if (m := re.match(r"v(\d+)(-user)?\.md$", f.name))]
    n = max(nums, default=0) + 1
    name = f"v{n}.md" if kind == "tool" else f"v{n}-user.md"
    path = drafts / name
    path.write_text(md, encoding="utf-8")
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


def _read_paper(paper: Path, required: bool) -> str | None:
    p = paper / "paper.md"
    if p.is_file():
        return p.read_text(encoding="utf-8")
    if required:
        print(f"{p} not found", file=sys.stderr)
        return None
    return ""


def _tool_md(paper: Path) -> str | None:
    from .state import last_tool_version
    v = last_tool_version(paper)
    return v.read_text(encoding="utf-8") if v and v.is_file() else None


def _cmd_replace(args) -> int:
    paper = Path(args.paper)
    style = _style(args)
    src = Path(args.src)
    if style is None or not src.is_file():
        if style is not None:
            print(f"{src} not found", file=sys.stderr)
        return 2
    current = _read_paper(paper, False)
    try:
        merged, warns = replace_owned(current, src.read_text(encoding="utf-8"), args.owner, style,
                                      only=args.only, tool_md=_tool_md(paper), force_sections=args.force or [])
    except HandEditConflict as e:
        emit({"conflict": e.sections})
        return 1
    paper.mkdir(parents=True, exist_ok=True)
    (paper / "paper.md").write_text(merged, encoding="utf-8")
    v = save_version(paper, merged, "tool")
    emit({"written": str(paper / "paper.md"), "version": str(v), "warnings": warns})
    return 0


def _cmd_edits(args) -> int:
    paper = Path(args.paper)
    if _style(args) is None:
        return 2
    current = _read_paper(paper, False)
    tool = _tool_md(paper)
    if tool is None:
        emit({"sections": [], "paragraphs": 0})
    else:
        emit({"sections": sections_with_hand_edits(current, tool),
              "paragraphs": len(hand_edited_paragraphs(current, tool))})
    return 0


def _cmd_references(args) -> int:
    from .library import load_library
    from .references import update_references
    paper = Path(args.paper)
    style = _style(args)
    current = _read_paper(paper, True)
    if style is None or current is None:
        return 2
    entries = {e.key: e for e in load_library(paper)}
    (paper / "paper.md").write_text(update_references(current, entries, style.citation_style), encoding="utf-8")
    emit({"written": str(paper / "paper.md")})
    return 0


def _cmd_save_version(args) -> int:
    paper = Path(args.paper)
    current = _read_paper(paper, True)
    if current is None:
        return 2
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
    cmds.add_parser("edits", parents=[common_parent()], help="report hand edits").set_defaults(func=_cmd_edits)
    cmds.add_parser("references", parents=[common_parent()],
                    help="regenerate References").set_defaults(func=_cmd_references)
    s = cmds.add_parser("save-version", parents=[common_parent()], help="save paper.md as a draft version")
    s.add_argument("--kind", choices=["tool", "user"], default="tool")
    s.set_defaults(func=_cmd_save_version)
