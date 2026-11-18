"""Citation keys in paper.md and the generated References section."""
import re
from collections.abc import Container

from .bibimport import CITATION_KEY
from .paper import Section, assemble, detect_eol, ensure_blank, fence_tags, split_sections

BRACKET_RE = re.compile(r"\[([^\[\]]*@[^\[\]]*)\]")
KEY_RE = re.compile(rf"(?<![\w@])@({CITATION_KEY})")  # not after a word: Recall@10, me@x.org
INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
# where a bare @word is not a citation: HTML comments, URLs and link targets
_NOT_BARE_RE = re.compile(r"<!--.*?(?:-->|\Z)|<https?://[^>\s]*>|https?://\S+|\]\([^)\n]*\)", re.S)
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


def _blank(text: str, pattern: re.Pattern) -> str:
    return pattern.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)


def citations(text: str) -> list[tuple[int, str, bool]]:
    """(position, key, bracketed) of each `@key` in a stretch of prose, in order of position.

    bracketed: inside a bracketed citation `[...@key...]`. The others are bare `@key`s, pandoc's
    narrative citations, outside inline code, HTML comments, URLs and link targets; they cite only
    when the key is a library key. Fenced code is the caller's business."""
    text = _blank(text, INLINE_CODE_RE)
    groups = list(BRACKET_RE.finditer(text))
    found = [(g.start(), k, True) for g in groups for k in KEY_RE.findall(g.group(1))]
    bare = _blank(text, _NOT_BARE_RE)
    for g in groups:
        bare = bare[:g.start()] + " " * len(g.group(0)) + bare[g.end():]
    found += [(m.start(), m.group(1), False) for m in KEY_RE.finditer(bare)]
    return sorted(found, key=lambda f: f[0])


def cited_keys(md: str, library: Container[str] | None = None) -> list[str]:
    """Keys cited in md, in order of first appearance: every key of a bracketed citation, and, when
    the library's keys are given, every bare `@key` that is one of them."""
    seen: dict[str, None] = {}
    for _, k, bracketed in citations(_prose(md)):
        if bracketed or (library is not None and k in library):
            seen.setdefault(k)
    return list(seen)


def bare_unknown_keys(md: str, library: Container[str]) -> list[str]:
    """Bare `@key`s that are not library keys (and not cited in brackets either): not citations."""
    found = citations(_prose(md))
    bracketed = {k for _, k, b in found if b}
    return list(dict.fromkeys(k for _, k, b in found if not b and k not in library and k not in bracketed))


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
    block = render_references(entries, cited_keys(md, entries), citation_style)
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
