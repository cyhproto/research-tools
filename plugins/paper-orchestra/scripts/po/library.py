"""Verified reference library: candidate checking, citation keys, BibTeX and counts."""
import dataclasses
import json
import os
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from .bibimport import ImportedRef, load_imports, normalize_doi
from .cli import common_parent, emit
from .scholar import Lookup, PaperRecord, best_match, normalize_title, truncate_abstract
from .state import task_done

STOPWORDS = {"the", "a", "an", "in", "on", "at", "for", "to", "of", "and", "is", "are", "with", "by", "study"}


_SOURCE_LABELS = {"openalex": "openalex", "semanticscholar": "s2", "s2": "s2", "crossref": "crossref"}


def _label(source: str | None) -> str:
    return _SOURCE_LABELS.get(source or "", source or "")


@dataclass
class LibraryEntry:
    key: str
    title: str
    authors: list[str]
    venue: str | None
    year: int | None
    abstract: str | None
    abstract_source: str | None
    verified_by: str
    must_cite: bool
    found_in_section: str
    reason: str
    doi: str | None = None
    ids: dict[str, str] = field(default_factory=dict)
    journal: str | None = None
    volume: str | None = None
    pages: str | None = None
    publication_date: str | None = None
    citation_count: int = 0

    @property
    def title_only(self) -> bool:
        return self.abstract is None


@dataclass
class Candidate:
    task_id: str
    section: str
    search_type: str
    title: str
    year: int | None
    reason: str


@dataclass
class VerifyResult:
    entries: list[LibraryEntry]
    dropped: list[dict]
    counts: dict
    resolved: dict = field(default_factory=dict)  # normalized candidate title -> entry key


# -- keys ---------------------------------------------------------------------

def _ascii(s: str) -> str:
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode("ascii")


def make_key(authors: list[str], year: int | None, title: str) -> str:
    author = "Unknown"
    if authors:
        tokens = _ascii(authors[0]).split()
        last = re.sub(r"[^A-Za-z]", "", tokens[-1]) if tokens else ""
        if last:
            author = last.capitalize()
    words = [w for w in re.findall(r"[A-Za-z0-9]+", _ascii(title)) if w.lower() not in STOPWORDS][:2]
    return f"{author}{year if year is not None else 'nd'}{''.join(w.capitalize() for w in words) or 'Paper'}"


def _suffix(n: int) -> str:
    """0 -> a, 25 -> z, 26 -> aa, ..."""
    out = ""
    n += 1
    while n:
        n, r = divmod(n - 1, 26)
        out = chr(97 + r) + out
    return out


def assign_unique_keys(entries: list[LibraryEntry]) -> None:
    """Make keys unique in place. Must-cite keys are never renamed."""
    used = {e.key for e in entries if e.must_cite}
    for e in entries:
        if e.must_cite:
            continue
        key, n = e.key, 0
        while key in used:
            key = e.key + _suffix(n)
            n += 1
        e.key = key
        used.add(key)


# -- candidates ----------------------------------------------------------------

def _parse_candidate_file(data) -> tuple[str, str, str, list[Candidate]]:
    if not isinstance(data, dict):
        raise ValueError("not an object")
    tid, section, stype = data.get("task_id"), data.get("section"), data.get("search_type")
    if not (isinstance(tid, str) and tid.strip() and isinstance(section, str) and isinstance(stype, str)):
        raise ValueError("task_id, section and search_type must be strings")
    items = data.get("candidates")
    if not isinstance(items, list):
        raise ValueError("candidates must be a list")
    out = []
    for it in items:
        if not isinstance(it, dict) or not isinstance(it.get("title"), str) or not it["title"].strip():
            raise ValueError("every candidate needs a title")
        year = it.get("year")
        if isinstance(year, str) and year.strip().isdigit():
            year = int(year)
        if year is not None and (isinstance(year, bool) or not isinstance(year, int)):
            raise ValueError("year must be an integer or null")
        reason = it.get("reason", "")
        if not isinstance(reason, str):
            raise ValueError("reason must be a string")
        out.append(Candidate(tid, section, stype, it["title"].strip(), year, reason))
    return tid, section, stype, out


def _scan_candidates(paper_dir) -> tuple[list[tuple[str, str, str, list[Candidate]]], list[str]]:
    d = Path(paper_dir) / "references" / "candidates"
    files, invalid = [], []
    for p in sorted(d.glob("*.json")) if d.is_dir() else []:
        try:
            files.append(_parse_candidate_file(json.loads(p.read_text(encoding="utf-8"))))
        except (ValueError, OSError):
            invalid.append(p.name)
    return files, invalid


def load_candidates(paper_dir: Path) -> tuple[list[Candidate], list[str]]:
    files, invalid = _scan_candidates(paper_dir)
    return [c for f in files for c in f[3]], invalid


# -- counts ----------------------------------------------------------------------

def counts(entries: list[LibraryEntry], dropped: list[dict]) -> dict:
    by_reason: dict[str, int] = {}
    for d in dropped:
        by_reason[d["reason"]] = by_reason.get(d["reason"], 0) + 1
    return {"with_abstract": sum(1 for e in entries if not e.title_only),
            "title_only": sum(1 for e in entries if e.title_only),
            "must_cite": sum(1 for e in entries if e.must_cite),
            "dropped": len(dropped), "dropped_by_reason": by_reason}


# -- verification --------------------------------------------------------------------

def _entry_from_record(rec: PaperRecord, cand: Candidate, imp: ImportedRef | None,
                       abstract: str | None, abstract_source: str | None, verified_by: str) -> LibraryEntry:
    return LibraryEntry(
        key=make_key(rec.authors or (imp.authors if imp else []), rec.year, rec.title),
        title=rec.title, authors=list(rec.authors or (imp.authors if imp else [])),
        venue=rec.venue, year=rec.year, abstract=truncate_abstract(abstract),
        abstract_source=abstract_source if abstract else None, verified_by=verified_by,
        must_cite=False, found_in_section=cand.section, reason=cand.reason,
        doi=normalize_doi(rec.doi), ids=dict(rec.ids or {}), journal=rec.journal, volume=rec.volume,
        pages=rec.pages, publication_date=rec.publication_date, citation_count=rec.citation_count or 0)


def _find_import(title: str, year: int | None, imports: list[ImportedRef]) -> ImportedRef | None:
    rec_like = [PaperRecord(i.title, i.authors, i.year, None, i.venue, None, None, None, i.doi,
                            i.abstract, 0, {}, "import") for i in imports]
    m = best_match(title, year, rec_like, None)
    return imports[rec_like.index(m)] if m is not None else None


def _verify_one(cand: Candidate, imports: list[ImportedRef], lookup, cutoff: str) -> tuple[LibraryEntry | None, str | None]:
    imp = _find_import(cand.title, cand.year, imports)
    imp_doi = normalize_doi(imp.doi) if imp else None
    outcomes: dict[str, list[PaperRecord]] = {}
    failed = outside = False
    match: PaperRecord | None = None

    def consider(service: str, out) -> bool:
        nonlocal failed, outside, match
        failed = failed or out.failed
        outcomes.setdefault(service, [])
        outcomes[service].extend(out.records)
        match = best_match(cand.title, cand.year, out.records, cutoff)
        if match is None and best_match(cand.title, cand.year, out.records, None) is not None:
            outside = True
        return match is not None

    found = False
    if imp_doi:
        found = consider("openalex", lookup.openalex_doi(imp_doi))
    if not found:
        found = consider("openalex", lookup.openalex_title(cand.title))
    if not found:
        found = consider("s2", lookup.s2_title(cand.title))
    if not found:
        found = consider("crossref", lookup.crossref_title(cand.title))

    if found:
        rec = match
        if imp is None:
            rdoi = normalize_doi(rec.doi)
            imp = next((i for i in imports if rdoi and normalize_doi(i.doi) == rdoi), None)
        if imp is not None and imp.abstract:
            abstract, source = imp.abstract, "import"
        elif rec.abstract:
            abstract, source = rec.abstract, _label(rec.source)
        else:
            abstract, source = None, None
            for service in ("openalex", "s2"):
                if service not in outcomes:
                    outcomes[service] = lookup.s2_title(cand.title).records if service == "s2" else []
                alt = best_match(rec.title, rec.year, outcomes[service], cutoff)
                if alt is not None and alt.abstract:
                    abstract, source = alt.abstract, service
                    break
        return _entry_from_record(rec, cand, imp, abstract, source, _label(rec.source)), None
    if outside:
        return None, "after-cutoff"
    if imp is not None:
        rec = PaperRecord(imp.title, imp.authors, imp.year, None, imp.venue, None, None, None,
                          imp.doi, imp.abstract, 0, {}, "import")
        return _entry_from_record(rec, cand, imp, imp.abstract, "import", "user-library"), None
    return None, "lookup-failed" if failed else "not-found"


def _remap(resolved: dict, mapping: dict) -> None:
    for k, v in list(resolved.items()):
        resolved[k] = mapping.get(v, v)


def verify_candidates(candidates: list[Candidate], imports: list[ImportedRef], lookup: Lookup,
                      cutoff: str, previous: VerifyResult | None = None) -> VerifyResult:
    entries = list(previous.entries) if previous else []
    resolved: dict[str, str] = dict(previous.resolved) if previous else {}
    seen_titles = {normalize_title(e.title) for e in entries}
    dropped: list[dict] = []
    if previous:
        current = {normalize_title(c.title) for c in candidates}
        for d in previous.dropped:
            nt = normalize_title(d["title"])
            if not (d["reason"] == "lookup-failed" and nt in current):  # those are retried below
                dropped.append(d)
                seen_titles.add(nt)
    seen_candidates: set[str] = set()
    for cand in candidates:
        nt = normalize_title(cand.title)
        if nt in seen_candidates:
            continue
        seen_candidates.add(nt)
        if nt in seen_titles or nt in resolved:
            continue
        entry, reason = _verify_one(cand, imports, lookup, cutoff)
        if entry is not None:
            mt = normalize_title(entry.title)
            existing = next((e for e in entries if normalize_title(e.title) == mt), None)
            if existing is not None:
                resolved[nt] = existing.key
                continue
            entries.append(entry)
            resolved[nt] = entry.key
        else:
            dropped.append({"title": cand.title, "task_id": cand.task_id, "reason": reason})
    old = {id(e): e.key for e in entries}
    assign_unique_keys(entries)
    _remap(resolved, {old[id(e)]: e.key for e in entries if id(e) in old})
    return VerifyResult(entries, dropped, counts(entries, dropped), resolved)


def add_must_cite(refs: list[ImportedRef], lookup: Lookup) -> list[LibraryEntry]:
    out = []
    for ref in refs:
        rec = None
        doi = normalize_doi(ref.doi)
        if doi:
            recs = lookup.openalex_doi(doi).records
            rec = recs[0] if recs else None
        if rec is None:
            for fn in (lookup.openalex_title, lookup.s2_title, lookup.crossref_title):
                rec = best_match(ref.title, ref.year, fn(ref.title).records, None)
                if rec is not None:
                    break
        if ref.abstract:
            abstract, source = truncate_abstract(ref.abstract), "import"
        elif rec is not None and rec.abstract:
            abstract, source = truncate_abstract(rec.abstract), _label(rec.source)
        else:
            abstract = source = None
        authors = (rec.authors if rec is not None and rec.authors else ref.authors)
        out.append(LibraryEntry(
            key=ref.key, title=rec.title if rec is not None else ref.title, authors=list(authors),
            venue=(rec.venue if rec is not None and rec.venue else ref.venue),
            year=rec.year if rec is not None and rec.year is not None else ref.year,
            abstract=abstract, abstract_source=source,
            verified_by=_label(rec.source) if rec is not None else "user-vouched",
            must_cite=True, found_in_section="must-cite", reason="user must-cite",
            doi=normalize_doi(rec.doi if rec is not None and rec.doi else ref.doi),
            ids=dict(rec.ids) if rec is not None else {},
            journal=rec.journal if rec is not None else None,
            volume=rec.volume if rec is not None else None,
            pages=rec.pages if rec is not None else None,
            publication_date=rec.publication_date if rec is not None else None,
            citation_count=(rec.citation_count or 0) if rec is not None else 0))
    return out


def merge_must_cite(result: VerifyResult, must: list[LibraryEntry]) -> VerifyResult:
    """Keep one entry per paper; the must-cite one wins (and keeps its key)."""
    titles = {normalize_title(e.title) for e in must}
    dois = {d for d in (normalize_doi(e.doi) for e in must) if d}
    kept, mapping = [], {}
    for e in result.entries:
        if e.must_cite:
            continue
        twin = next((m for m in must if normalize_title(m.title) == normalize_title(e.title)
                     or (normalize_doi(e.doi) and normalize_doi(m.doi) == normalize_doi(e.doi))), None)
        if twin is not None:
            mapping[e.key] = twin.key
        else:
            kept.append(e)
    entries = kept + list(must)
    old = {id(e): e.key for e in entries}
    assign_unique_keys(entries)
    for e in entries:
        mapping.setdefault(old[id(e)], e.key)
    resolved = dict(result.resolved)
    _remap(resolved, mapping)
    return VerifyResult(entries, result.dropped, counts(entries, result.dropped), resolved)


def dedupe_must_cite_keys(entries: list[LibraryEntry]) -> tuple[list[LibraryEntry], list[str]]:
    """Keep the first must-cite entry per import key; later ones are dropped with a warning."""
    seen: dict[str, str] = {}
    out, warns = [], []
    for e in entries:
        if e.key in seen:
            warns.append(f"must-cite key {e.key!r} is used twice; kept {seen[e.key]!r}, dropped {e.title!r}")
            continue
        seen[e.key] = e.title
        out.append(e)
    return out, warns


# -- BibTeX -------------------------------------------------------------------------

def _bib(v) -> str:
    return re.sub(r"[{}]", "", str(v)).strip()


_TEX = {"\\": "\\textbackslash{}", "&": "\\&", "%": "\\%", "$": "\\$", "#": "\\#", "_": "\\_",
        "{": "\\{", "}": "\\}", "~": "\\textasciitilde{}", "^": "\\textasciicircum{}"}


def _tex(v) -> str:
    return "".join(_TEX.get(c, c) for c in str(v)).strip()


def write_bibtex(entries: list[LibraryEntry]) -> str:
    blocks = []
    for e in entries:
        if e.journal:
            kind, container = "article", ("journal", e.journal)
        else:
            kind, container = "inproceedings", ("booktitle", e.venue or "arXiv")
        fields = [("title", "{" + _tex(e.title) + "}" if e.title else None),
                  ("author", " and ".join(_tex(a) for a in e.authors)), ("year", e.year),
                  (container[0], _tex(container[1])), ("volume", e.volume), ("pages", e.pages), ("doi", e.doi)]
        body = ",\n".join(f"  {k}={{{v if k in ('title', 'author', 'journal', 'booktitle') else _bib(v)}}}"
                          for k, v in fields if v not in (None, ""))
        blocks.append(f"@{kind}{{{e.key},\n{body}\n}}")
    return "\n\n".join(blocks) + ("\n" if blocks else "")


# -- persistence ----------------------------------------------------------------------

def _write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def save_library(paper_dir, result: VerifyResult, task_files=None) -> None:
    """task_files: the valid candidate files snapshotted when the candidates were loaded."""
    ref = Path(paper_dir) / "references"
    files = task_files if task_files is not None else _scan_candidates(paper_dir)[0]
    tasks = {tid: {"section": section, "search_type": stype, "candidates": len(cands)}
             for tid, section, stype, cands in files}
    _write_atomic(ref / "library.json",
                  json.dumps([dataclasses.asdict(e) for e in result.entries], ensure_ascii=False, indent=2) + "\n")
    _write_atomic(ref / "references.bib", write_bibtex(result.entries))
    _write_atomic(ref / "search_log.json",
                  json.dumps({"dropped": result.dropped, "resolved": result.resolved, "tasks": tasks}, ensure_ascii=False, indent=2) + "\n")
    for tid in tasks:
        task_done(paper_dir, f"lit:{tid}")


class LibraryError(ValueError):
    """references/library.json cannot be read (for example after a hand edit)."""


def load_library(paper_dir) -> list[LibraryEntry]:
    p = Path(paper_dir) / "references" / "library.json"
    if not p.is_file():
        return []
    names = {f.name for f in dataclasses.fields(LibraryEntry)}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return [LibraryEntry(**{k: v for k, v in e.items() if k in names}) for e in data]
    except (ValueError, TypeError, AttributeError) as e:
        raise LibraryError(f"{p} is not a valid library ({e}); fix the file by hand") from e


def _load_log(paper_dir) -> dict | None:
    p = Path(paper_dir) / "references" / "search_log.json"
    if not p.is_file():
        return None
    data = json.loads(p.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else None


# -- CLI ------------------------------------------------------------------------------

def _cmd_import_check(args) -> int:
    imp = load_imports(Path(args.paper))
    emit({"library": len(imp["library"]), "must_cite": len(imp["must_cite"]), "warnings": imp["warnings"]})
    return 0


def _cmd_verify(args) -> int:
    from .settings import SettingsError, load_settings
    paper = Path(args.paper)
    if not (paper / "references" / "candidates").is_dir():
        print(f"{paper / 'references' / 'candidates'} does not exist; run the literature search first",
              file=sys.stderr)
        return 2
    try:
        settings = load_settings(paper)
    except (SettingsError, OSError) as e:
        print(str(e), file=sys.stderr)
        return 2
    files, invalid = _scan_candidates(paper)
    cands = [c for f in files for c in f[3]]
    imports = load_imports(paper)
    previous = None
    log = _load_log(paper)
    prev_entries = load_library(paper)
    if prev_entries or log:
        previous = VerifyResult(entries=prev_entries, dropped=(log or {}).get("dropped", []), counts={},
                                resolved=(log or {}).get("resolved", {}))
    lookup = Lookup(cache_path=paper / "references" / "cache.json")
    result = verify_candidates(cands, imports["library"], lookup, settings.cutoff, previous)
    must, dup_warns = dedupe_must_cite_keys(add_must_cite(imports["must_cite"], lookup))
    result = merge_must_cite(result, must)
    save_library(paper, result, files)
    emit({**result.counts, "invalid_task_files": invalid, "warnings": imports["warnings"] + dup_warns})
    return 1 if invalid else 0


def _cmd_counts(args) -> int:
    paper = Path(args.paper)
    if not (paper / "references" / "library.json").is_file():
        print(f"{paper / 'references' / 'library.json'} does not exist; run refs verify first", file=sys.stderr)
        return 2
    emit(counts(load_library(paper), (_load_log(paper) or {}).get("dropped", [])))
    return 0


def register(sub) -> None:
    group = sub.add_parser("refs", help="verified reference library")
    cmds = group.add_subparsers(dest="refs_command")
    for name, fn, h in (("import-check", _cmd_import_check, "count user-supplied references and warnings"),
                        ("verify", _cmd_verify, "verify candidates and write the library"),
                        ("counts", _cmd_counts, "library counts")):
        cmds.add_parser(name, parents=[common_parent()], help=h).set_defaults(func=fn)
