import json
from po.library import *
from po.library import merge_must_cite
from po.scholar import PaperRecord, LookupOutcome
from po.bibimport import ImportedRef


def test_make_key_examples():
    assert make_key(["Ashish Vaswani", "Noam Shazeer"], 2017, "Attention Is All You Need") == "Vaswani2017AttentionAll"
    assert make_key([], None, "The Study") == "UnknownndPaper"


def test_make_key_non_ascii():
    assert make_key(["José Müller-López"], 2020, "Über Graphs") == "Mullerlopez2020UberGraphs"
    assert make_key(["김철수"], 2021, "딥러닝 연구") == "Unknown2021Paper"


class FakeLookup:
    def __init__(self, oa=None, fail=False): self.oa, self.fail = oa or {}, fail
    def openalex_title(self, t): return LookupOutcome(self.oa.get(t, []), self.fail)
    openalex_doi = lambda self, d: LookupOutcome([], self.fail)
    s2_title = lambda self, t: LookupOutcome([], False)
    crossref_title = lambda self, t: LookupOutcome([], self.fail)


def R(title, year=2020, date=None, abstract="abs"):
    return PaperRecord(title, ["Ann Lee"], year, date, "Venue", None, None, None, "10.1/x" + title[:3], abstract, 5, {}, "openalex")
C = lambda title, tid="t1": Candidate(tid, "Introduction", "exploration", title, 2020, "why")


def test_verify_paths():
    oa = {"Good Paper": [R("Good Paper")], "Bare Paper": [R("Bare Paper", abstract=None)],
          "Late Paper": [R("Late Paper", 2025, "2025-03-01")]}
    imp = [ImportedRef("k", "Only In Zotero", ["Z Z"], 2019, None, "J", "zabs", "library.bib")]
    res = verify_candidates([C("Good Paper"), C("Bare Paper"), C("Late Paper"), C("Missing Paper"),
                             C("Good Paper"), C("Only In Zotero")], imp, FakeLookup(oa), "2024-11")
    by = {e.title: e for e in res.entries}
    assert by["Good Paper"].abstract_source == "openalex" and by["Bare Paper"].title_only
    assert by["Only In Zotero"].verified_by == "user-library" and by["Only In Zotero"].abstract == "zabs"
    assert {d["title"]: d["reason"] for d in res.dropped} == {"Late Paper": "after-cutoff", "Missing Paper": "not-found"}
    assert res.counts == {"with_abstract": 2, "title_only": 1, "must_cite": 0, "dropped": 2,
                          "dropped_by_reason": {"after-cutoff": 1, "not-found": 1}}


def test_import_abstract_wins_by_doi():
    imp = [ImportedRef("k", "Good Paper", ["Ann Lee"], 2020, "10.1/xGoo", "V", "mine", "library.bib")]
    [e] = verify_candidates([C("Good Paper")], imp, FakeLookup({"Good Paper": [R("Good Paper")]}), "2024-11").entries
    assert (e.abstract, e.abstract_source) == ("mine", "import")


def test_lookup_failed_is_retried():
    first = verify_candidates([C("Good Paper")], [], FakeLookup(fail=True), "2024-11")
    assert first.dropped[0]["reason"] == "lookup-failed"
    second = verify_candidates([C("Good Paper")], [], FakeLookup({"Good Paper": [R("Good Paper")]}), "2024-11", previous=first)
    assert [e.title for e in second.entries] == ["Good Paper"]


def test_must_cite_vouched():
    [e] = add_must_cite([ImportedRef("m", "My In-Press Work", ["Me Me"], 2026, None, None, None, "must_cite.bib")], FakeLookup())
    assert (e.verified_by, e.must_cite, e.title_only) == ("user-vouched", True, True)


def test_unique_keys_and_bibtex():
    titles = ["Deep Nets A", "Deep Nets B", "Deep Nets C"]
    es = verify_candidates([C(t) for t in titles], [], FakeLookup({t: [R(t)] for t in titles}), "2024-11").entries
    assert [e.key for e in es] == ["Lee2020DeepNets", "Lee2020DeepNetsa", "Lee2020DeepNetsb"]
    e = es[0]; bib = write_bibtex([e])
    assert bib.startswith("@inproceedings{") and "booktitle={Venue}" in bib and "doi={" in bib


def test_partial_candidate_file_is_not_done(tmp_path):
    d = tmp_path / "references/candidates"; d.mkdir(parents=True)
    (d / "t1.json").write_text('{"task_id": "t1", "candidates": [')
    cands, invalid = load_candidates(tmp_path)
    assert cands == [] and invalid == ["t1.json"]


# ---- Ruling P4 -------------------------------------------------------------

def test_must_cite_key_never_renamed_generated_takes_suffix():
    must = add_must_cite([ImportedRef("Lee2020DeepNets", "My Own Work", ["Me Me"], 2020, None, None, None, "m.bib")],
                         FakeLookup())
    gen = verify_candidates([C("Deep Nets A")], [], FakeLookup({"Deep Nets A": [R("Deep Nets A")]}), "2024-11")
    assert gen.entries[0].key == "Lee2020DeepNets"
    merged = merge_must_cite(gen, must)
    by = {e.title: e.key for e in merged.entries}
    assert by["My Own Work"] == "Lee2020DeepNets"
    assert by["Deep Nets A"] == "Lee2020DeepNetsa"


def test_must_cite_wins_over_candidate_with_same_title_or_doi():
    imp = ImportedRef("MyKey", "Good Paper", ["Ann Lee"], 2020, None, "V", "mine", "must_cite.bib")
    must = add_must_cite([imp], FakeLookup({"Good Paper": [R("Good Paper")]}))
    gen = verify_candidates([C("Good Paper")], [], FakeLookup({"Good Paper": [R("Good Paper")]}), "2024-11")
    merged = merge_must_cite(gen, must)
    [e] = merged.entries
    assert e.key == "MyKey" and e.must_cite is True
    assert merged.counts["must_cite"] == 1
    # same DOI, different title
    imp2 = ImportedRef("K2", "Totally Different Title", ["Ann Lee"], 2020, "https://doi.org/10.1/xGoo", None, None, "m.bib")
    must2 = add_must_cite([imp2], FakeLookup())
    merged2 = merge_must_cite(gen, must2)
    assert [(e.key, e.must_cite) for e in merged2.entries] == [("K2", True)]


def test_assign_unique_keys_keeps_must_cite_even_when_listed_late():
    def E(key, must=False):
        return LibraryEntry(key, "t", [], None, None, None, None, "openalex", must, "s", "r")
    es = [E("A"), E("A", True), E("A")]
    assign_unique_keys(es)
    assert [e.key for e in es] == ["Aa", "A", "Ab"]


# ---- persistence / CLI ------------------------------------------------------

def _write_cand(tmp_path, tid, titles):
    d = tmp_path / "references/candidates"; d.mkdir(parents=True, exist_ok=True)
    (d / f"{tid}.json").write_text(json.dumps({"task_id": tid, "section": "Intro", "search_type": "macro",
        "candidates": [{"title": t, "year": 2020, "reason": "r"} for t in titles]}))


def test_save_load_roundtrip_and_task_done(tmp_path):
    from po.state import is_task_done
    _write_cand(tmp_path, "t1", ["Good Paper", "Missing Paper"])
    (tmp_path / "references/candidates/bad.json").write_text("{")
    cands, invalid = load_candidates(tmp_path)
    res = verify_candidates(cands, [], FakeLookup({"Good Paper": [R("Good Paper")]}), "2024-11")
    save_library(tmp_path, res)
    assert is_task_done(tmp_path, "lit:t1") and not is_task_done(tmp_path, "lit:bad")
    lib = json.loads((tmp_path / "references/library.json").read_text())
    assert isinstance(lib, list) and lib[0]["key"] and lib[0]["found_in_section"] == "Intro"
    assert (tmp_path / "references/references.bib").read_text().startswith("@")
    log = json.loads((tmp_path / "references/search_log.json").read_text())
    assert log["dropped"] == [{"title": "Missing Paper", "task_id": "t1", "reason": "not-found"}]
    assert log["tasks"]["t1"] == {"section": "Intro", "search_type": "macro", "candidates": 2}
    assert [e.key for e in load_library(tmp_path)] == [e["key"] for e in lib]


def test_cli_verify_missing_dir(tmp_path):
    from po.cli import main
    assert main(["refs", "verify", "--paper", str(tmp_path)]) == 2


def test_cli_counts_and_import_check(tmp_path, capsys):
    from po.cli import main
    _write_cand(tmp_path, "t1", ["Good Paper"])
    cands, _ = load_candidates(tmp_path)
    save_library(tmp_path, verify_candidates(cands, [], FakeLookup({"Good Paper": [R("Good Paper")]}), "2024-11"))
    capsys.readouterr()
    assert main(["refs", "counts", "--paper", str(tmp_path)]) == 0
    assert json.loads(capsys.readouterr().out)["with_abstract"] == 1
    assert main(["refs", "import-check", "--paper", str(tmp_path)]) == 0
