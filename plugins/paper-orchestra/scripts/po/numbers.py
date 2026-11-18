"""Numbers in paper.md: extract the ones that need a source, and match them to the materials."""
import re
from dataclasses import dataclass

from .numtok import Num, find_numbers, is_trivial, values_match
from .paper import H2_RE, LINE_RE, fence_tags, section_name
from .references import ENTRY_RE
from .sourcetags import mask_tags

_HTML_COMMENT_RE = re.compile(r"<!--.*?(?:-->|\Z)", re.S)
_INLINE_CODE_RE = re.compile(r"(`+)(?!`).+?(?<!`)\1(?!`)", re.S)
_CITATION_RE = re.compile(r"\[@[^\]]*\]")
_LINK_TARGET_RE = re.compile(r"\]\([^)\n]*\)")
_TAG_RE = re.compile(r"\\tag\*?\{[^}]*\}")
_HEADING_NUM_RE = re.compile(r"^(#{1,6}[ \t]+)\d+(?:\.\d+)*\.?(?=\s|$)", re.M)
_LIST_MARKER_RE = re.compile(r"^([ \t]*)(?:[-*+]|\d+[.)])(?=\s)", re.M)
_XREF_RE = re.compile(
    r"\b(?:Figure|Fig\.|Table|Section|Sec\.|Eq\.|Equation|Appendix)[ \t]*\(?[ \t]*\d+(?:\.\d+)*\)?", re.I)
_SENTENCE_END_RE = re.compile(r"(?<=[.!?])\s+")
_CONTEXT_MAX = 200


@dataclass
class NumberHit:
    line_no: int
    num: Num
    context: str


def _blank(text: str, pattern: re.Pattern) -> str:
    return pattern.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)


def _masked(md: str) -> str:
    lines = LINE_RE.findall(md)
    in_refs = False
    kept = []
    for line, tag in zip(lines, fence_tags(lines)):
        blank = re.sub(r"[^\r\n]", " ", line)
        if tag is not None:
            kept.append(blank)
            continue
        h = H2_RE.match(line.rstrip("\r\n"))
        if h:
            in_refs = section_name(h.group(1)) == "References"
        kept.append(blank if in_refs and (h or ENTRY_RE.match(line)) else line)  # entries only
    text = "".join(kept)
    for pat in (_HTML_COMMENT_RE, _INLINE_CODE_RE, _CITATION_RE, _LINK_TARGET_RE, _TAG_RE):
        text = _blank(text, pat)
    text = _HEADING_NUM_RE.sub(lambda m: m.group(1) + " " * (len(m.group(0)) - len(m.group(1))), text)
    text = _LIST_MARKER_RE.sub(lambda m: " " * len(m.group(0)), text)
    return _blank(text, _XREF_RE)


def _context(md: str, pos: int) -> str:
    start = md.rfind("\n", 0, pos) + 1
    end = md.find("\n", pos)
    line = md[start:end if end >= 0 else len(md)]
    rel = pos - start
    s = 0
    for m in _SENTENCE_END_RE.finditer(line):
        if m.end() <= rel:
            s = m.end()
        else:
            e = m.start()
            break
    else:
        e = len(line)
    sent = line[s:e].strip().rstrip("\r")
    if len(sent) > _CONTEXT_MAX:
        off = max(0, min(rel - s - _CONTEXT_MAX // 2, len(sent) - _CONTEXT_MAX))
        sent = sent[off:off + _CONTEXT_MAX]
    return sent


def extract_paper_numbers(md: str) -> list[NumberHit]:
    hits = []
    for n in find_numbers(_masked(md)):
        if is_trivial(n):
            continue
        hits.append(NumberHit(md.count("\n", 0, n.start) + 1, n, _context(md, n.start)))
    return hits


def materials_numbers(texts: list[str]) -> list[Num]:
    return [n for t in texts for n in find_numbers(mask_tags(t))]


def matches(num: Num, materials: list[Num]) -> bool:
    for m in materials:
        for v in (m.value, m.value * 100, m.value / 100):
            if num.value == v or values_match(num.value, num.decimals, v):
                return True
    return False


def unmatched(md: str, materials_texts: list[str], excluded_years: set[int]) -> list[NumberHit]:
    mats = materials_numbers(materials_texts)
    return [h for h in extract_paper_numbers(md)
            if not (h.num.decimals == 0 and not h.num.percent and h.num.value in excluded_years)
            and not matches(h.num, mats)]
