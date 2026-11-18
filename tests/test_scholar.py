import json, urllib.error
from dataclasses import asdict
from po.scholar import *

FX = lambda n: json.load(open(f"tests/fixtures/api/{n}"))
def rec(title, year=2017, date=None): return PaperRecord(title, ["A B"], year, date, None, None, None, None, None, None, 0, {}, "openalex")

def test_title_score_and_best_match():
    assert title_score("Attention is all you need", "Attention Is All You Need", 2017, 2017) == 110.0
    assert best_match("Attention is all you need", 2017, [rec("Graph networks")], None) is None
    assert best_match("Attention is all you need", 2017, [rec("Attention Is All You Need")], "2024-11").title

def test_within_cutoff():
    assert within_cutoff("2024-11-30", 2024, "2024-11") and not within_cutoff("2024-12-01", 2024, "2024-11")
    assert within_cutoff(None, 2024, "2024-11") and not within_cutoff(None, 2025, "2024-11")
    assert within_cutoff(None, None, "2024-11")

def test_reconstruct_truncate():
    assert reconstruct_abstract({"Hello": [0], "world": [1, 3], "big": [2]}) == "Hello world big world"
    assert truncate_abstract("x" * 1600) == "x" * 1500 + "... [Truncated]"

def test_openalex_parse_no_notice():
    lk = Lookup(fetch_json=lambda u, p, h: FX("openalex_attention.json"), sleep=lambda s: None)
    [r, *_] = lk.openalex_title("Attention Is All You Need").records
    assert (r.year, r.doi, r.source) == (2017, "10.48550/arxiv.1706.03762", "openalex")
    assert r.abstract and r.authors[0] == "Ashish Vaswani"
    notice = FX("openalex_attention.json")["meta"]["notice"]
    assert notice[:40] not in json.dumps(asdict(r))

def test_sanitize_and_match_punctuated_title():
    s = sanitize_filter_value('BERT: Pre-training, of Deep|Bidirectional (Transformers)')
    assert not set(",|:()") & set(s)
    seen = {}
    lk = Lookup(fetch_json=lambda u, p, h: seen.update(p) or FX("openalex_bert.json"), sleep=lambda s: None)
    out = lk.openalex_title("BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding")
    assert "," not in seen["filter"].split("title.search:", 1)[1]
    assert best_match("BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding", 2019, out.records, None)

def test_rate_limited_lookup_not_cached(tmp_path):
    sleeps, cache = [], tmp_path / "cache.json"
    def boom(u, p, h): raise urllib.error.HTTPError(u, 429, "Too Many", {}, None)
    out = Lookup(fetch_json=boom, sleep=sleeps.append, cache_path=cache).openalex_title("X paper")
    assert out.failed and [s for s in sleeps if s >= 2] == [2, 4]
    assert not cache.exists() or "X paper".lower() not in cache.read_text().lower()
    calls = []
    lk = Lookup(fetch_json=lambda u, p, h: calls.append(1) or {"results": []}, sleep=lambda s: None, cache_path=cache)
    lk.openalex_title("X paper"); assert calls == [1]

def test_spacing_between_requests():
    t, sleeps = [0.0], []
    lk = Lookup(fetch_json=lambda u, p, h: {"results": []}, clock=lambda: t[0], sleep=sleeps.append)
    lk.openalex_title("a"); lk.openalex_title("b")
    assert sleeps and abs(sleeps[-1] - 1.0) < 1e-6

def test_s2_skipped_without_key():
    called = []
    out = Lookup(fetch_json=lambda *a: called.append(1), s2_key=None).s2_title("x")
    assert out == LookupOutcome([], False) and called == []

def test_crossref_strips_jats():
    lk = Lookup(fetch_json=lambda u, p, h: (_ for _ in ()).throw(AssertionError) if "mailto" in json.dumps(p) else FX("crossref_resnet.json"), sleep=lambda s: None)
    [r, *_] = lk.crossref_title("Deep Residual Learning for Image Recognition").records
    assert "<jats" not in (r.abstract or "")

# --- extra coverage (beyond the brief's tests) ---
def test_s2_parse_and_key_header():
    seen = {}
    lk = Lookup(fetch_json=lambda u, p, h: seen.update(h=h, p=p) or FX("s2_match.json"), s2_key="k", sleep=lambda s: None)
    [r] = lk.s2_title("Deep Residual Learning for Image Recognition").records
    assert seen["h"] == {"x-api-key": "k"} and "externalIds" in seen["p"]["fields"]
    assert (r.doi, r.year, r.source, r.ids["arxiv"]) == ("10.1109/cvpr.2016.90", 2015, "semanticscholar", "1512.03385")

def test_crossref_fields_and_openalex_key_param():
    [r, *_] = Lookup(fetch_json=lambda u, p, h: FX("crossref_resnet.json"), sleep=lambda s: None).crossref_title("x").records
    assert r.abstract.startswith("Deeper neural") and r.doi == "10.1109/cvpr.2016.90"
    assert (r.year, r.publication_date, r.pages, r.authors[0]) == (2016, "2016-06", "770-778", "Kaiming He")
    seen = {}
    Lookup(fetch_json=lambda u, p, h: seen.update(p) or {"results": []}, openalex_key="K", sleep=lambda s: None).openalex_doi("https://doi.org/10.1/ABC")
    assert seen["api_key"] == "K" and seen["filter"] == "doi:10.1/abc"

def test_success_cached_including_empty(tmp_path):
    calls = []
    mk = lambda: Lookup(fetch_json=lambda u, p, h: calls.append(1) or {"results": []}, sleep=lambda s: None, cache_path=tmp_path / "c.json")
    mk().openalex_title("Some, Title!"); mk().openalex_title("some title")
    assert calls == [1]

# --- review fixes ---
def test_normalize_title_unicode():
    assert normalize_title("Attention Is All You Need!") == "attentionisallyouneed"
    a, b, c = normalize_title("딥러닝 연구"), normalize_title("Глубокое обучение"), normalize_title("机器学习")
    assert a and b and c and len({a, b, c}) == 3

def test_openalex_doi_with_separator_skipped():
    called = []
    lk = Lookup(fetch_json=lambda *a: called.append(1), sleep=lambda s: None)
    assert lk.openalex_doi("10.1/a,b") == LookupOutcome([], False)
    assert lk.openalex_doi("10.1/a|b") == LookupOutcome([], False) and called == []

def test_unwritable_cache_does_not_crash(tmp_path):
    blocker = tmp_path / "file"; blocker.write_text("x")
    lk = Lookup(fetch_json=lambda u, p, h: FX("openalex_attention.json"), sleep=lambda s: None, cache_path=blocker / "c.json")
    out = lk.openalex_title("Attention Is All You Need")
    assert not out.failed and out.records

def test_crossref_null_date_part():
    d = FX("crossref_resnet.json"); d["message"]["items"][0]["issued"] = {"date-parts": [[2016, None]]}
    out = Lookup(fetch_json=lambda u, p, h: d, sleep=lambda s: None).crossref_title("x")
    assert not out.failed and (out.records[0].year, out.records[0].publication_date) == (2016, "2016")
