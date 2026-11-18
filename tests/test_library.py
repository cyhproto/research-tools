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


# ---- fix round 1 ------------------------------------------------------------

class SrcLookup(FakeLookup):
    def __init__(self, oa=None, s2=None, fail=False):
        super().__init__(oa, fail); self.s2 = s2 or {}
    def s2_title(self, t): return LookupOutcome(self.s2.get(t, []), False)


def S2R(title, abstract="s2 abs"):
    r = R(title, abstract=abstract); r.source = "semanticscholar"; return r


def test_s2_source_label_mapped():
    [e] = verify_candidates([C("Only S2")], [], SrcLookup(s2={"Only S2": [S2R("Only S2")]}), "2024-11").entries
    assert e.verified_by == "s2" and e.abstract_source == "s2"


def test_s2_abstract_fallback_label():
    lk = SrcLookup(oa={"Bare Paper": [R("Bare Paper", abstract=None)]}, s2={"Bare Paper": [S2R("Bare Paper")]})
    [e] = verify_candidates([C("Bare Paper")], [], lk, "2024-11").entries
    assert e.verified_by == "openalex" and (e.abstract, e.abstract_source) == ("s2 abs", "s2")


def test_bibtex_escaping():
    e = LibraryEntry("K", "R&D: 50% of {BERT} costs $5 #1 a_b", ["A_B & C"], "Conf~X^Y\\Z", 2020, None, None,
                     "openalex", False, "s", "r", doi="10.1/a_b{x}")
    bib = write_bibtex([e])
    assert "title={{R\\&D: 50\\% of \\{BERT\\} costs \\$5 \\#1 a\\_b}}" in bib
    assert "author={A\\_B \\& C}" in bib
    assert "booktitle={Conf\\textasciitilde{}X\\textasciicircum{}Y\\textbackslash{}Z}" in bib
    assert "doi={10.1/a_bx}" in bib


def test_duplicate_must_cite_keys_first_wins_with_warning():
    a = add_must_cite([ImportedRef("Dup", "First Work", ["A B"], 2020, None, None, None, "m.bib"),
                       ImportedRef("Dup", "Second Work", ["C D"], 2021, None, None, None, "m.bib")], FakeLookup())
    out, warns = dedupe_must_cite_keys(a)
    assert [e.title for e in out] == ["First Work"] and len(warns) == 1 and "Dup" in warns[0]


def test_cli_verify_reports_duplicate_must_cite_warning(tmp_path, monkeypatch, capsys):
    import types, po.library as lib, po.settings as st
    from po.cli import main
    _write_cand(tmp_path, "t1", ["Good Paper"])
    d = tmp_path / "materials/references"; d.mkdir(parents=True)
    (d / "must_cite.bib").write_text("@article{Dup, title={First Work}, author={A B}, year={2020}}\n"
                                     "@article{Dup, title={Second Work}, author={C D}, year={2021}}\n")
    monkeypatch.setattr(lib, "Lookup", lambda **kw: FakeLookup({"Good Paper": [R("Good Paper")]}))
    monkeypatch.setattr(st, "load_settings", lambda p: types.SimpleNamespace(cutoff="2024-11"))
    capsys.readouterr()
    assert main(["refs", "verify", "--paper", str(tmp_path)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert any("Dup" in w for w in out["warnings"]) and out["must_cite"] == 1


def test_done_marking_uses_snapshot(tmp_path):
    from po.state import is_task_done
    from po.library import _scan_candidates
    _write_cand(tmp_path, "t1", ["Good Paper"])
    files, _ = _scan_candidates(tmp_path)
    _write_cand(tmp_path, "t2", ["Other"])  # appears after the snapshot
    save_library(tmp_path, VerifyResult([], [], counts([], [])), files)
    assert is_task_done(tmp_path, "lit:t1") and not is_task_done(tmp_path, "lit:t2")


def test_resolved_candidates_not_retried_or_dropped(tmp_path):
    cand = C("Attn is all you need (2017)")
    lk = FakeLookup({cand.title: [R("Attention Is All You Need")]})
    first = verify_candidates([cand], [], lk, "2024-11")
    assert [e.title for e in first.entries] == ["Attention Is All You Need"]
    _write_cand(tmp_path, "t1", [cand.title])
    save_library(tmp_path, first)
    log = json.loads((tmp_path / "references/search_log.json").read_text())
    assert list(log["resolved"].values()) == [first.entries[0].key]
    prev = VerifyResult(load_library(tmp_path), log["dropped"], {}, log["resolved"])
    second = verify_candidates([cand], [], FakeLookup(fail=True), "2024-11", previous=prev)
    assert second.dropped == [] and [e.key for e in second.entries] == [first.entries[0].key]


def test_resolved_follows_key_rename_on_merge():
    cand = C("Deep Nets A")
    gen = verify_candidates([cand], [], FakeLookup({cand.title: [R(cand.title)]}), "2024-11")
    must = add_must_cite([ImportedRef("Lee2020DeepNets", "Mine", ["Me"], 2020, None, None, None, "m.bib")], FakeLookup())
    merged = merge_must_cite(gen, must)
    assert list(merged.resolved.values()) == ["Lee2020DeepNetsa"]


# ---- m8 / P37: keep the library re-checks kept entries against the current cutoff -----------
def test_kept_entries_are_rechecked_against_an_earlier_cutoff():
    oa = {"Early Paper": [R("Early Paper", 2019, "2019-05-01")],
          "Late Paper (2023)": [R("Late Paper", 2023, "2023-03-01")],
          "Cutoff Month Paper": [R("Cutoff Month Paper", 2022, "2022-12-20")]}
    cands = [C("Early Paper"), C("Late Paper (2023)", "t2"), C("Cutoff Month Paper")]
    first = verify_candidates(cands, [], FakeLookup(oa), "2024-11")
    assert len(first.entries) == 3
    must = add_must_cite([ImportedRef("Mine", "My Late Work", ["Me"], 2024, None, None, None, "m.bib")], FakeLookup())
    first = merge_must_cite(first, must)
    lookup = FakeLookup(oa)
    second = verify_candidates(cands, [], lookup, "2022-12", previous=first)
    assert sorted(e.title for e in second.entries) == ["Cutoff Month Paper", "Early Paper", "My Late Work"]
    assert second.dropped == [{"title": "Late Paper", "task_id": "t2", "reason": "after-cutoff"}]
    assert sorted(second.resolved.values()) == sorted(e.key for e in second.entries if not e.must_cite)
    assert second.counts["dropped_by_reason"] == {"after-cutoff": 1}


# ---- P39: a user-library entry is checked against the cutoff when it is admitted ------------
def test_user_library_entry_after_the_cutoff_is_dropped_at_once():
    imp = [ImportedRef("k1", "Only In Zotero Late", ["Z Z"], 2025, None, "J", "late abs", "library.bib"),
           ImportedRef("k2", "Only In Zotero Undated", ["Z Z"], None, None, "J", "undated abs", "library.bib")]
    cands = [C("Only In Zotero Late"), C("Only In Zotero Undated")]
    first = verify_candidates(cands, imp, FakeLookup(), "2024-11")
    assert [e.title for e in first.entries] == ["Only In Zotero Undated"]
    assert first.dropped == [{"title": "Only In Zotero Late", "task_id": "t1", "reason": "after-cutoff"}]
    second = verify_candidates(cands, imp, FakeLookup(), "2024-11", previous=first)  # keep the library
    assert [e.title for e in second.entries] == ["Only In Zotero Undated"] and second.dropped == first.dropped
