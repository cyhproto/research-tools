"""Citation keys in paper.md and the generated References section."""
import re

from .paper import Section, assemble, detect_eol, ensure_blank, fence_tags, split_sections

BRACKET_RE = re.compile(r"\[([^\[\]]*@[^\[\]]*)\]")
KEY_RE = re.compile(r"(?<![\w@])@(\w(?:[\w:.\-]*\w)?)")
INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
DOI_PREFIX_RE = re.compile(r"^(https?://(dx\.)?doi\.org/|doi:\s*)", re.I)
ENTRY_RE = re.compile(r"^- \[@[^\[\]]+\]")  # a generated reference entry: "- [@key] Authors. (year). ..."
MAX_AUTHORS = 6


def _kept_groups(text: str) -> list[list[str]]:
    """Paragraphs of the lines in a References section's text that are neither blank nor entries."""
    groups: list[list[str]] = []
    cur: list[str] = []
    for line in text.splitlines():
        if not line.strip() or ENTRY_RE.match(line):
            if cur:
                groups.append(cur)
            cur = []
        else:
            cur.append(line)
    if cur:
        groups.append(cur)
    return groups


def kept_reference_lines(md: str) -> list[str]:
    """The user's text under ## References: every non-blank line that is not a reference entry."""
    _, secs = split_sections(md)
    return [l for s in secs if s.name == "References" for g in _kept_groups(s.text) for l in g]


def _without_entries(s: Section) -> Section:
    if s.name != "References":
        return s
    return Section(s.heading, s.name, "".join("" if ENTRY_RE.match(l) else l for l in s.text.splitlines(True)))


def _prose(md: str) -> str:
    """md without fenced blocks, inline code and the generated reference entries."""
    pre, secs = split_sections(md)
    text = assemble(pre, [_without_entries(s) for s in secs])
    lines = text.splitlines()
    return "\n".join(INLINE_CODE_RE.sub("", l) for l, t in zip(lines, fence_tags(lines)) if t is None)


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
    doi = DOI_PREFIX_RE.sub("", (e.doi or "").strip())
    if doi:
        parts.append(f"https://doi.org/{doi}")
    return " ".join(p for p in parts if p)


def render_references(entries: dict, cited: list[str], citation_style: str) -> str:
    keys = [k for k in cited if k in entries]
    if citation_style == "author-year":
        keys = sorted(keys, key=lambda k: (k.casefold(), k))
    lines = [_line(entries[k]) for k in keys]
    return "## References\n\n" + "".join(l + "\n" for l in lines)


def update_references(md: str, entries: dict, citation_style: str) -> str:
    eol = detect_eol(md)
    block = render_references(entries, cited_keys(md), citation_style)
    pre, secs = split_sections(md)
    kept = [g for s in secs if s.name == "References" for g in _kept_groups(s.text)]
    secs = [s for s in secs if s.name != "References"]
    body = block[len("## References"):]
    if kept:  # the user's text stays, after the regenerated list
        body = body.rstrip("\n") + "\n\n" + "\n\n".join("\n".join(g) for g in kept) + "\n"
    body = body.replace("\n", eol)
    pos = next((i for i, s in enumerate(secs) if s.name == "Appendix"), len(secs))
    ref = Section("## References", "References", body.rstrip("\r\n") + eol * (1 if pos == len(secs) else 2))
    if pos:
        secs[pos - 1] = Section(secs[pos - 1].heading, secs[pos - 1].name, ensure_blank(secs[pos - 1].text, eol))
    else:
        pre = ensure_blank(pre, eol)
    secs.insert(pos, ref)
    return assemble(pre, secs)
