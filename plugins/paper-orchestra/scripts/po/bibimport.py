"""Import references from reference-manager exports (BibTeX, CSL JSON).

Citation keys are kept exactly as written in the user's file (case preserved).
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ImportedRef:
    key: str
    title: str
    authors: list[str]
    year: int | None
    doi: str | None
    venue: str | None
    abstract: str | None
    source_file: str


_ACCENTS = {'"': "\u0308", "'": "\u0301", "`": "\u0300", "^": "\u0302", "~": "\u0303"}
_ACCENT_RE = re.compile(r"""\\(["'`^~])\s*(?:\{\s*\\?([A-Za-z])\s*\}|\\?([A-Za-z]))""")
_STYLE_RE = re.compile(r"\\(?:emph|textit|textbf|textsc|textrm|mathrm)\s*\{([^{}]*)\}")


def clean_latex(s: str) -> str:
    def accent(m: re.Match) -> str:
        return unicodedata.normalize("NFC", (m.group(2) or m.group(3)) + _ACCENTS[m.group(1)])

    s = _ACCENT_RE.sub(accent, s)
    prev = None
    while prev != s:  # unwrap nested style commands
        prev, s = s, _STYLE_RE.sub(r"\1", s)
    s = re.sub(r"\\([&%_$#])", r"\1", s)
    s = s.replace("{", "").replace("}", "").replace("--", "\u2013")
    return re.sub(r"\s+", " ", s).strip()


def normalize_doi(doi: str | None) -> str | None:
    if not doi:
        return None
    d = doi.strip().lower()
    d = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", d)
    return d or None


def _year(v: str | None) -> int | None:
    m = re.search(r"\d{4}", v or "")
    return int(m.group()) if m else None


def _match(text: str, i: int) -> int:
    """Index just past the group opened at text[i] ('{' or '('), or -1 if unclosed."""
    open_c = text[i]
    if open_c == "(":
        j = text.find(")", i)
        return -1 if j < 0 else j + 1
    depth = 0
    for j in range(i, len(text)):
        c = text[j]
        if c == "\\":
            continue
        if c == "{" and text[j - 1] != "\\":
            depth += 1
        elif c == "}" and text[j - 1] != "\\":
            depth -= 1
            if depth == 0:
                return j + 1
    return -1


def _read_value(body: str, i: int, macros: dict[str, str]) -> tuple[str, int]:
    """Read a field value (pieces joined by '#') starting at body[i]."""
    parts: list[str] = []
    n = len(body)
    while True:
        while i < n and body[i].isspace():
            i += 1
        if i >= n:
            break
        c = body[i]
        if c == "{":
            j = _match(body, i)
            if j < 0:
                raise ValueError("unbalanced braces in value")
            parts.append(body[i + 1:j - 1])
            i = j
        elif c == '"':
            depth, j = 0, i + 1
            while j < n and not (body[j] == '"' and depth == 0):
                if body[j] == "{":
                    depth += 1
                elif body[j] == "}":
                    depth -= 1
                j += 1
            if j >= n:
                raise ValueError("unterminated quoted value")
            parts.append(body[i + 1:j])
            i = j + 1
        else:
            m = re.match(r"[^\s,#{}\"]+", body[i:])
            if not m:
                raise ValueError("bad value")
            tok = m.group()
            parts.append(macros.get(tok.lower(), tok))
            i += len(tok)
        while i < n and body[i].isspace():
            i += 1
        if i < n and body[i] == "#":
            i += 1
            continue
        break
    return "".join(parts), i


def _parse_fields(body: str, macros: dict[str, str]) -> dict[str, str]:
    fields: dict[str, str] = {}
    i, n = 0, len(body)
    while i < n:
        while i < n and (body[i].isspace() or body[i] == ","):
            i += 1
        if i >= n:
            break
        m = re.match(r"[A-Za-z0-9_\-:.]+", body[i:])
        if not m:
            raise ValueError(f"unexpected text {body[i:i + 15]!r}")
        name = m.group().lower()
        i += len(name)
        while i < n and body[i].isspace():
            i += 1
        if i >= n or body[i] != "=":
            raise ValueError(f"field {name!r} has no '='")
        value, i = _read_value(body, i + 1, macros)
        fields[name] = value
    return fields


def _split_authors(raw: str) -> list[str]:
    names, depth, cur, i = [], 0, "", 0
    while i < len(raw):
        c = raw[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        if depth == 0 and re.match(r"\s+and\s+", raw[i:], re.I) and cur.strip():
            names.append(cur)
            i += re.match(r"\s+and\s+", raw[i:], re.I).end()
            cur = ""
            continue
        cur += c
        i += 1
    if cur.strip():
        names.append(cur)
    out = []
    for nm in names:
        nm = nm.strip()
        if nm.startswith("{") and nm.endswith("}") and _match(nm, 0) == len(nm):
            out.append(clean_latex(nm))  # corporate author
            continue
        # split on top-level commas
        segs, d, cur = [], 0, ""
        for c in nm:
            d += (c == "{") - (c == "}")
            if c == "," and d == 0:
                segs.append(cur)
                cur = ""
            else:
                cur += c
        segs.append(cur)
        segs = [x.strip() for x in segs]
        if len(segs) >= 2:
            last, first = segs[0], segs[-1]
            if len(segs) == 3 and segs[1]:
                last = f"{last} {segs[1]}"
            out.append(clean_latex(f"{first} {last}"))
        else:
            out.append(clean_latex(nm))
    return [a for a in out if a]


def parse_bibtex(text: str, source_file: str = "") -> tuple[list[ImportedRef], list[str]]:
    refs: list[ImportedRef] = []
    warns: list[str] = []
    macros: dict[str, str] = {}
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == "%":
            j = text.find("\n", i)
            i = n if j < 0 else j + 1
            continue
        if c != "@":
            i += 1
            continue
        m = re.compile(r"@\s*([A-Za-z]+)\s*([{(])").match(text, i)
        if not m:
            i += 1
            continue
        etype = m.group(1).lower()
        open_at = m.end() - 1
        end = _match(text, open_at)
        head = re.match(r"\s*([^,\s{}=]*)", text[open_at + 1:open_at + 200])
        key = head.group(1) if head else ""
        if end < 0:
            warns.append(f"{source_file}: entry '{key}' is malformed (unclosed); skipped")
            nxt = text.find("\n@", open_at)
            i = n if nxt < 0 else nxt + 1
            continue
        body = text[open_at + 1:end - 1]
        i = end
        if etype in ("comment", "preamble"):
            continue
        try:
            if etype == "string":
                macros.update(_parse_fields(body, macros))
                continue
            comma = body.find(",")
            if comma < 0:
                raise ValueError("no fields")
            key = body[:comma].strip()
            if not key:
                raise ValueError("missing citation key")
            f = _parse_fields(body[comma + 1:], macros)
        except ValueError as e:
            warns.append(f"{source_file}: entry '{key}' is malformed ({e}); skipped")
            continue
        venue = f.get("journal") or f.get("booktitle")
        refs.append(ImportedRef(
            key=key,
            title=clean_latex(f.get("title", "")),
            authors=_split_authors(f["author"]) if f.get("author") else [],
            year=_year(f.get("year") or f.get("date")),
            doi=normalize_doi(clean_latex(f["doi"])) if f.get("doi") else None,
            venue=clean_latex(venue) if venue else None,
            abstract=clean_latex(f["abstract"]) if f.get("abstract") else None,
            source_file=source_file,
        ))
    return refs, warns


def _first(v) -> str | None:
    if isinstance(v, list):
        v = v[0] if v else None
    return str(v) if v else None


def parse_csl_json(text: str, source_file: str = "") -> tuple[list[ImportedRef], list[str]]:
    warns: list[str] = []
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        return [], [f"{source_file}: invalid JSON ({e})"]
    if isinstance(data, dict):
        data = data.get("items", [data])
    if not isinstance(data, list):
        return [], [f"{source_file}: CSL JSON must be a list of items"]
    refs: list[ImportedRef] = []
    for idx, it in enumerate(data):
        if not isinstance(it, dict):
            warns.append(f"{source_file}: item {idx} is not an object; skipped")
            continue
        key = str(it.get("id") or it.get("citation-key") or "")
        if not key:
            warns.append(f"{source_file}: item {idx} has no id or citation-key")
        authors = []
        for a in it.get("author") or []:
            if not isinstance(a, dict):
                continue
            name = " ".join(x for x in (a.get("given"), a.get("family")) if x) or a.get("literal", "")
            if name.strip():
                authors.append(name.strip())
        year = None
        try:
            year = int(it["issued"]["date-parts"][0][0])
        except (KeyError, IndexError, TypeError, ValueError):
            pass
        refs.append(ImportedRef(
            key=key,
            title=re.sub(r"\s+", " ", str(it.get("title") or "")).strip(),
            authors=authors,
            year=year,
            doi=normalize_doi(it.get("DOI")),
            venue=_first(it.get("container-title")),
            abstract=it.get("abstract") or None,
            source_file=source_file,
        ))
    return refs, warns


def load_imports(paper_dir: Path) -> dict:
    ref_dir = Path(paper_dir) / "materials" / "references"
    out: dict = {"library": [], "must_cite": [], "warnings": []}
    for slot in ("library", "must_cite"):
        for ext, parser in (("bib", parse_bibtex), ("json", parse_csl_json)):
            p = ref_dir / f"{slot}.{ext}"
            if p.is_file():
                refs, warns = parser(p.read_text(encoding="utf-8"), p.name)
                out[slot].extend(refs)
                out["warnings"].extend(warns)
    return out
