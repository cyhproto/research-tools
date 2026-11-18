"""Paper lookups (OpenAlex, Semantic Scholar, Crossref). The only module that uses the network."""
from __future__ import annotations

import json
import os
import re
import socket
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from .bibimport import normalize_doi

MATCH_THRESHOLD = 70
_BACKOFF = (2, 4)


@dataclass
class PaperRecord:
    title: str
    authors: list[str]
    year: int | None
    publication_date: str | None
    venue: str | None
    journal: str | None
    volume: str | None
    pages: str | None
    doi: str | None
    abstract: str | None
    citation_count: int
    ids: dict[str, str]
    source: str


@dataclass
class LookupOutcome:
    records: list[PaperRecord] = field(default_factory=list)
    failed: bool = False


def normalize_title(t: str) -> str:
    folded = unicodedata.normalize("NFKC", t or "").casefold()
    return "".join(c for c in folded if c.isalnum()) or folded.strip()


def title_score(query: str, candidate: str, query_year: int | None, cand_year: int | None) -> float:
    score = SequenceMatcher(None, query.lower(), candidate.lower()).ratio() * 100
    if query_year is not None and cand_year is not None and query_year == cand_year:
        score += 10
    return score


def within_cutoff(publication_date: str | None, year: int | None, cutoff: str) -> bool:
    cut = cutoff[:7]
    m = re.match(r"(\d{4})-(\d{2})", publication_date or "")
    if m:
        return f"{m.group(1)}-{m.group(2)}" <= cut
    if year is None:
        m = re.match(r"(\d{4})", publication_date or "")
        year = int(m.group(1)) if m else None
    if year is None:
        return True
    return year <= int(cut[:4])


def sanitize_filter_value(title: str) -> str:
    s = unicodedata.normalize("NFKC", title or "")
    s = "".join(c if (c.isalnum() or c in " -") else " " for c in s)
    return re.sub(r" +", " ", s).strip()


def reconstruct_abstract(inv: dict[str, list[int]] | None) -> str | None:
    if not inv:
        return None
    slots: dict[int, str] = {}
    for word, positions in inv.items():
        for p in positions:
            slots[p] = word
    return " ".join(slots[i] for i in sorted(slots)) or None


def truncate_abstract(text: str | None, limit: int = 1500) -> str | None:
    if text is None or len(text) <= limit:
        return text
    return text[:limit] + "... [Truncated]"


def best_match(title: str, year: int | None, records: list[PaperRecord],
               cutoff: str | None) -> PaperRecord | None:
    best, best_score = None, float("-inf")
    for r in records:
        if cutoff and not within_cutoff(r.publication_date, r.year, cutoff):
            continue
        s = title_score(title, r.title, year, r.year)
        if s > best_score:
            best, best_score = r, s
    return best if best is not None and best_score > MATCH_THRESHOLD else None


def _default_fetch_json(url: str, params: dict, headers: dict) -> Any:
    full = url + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(full, headers={"User-Agent": "paper-orchestra/0.1", **headers})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _str(v: Any) -> str | None:
    return v if isinstance(v, str) and v else None


def _int(v: Any) -> int | None:
    return v if isinstance(v, int) and not isinstance(v, bool) else None


def _strip_jats(text: str | None) -> str | None:
    if not text:
        return None
    s = re.sub(r"<[^>]+>", " ", text)
    s = re.sub(r"\s+", " ", s).strip()
    return s or None


class Lookup:
    def __init__(self, fetch_json=None, sleep=time.sleep, clock=time.monotonic,
                 openalex_key=os.environ.get("OPENALEX_API_KEY"),
                 s2_key=os.environ.get("SEMANTIC_SCHOLAR_API_KEY"),
                 cache_path: Path | None = None, min_interval: float = 1.0, retries: int = 2):
        self.fetch_json = fetch_json or _default_fetch_json
        self.sleep = sleep
        self.clock = clock
        self.openalex_key = openalex_key
        self.s2_key = s2_key
        self.cache_path = Path(cache_path) if cache_path else None
        self.min_interval = min_interval
        self.retries = retries
        self._last: dict[str, float] = {}
        self._cache: dict[str, list[dict]] | None = None

    # -- cache -------------------------------------------------------------
    def _load_cache(self) -> dict[str, list[dict]]:
        if self._cache is None:
            self._cache = {}
            if self.cache_path and self.cache_path.exists():
                try:
                    data = json.loads(self.cache_path.read_text(encoding="utf-8"))
                    if isinstance(data, dict):
                        self._cache = data
                except (OSError, ValueError):
                    pass
        return self._cache

    def _cache_get(self, key: str) -> list[PaperRecord] | None:
        if not self.cache_path:
            return None
        raw = self._load_cache().get(key)
        if raw is None:
            return None
        try:
            return [PaperRecord(**r) for r in raw]
        except TypeError:
            return None

    def _cache_put(self, key: str, records: list[PaperRecord]) -> None:
        if not self.cache_path:
            return
        cache = self._load_cache()
        cache[key] = [asdict(r) for r in records]
        tmp = self.cache_path.with_name(self.cache_path.name + ".tmp")
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, self.cache_path)
        except OSError:
            try:
                tmp.unlink()
            except OSError:
                pass

    # -- requests ----------------------------------------------------------
    def _wait(self, service: str) -> None:
        last = self._last.get(service)
        if last is not None:
            gap = self.min_interval - (self.clock() - last)
            if gap > 0:
                self.sleep(gap)
        self._last[service] = self.clock()

    def _request(self, service: str, url: str, params: dict, headers: dict) -> tuple[Any, bool]:
        """Return (json, ok). Retries 429/5xx/network errors with 2s then 4s backoff."""
        for attempt in range(self.retries + 1):
            self._wait(service)
            try:
                return self.fetch_json(url, params, headers), True
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    return None, True
                if not (e.code == 429 or e.code >= 500):
                    return None, False
            except (urllib.error.URLError, socket.timeout, TimeoutError, OSError, ValueError):
                pass
            if attempt < self.retries:
                self.sleep(_BACKOFF[min(attempt, len(_BACKOFF) - 1)])
        return None, False

    def _lookup(self, service: str, spacing: str, key: str, url: str, params: dict,
                headers: dict, parse) -> LookupOutcome:
        ckey = f"{service}:{key}"
        cached = self._cache_get(ckey)
        if cached is not None:
            return LookupOutcome(cached, False)
        data, ok = self._request(spacing, url, params, headers)
        if not ok:
            return LookupOutcome([], True)
        try:
            records = parse(data) if data is not None else []
        except (AttributeError, TypeError, KeyError, IndexError):
            return LookupOutcome([], True)
        self._cache_put(ckey, records)
        return LookupOutcome(records, False)

    # -- OpenAlex ----------------------------------------------------------
    _OA_SELECT = ("id,doi,display_name,publication_year,publication_date,authorships,"
                  "primary_location,abstract_inverted_index,cited_by_count,biblio")

    def _openalex(self, service: str, key: str, flt: str) -> LookupOutcome:
        params = {"filter": flt, "per_page": 5, "select": self._OA_SELECT}
        if self.openalex_key:
            params["api_key"] = self.openalex_key
        return self._lookup(service, "openalex", key, "https://api.openalex.org/works",
                            params, {}, self._parse_openalex)

    def openalex_title(self, title: str) -> LookupOutcome:
        return self._openalex("openalex", normalize_title(title),
                              "title.search:" + sanitize_filter_value(title))

    def openalex_doi(self, doi: str) -> LookupOutcome:
        d = normalize_doi(doi) or doi
        if "," in d or "|" in d:  # OpenAlex reads these as filter separators
            return LookupOutcome([], False)
        return self._openalex("openalex-doi", d, "doi:" + d)

    @staticmethod
    def _parse_openalex(data: dict) -> list[PaperRecord]:
        out = []
        for w in data.get("results") or []:
            title = _str(w.get("display_name"))
            if not title:
                continue
            authors = [a["author"]["display_name"] for a in w.get("authorships") or []
                       if isinstance(a.get("author"), dict) and _str(a["author"].get("display_name"))]
            src = ((w.get("primary_location") or {}).get("source")) or {}
            venue = _str(src.get("display_name"))
            bib = w.get("biblio") or {}
            fp, lp = _str(bib.get("first_page")), _str(bib.get("last_page"))
            pages = f"{fp}-{lp}" if fp and lp and fp != lp else fp
            ids = {}
            if _str(w.get("id")):
                ids["openalex"] = w["id"]
            out.append(PaperRecord(
                title, authors, _int(w.get("publication_year")), _str(w.get("publication_date")),
                venue, venue if src.get("type") == "journal" else None, _str(bib.get("volume")),
                pages, normalize_doi(w.get("doi")),
                reconstruct_abstract(w.get("abstract_inverted_index")),
                _int(w.get("cited_by_count")) or 0, ids, "openalex"))
        return out

    # -- Semantic Scholar --------------------------------------------------
    def s2_title(self, title: str) -> LookupOutcome:
        if not self.s2_key:
            return LookupOutcome([], False)
        params = {"query": title, "fields": "title,authors,venue,year,abstract,citationCount,"
                                            "journal,publicationDate,externalIds"}
        return self._lookup("s2", "s2", normalize_title(title),
                            "https://api.semanticscholar.org/graph/v1/paper/search/match",
                            params, {"x-api-key": self.s2_key}, self._parse_s2)

    @staticmethod
    def _parse_s2(data: dict) -> list[PaperRecord]:
        out = []
        for p in (data.get("data") or [])[:1]:
            title = _str(p.get("title"))
            if not title:
                continue
            ext = p.get("externalIds") or {}
            ids = {"s2": p["paperId"]} if _str(p.get("paperId")) else {}
            if _str(ext.get("ArXiv")):
                ids["arxiv"] = ext["ArXiv"]
            j = p.get("journal") or {}
            out.append(PaperRecord(
                title, [a["name"] for a in p.get("authors") or [] if _str(a.get("name"))],
                _int(p.get("year")), _str(p.get("publicationDate")), _str(p.get("venue")),
                _str(j.get("name")), _str(j.get("volume")), _str(j.get("pages")),
                normalize_doi(ext.get("DOI")), _str(p.get("abstract")),
                _int(p.get("citationCount")) or 0, ids, "semanticscholar"))
        return out

    # -- Crossref ----------------------------------------------------------
    def crossref_title(self, title: str) -> LookupOutcome:
        params = {"query.bibliographic": title, "rows": 3,
                  "select": "DOI,title,author,issued,container-title,abstract,volume,page"}
        return self._lookup("crossref", "crossref", normalize_title(title),
                            "https://api.crossref.org/works", params, {}, self._parse_crossref)

    @staticmethod
    def _parse_crossref(data: dict) -> list[PaperRecord]:
        out = []
        for it in (data.get("message") or {}).get("items") or []:
            titles = it.get("title") or []
            title = _str(titles[0]) if titles else None
            if not title:
                continue
            authors = [" ".join(x for x in (a.get("given"), a.get("family")) if x) or a.get("name", "")
                       for a in it.get("author") or []]
            raw = ((it.get("issued") or {}).get("date-parts") or [[]])[0] or []
            parts = []
            for x in raw:
                if not _int(x):
                    break
                parts.append(x)
            year = parts[0] if parts else None
            date = "-".join([f"{parts[0]:04d}"] + [f"{p:02d}" for p in parts[1:3]]) if year else None
            cont = it.get("container-title") or []
            venue = _str(cont[0]) if cont else None
            out.append(PaperRecord(
                title, [a for a in authors if a], year, date, venue, venue,
                _str(it.get("volume")), _str(it.get("page")), normalize_doi(it.get("DOI")),
                _strip_jats(it.get("abstract")), 0, {}, "crossref"))
        return out
