"""Citation keys in paper.md and the generated References section."""
import re

from .paper import FENCE_RE, Section, assemble, split_sections

BRACKET_RE = re.compile(r"\[([^\[\]]*@[^\[\]]*)\]")
KEY_RE = re.compile(r"(?<![\w@])@(\w(?:[\w:.\-]*\w)?)")
INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
MAX_AUTHORS = 6


def _prose(md: str) -> str:
    """md without fenced blocks, inline code and the References section."""
    pre, secs = split_sections(md)
    text = assemble(pre, [s for s in secs if s.name != "References"])
    out, in_fence = [], False
    for line in text.splitlines():
        if FENCE_RE.match(line):
            in_fence = not in_fence
        elif not in_fence:
            out.append(INLINE_CODE_RE.sub("", line))
    return "\n".join(out)


def cited_keys(md: str) -> list[str]:
    seen: dict[str, None] = {}
    for group in BRACKET_RE.findall(_prose(md)):
        for k in KEY_RE.findall(group):
            seen.setdefault(k)
    return list(seen)


def _line(e) -> str:
    authors = list(e.authors or [])
    names = ", ".join(authors[:MAX_AUTHORS]) + (", et al." if len(authors) > MAX_AUTHORS else "")
    head = names if names.endswith(".") else (names + "." if names else "")
    title = (e.title or "").strip()
    title = title if title.endswith((".", "?", "!")) else title + "."
    year = e.year if e.year is not None else "n.d."
    venue = e.venue or e.journal
    where = ", ".join(p for p in (f"*{venue}*" if venue else "", e.volume, e.pages) if p)
    parts = [f"- [@{e.key}]", head, f"({year}).", title]
    if where:
        parts.append(where + ".")
    if e.doi:
        parts.append(f"https://doi.org/{e.doi}")
    return " ".join(p for p in parts if p)


def render_references(entries: dict, cited: list[str], citation_style: str) -> str:
    keys = [k for k in cited if k in entries]
    if citation_style == "author-year":
        keys = sorted(keys, key=lambda k: (k.casefold(), k))
    lines = [_line(entries[k]) for k in keys]
    return "## References\n\n" + "".join(l + "\n" for l in lines)


def update_references(md: str, entries: dict, citation_style: str) -> str:
    block = render_references(entries, cited_keys(md), citation_style)
    pre, secs = split_sections(md)
    secs = [s for s in secs if s.name != "References"]
    ref = Section("## References", "References", block[len("## References"):])
    pos = next((i for i, s in enumerate(secs) if s.name == "Appendix"), len(secs))
    secs.insert(pos, ref)
    secs = [Section(s.heading, s.name, s.text.rstrip("\n") + ("\n" if i == len(secs) - 1 else "\n\n"))
            for i, s in enumerate(secs)]
    if pre and not pre.endswith("\n\n"):
        pre = pre.rstrip("\n") + "\n\n"
    return assemble(pre, secs)
