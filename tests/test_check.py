import json, shutil
from po.check import run_check, finalize
from po.cli import main

def setup(tmp_path, edit=lambda md: md):
    root = tmp_path / "proj"; shutil.copytree("tests/fixtures/checkpaper", root)
    p = root / "paper"; (p / "paper.md").write_text(edit((p / "paper.md").read_text())); return p, root

def statuses(items): return {(i.category, i.status) for i in items}

def test_baseline_ready(tmp_path):
    p, root = setup(tmp_path)
    items = run_check(p, root)
    assert not [i for i in items if i.status in ("fail", "needs_ruling")]
    assert finalize(p, {})["status_line"] == "READY"

def test_planted_fake_citation_and_number(tmp_path):
    p, root = setup(tmp_path, lambda md: md.replace("## Conclusion", "We also reach 91.7 on X [@Fake2024Paper].\n\n## Conclusion"))
    items = run_check(p, root)
    assert any(i.status == "fail" and "Fake2024Paper" in i.message for i in items)
    assert any(i.category == "numbers" and i.status == "needs_ruling" and i.data["token"] == "91.7" for i in items)
    assert finalize(p, {})["status_line"] == "NOT READY: 2 problems"

def test_title_only_ruling(tmp_path):
    p, root = setup(tmp_path, lambda md: md.replace("## Conclusion", "Lee et al. report 95.1% accuracy [@Lee2022Graph].\n\n## Conclusion"))
    pend = [i for i in run_check(p, root) if i.status == "needs_ruling"]
    assert {i.category for i in pend} == {"citations", "numbers"}
    assert finalize(p, {i.id: {"ruling": "fail", "reason": "specific result", "arithmetic": None} for i in pend})["problems"] == 2

def test_allowed_derived_number(tmp_path):
    p, root = setup(tmp_path, lambda md: md.replace("## Conclusion", "This improves by 2.3 points.\n\n## Conclusion"))
    [i] = [i for i in run_check(p, root) if i.status == "needs_ruling"]
    out = finalize(p, {i.id: {"ruling": "allow", "reason": "difference", "arithmetic": "87.3 - 85.0 = 2.3"}})
    assert out["ready"] and "87.3 - 85.0 = 2.3" in (p / "review.md").read_text()

def test_figure_venue_mustcite_rules(tmp_path):
    p, root = setup(tmp_path, lambda md: md.replace("Figure 1 shows", "It shows").replace("## Limitations", "## Notes")
                    .replace("[@Kim2024Own]", "") + "\ncontact: jane@uni.edu\n")
    msgs = " ".join(i.message for i in run_check(p, root) if i.status == "fail")
    assert "Figure 1" in msgs and "Limitations" in msgs and "Kim2024Own" in msgs and "email" in msgs

def fails(items, cat=None):
    return [i for i in items if i.status == "fail" and (cat is None or i.category == cat)]

def test_source_tag_left_in_paper(tmp_path):
    p, root = setup(tmp_path, lambda md: md.replace("## Conclusion", "Gain 87.3 [src: results/m.csv | row=last | col=acc].\n\n## Conclusion"))
    items = run_check(p, root)
    assert any(i.category == "numbers" and i.status == "fail" and i.message == "source tag left in paper" for i in items)
    assert not [i for i in items if i.status == "needs_ruling"]

def test_urls_not_numbers(tmp_path):
    p, root = setup(tmp_path, lambda md: md.replace("## Conclusion", "See <https://x.org/v3/2931> and https://y.org/a/4471 now.\n\n## Conclusion"))
    assert not [i for i in run_check(p, root) if i.status == "needs_ruling"]

def test_embedding_plot_and_diagram(tmp_path):
    p, root = setup(tmp_path, lambda md: md.replace("![Main results](figures/fig_main.png)\n\n", ""))
    assert any("fig_main" in i.message for i in fails(run_check(p, root), "figures"))
    (p / "figures/d.mmd").write_text("graph TD\n  A --> B\n")
    info = json.loads((p / "figures/info.json").read_text())
    info.append({"id": "d", "kind": "diagram", "file": "figures/d.mmd", "caption": "c", "description": ""})
    (p / "figures/info.json").write_text(json.dumps(info))
    md = (p / "paper.md").read_text()
    (p / "paper.md").write_text(md.replace("## Conclusion", "```mermaid\ngraph TD\n    A --> B\n```\n\n## Conclusion"))
    msgs = " ".join(i.message for i in fails(run_check(p, root), "figures"))
    assert "figures/d.mmd" not in msgs
    (p / "paper.md").write_text(md.replace("## Conclusion", "```mermaid\ngraph TD\n    A --> C\n```\n\n## Conclusion"))
    assert "figures/d.mmd" in " ".join(i.message for i in fails(run_check(p, root), "figures"))

def test_missing_image_and_table_caption(tmp_path):
    p, root = setup(tmp_path, lambda md: md.replace("## Conclusion", "*Table 2: results.*\n\n| a |\n|---|\n| b |\n\n## Conclusion"))
    (p / "figures/fig_main.png").unlink()
    msgs = " ".join(i.message for i in fails(run_check(p, root), "figures"))
    assert "fig_main.png" in msgs and "Table 2" in msgs

def test_length_and_blind(tmp_path):
    p, root = setup(tmp_path, lambda md: md.replace("# A Graph Method", "# A Graph Method by Jane Roe"))
    assert any("Jane Roe" in i.message for i in fails(run_check(p, root), "venue"))
    (p / "settings.md").write_text("---\nstyle: ml-conference\ncutoff: 2025-06\nblind_review: false\nauthors: [Jane Roe]\n---\n")
    assert not fails(run_check(p, root), "venue")
    (p / "paper.md").write_text("# T\n\n## Abstract\n\nshort\n")
    assert any("words" in i.message for i in fails(run_check(p, root), "venue"))

def test_ids_and_cli(tmp_path, capsys):
    p, root = setup(tmp_path, lambda md: md.replace("## Conclusion", "A 91.7 and 92.7 here.\n\n## Conclusion"))
    ids = [i.id for i in run_check(p, root) if i.category == "numbers"]
    assert ids == ["numbers-001", "numbers-002"]
    assert main(["check", "run", "--paper", str(p)]) == 0
    assert json.loads(capsys.readouterr().out)["needs_ruling"] == 2
    assert (p / "check/report.json").is_file()
    rf = tmp_path / "r.json"; rf.write_text("")
    assert main(["check", "finalize", "--paper", str(p), "--rulings", str(rf)]) == 1
    assert "NOT READY: 2 problems" in capsys.readouterr().out
    rf.write_text(json.dumps({i: {"ruling": "allow", "reason": "r", "arithmetic": None} for i in ids}))
    assert main(["check", "finalize", "--paper", str(p), "--rulings", str(rf)]) == 0
    assert main(["check", "finalize", "--paper", str(p), "--rulings", str(tmp_path / "none.json")]) == 1


STYLE_REQ = "required_statements:\n  - Data and code availability\n"

def _req_setup(tmp_path, edit):
    p, root = setup(tmp_path, edit)
    st = (p / "style.md").read_text().replace("required_statements: []", STYLE_REQ.rstrip("\n"))
    (p / "style.md").write_text(st)
    return p, root

def test_required_statement_matches_section_name(tmp_path):
    p, root = _req_setup(tmp_path, lambda md: md.replace("## References", "## 7. Data and code availability\n\nAll public.\n\n## References"))
    assert not fails(run_check(p, root), "venue")
    p, root = _req_setup(tmp_path / "b", lambda md: md.replace("We evaluate on", "Data and code availability: none. We evaluate on"))
    assert any("Data and code availability" in i.message for i in fails(run_check(p, root), "venue"))
    p, root = _req_setup(tmp_path / "c", lambda md: md)
    assert any("Data and code availability" in i.message for i in fails(run_check(p, root), "venue"))

def test_missing_figures_link_target(tmp_path):
    p, root = setup(tmp_path, lambda md: md.replace("## Conclusion", "![x](figures/ghost.png)\n![y](figures/ghost.png)\n\n```\n![z](figures/code.png)\n```\n\n## Conclusion"))
    msgs = [i.message for i in fails(run_check(p, root), "figures")]
    assert sum("ghost.png" in m for m in msgs) == 1 and not any("code.png" in m for m in msgs)

def test_plural_and_range_references(tmp_path):
    def edit(md):
        md = md.replace("Figure 1 shows", "Figures 1 and 2 show")
        return md.replace("## Conclusion", "*Figure 2: other.*\n\n*Figure 12: more.*\n\n*Table 3: t.*\n\n*Table 4: u.*\n\nSee Tables 2-4 and Fig 12.\n\n## Conclusion")
    msgs = " ".join(i.message for i in fails(run_check(*setup(tmp_path, edit)), "figures"))
    assert "Figure 2" not in msgs and "Figure 12" not in msgs and "Table 3" not in msgs and "Table 4" not in msgs
    msgs = " ".join(i.message for i in fails(run_check(*setup(tmp_path / "b", lambda md: edit(md).replace("Fig 12", "Fig 120"))), "figures"))
    assert "Figure 12 " in msgs + " "

def test_caption_in_fence_and_reference_entries_ignored(tmp_path):
    p, root = setup(tmp_path, lambda md: md.replace("## Conclusion", "```\n*Table 9: x.*\n```\n\n## Conclusion").replace("## References\n\n", "## References\n\n- [@Old2020] See Table 9.\n"))
    assert not [i for i in fails(run_check(p, root), "figures")]
    p, root = setup(tmp_path / "b", lambda md: md.replace("Figure 1 shows", "It shows").replace("## References\n\n", "## References\n\n- [@Old2020] See Figure 1.\n"))
    assert any("Figure 1" in i.message for i in fails(run_check(p, root), "figures"))

def test_text_under_references_is_checked_and_warned(tmp_path):
    p, root = setup(tmp_path, lambda md: md + "\nWe also reach 91.7 [@Fake2024Paper].\n\nSee Figure 1.\n")
    items = run_check(p, root)
    n = len((p / "paper.md").read_text().splitlines())
    assert any(i.status == "fail" and "Fake2024Paper" in i.message and i.line == n - 2 for i in items)
    assert any(i.category == "numbers" and i.status == "needs_ruling" and i.data["token"] == "91.7" for i in items)
    [w] = [i for i in items if i.category == "references"]
    assert w.status == "warn" and w.line == n - 2 and f"lines {n - 2}, {n}" in w.message and "heading" in w.message
    assert finalize(p, {})["status_line"] == "NOT READY: 2 problems"

def test_author_whole_word_and_appendix(tmp_path):
    p, root = setup(tmp_path)
    (p / "settings.md").write_text("---\nstyle: ml-conference\ncutoff: 2025-06\nblind_review: true\nauthors: [Li]\n---\n")
    assert not fails(run_check(p, root), "venue")
    (p / "paper.md").write_text((p / "paper.md").read_text().replace("single benchmark", "single benchmark by Li"))
    assert any("Li" in i.message for i in fails(run_check(p, root), "venue"))
    (p / "style.md").write_text((p / "style.md").read_text().replace("[10, 2000]", "[10, 150]"))
    (p / "paper.md").write_text((p / "paper.md").read_text().replace("by Li", "") + "\n## Appendix A\n\n" + "word " * 500)
    assert not [i for i in fails(run_check(p, root), "venue") if "words" in i.message]

def test_bad_ruling_values_and_multiline_reason(tmp_path):
    p, root = setup(tmp_path, lambda md: md.replace("## Conclusion", "This improves by 2.3 points.\n\n## Conclusion"))
    [i] = [i for i in run_check(p, root) if i.status == "needs_ruling"]
    assert finalize(p, {i.id: "allow"})["problems"] == 1
    finalize(p, {i.id: {"ruling": "fail", "reason": "x\n## Experiments\ny", "arithmetic": "a\n\nb"}})
    text = (p / "review.md").read_text()
    assert "## Experiments" not in text.replace("x ## Experiments y", "")
    finalize(p, {})
    assert text.count("## Check") == 1 == (p / "review.md").read_text().count("## Check")


def test_finalize_flags_missing_rulings(tmp_path, capsys):
    p, root = setup(tmp_path, lambda md: md.replace("## Conclusion", "This improves by 2.3 points.\n\n## Conclusion"))
    assert main(["check", "run", "--paper", str(p)]) == 0
    capsys.readouterr()
    wrong = tmp_path / "check/rulings.json"  # e.g. a path resolved against the wrong directory
    assert main(["check", "finalize", "--paper", str(p), "--rulings", str(wrong)]) == 1
    cap = capsys.readouterr()
    assert json.loads(cap.out)["rulings_missing"] is True and "missing or empty" in cap.err
    rf = tmp_path / "r.json"; rf.write_text("  \n")
    assert main(["check", "finalize", "--paper", str(p), "--rulings", str(rf)]) == 1
    assert json.loads(capsys.readouterr().out)["rulings_missing"] is True
    [item] = [i for i in json.loads((p / "check/report.json").read_text())["items"] if i["status"] == "needs_ruling"]
    rf.write_text(json.dumps({item["id"]: {"ruling": "allow", "reason": "difference", "arithmetic": "87.3 - 85.0 = 2.3"}}))
    assert main(["check", "finalize", "--paper", str(p), "--rulings", str(rf)]) == 0
    cap = capsys.readouterr()
    assert json.loads(cap.out)["rulings_missing"] is False and cap.err == ""
    q, _ = setup(tmp_path / "b")  # nothing needs a ruling: a missing file is fine
    assert main(["check", "run", "--paper", str(q)]) == 0
    capsys.readouterr()
    assert main(["check", "finalize", "--paper", str(q), "--rulings", str(wrong)]) == 0
    cap = capsys.readouterr()
    assert json.loads(cap.out)["rulings_missing"] is False and cap.err == ""


def test_finalize_empty_object_rulings_count_as_missing(tmp_path, capsys):
    p, root = setup(tmp_path, lambda md: md.replace("## Conclusion", "This improves by 2.3 points.\n\n## Conclusion"))
    assert main(["check", "run", "--paper", str(p)]) == 0
    capsys.readouterr()
    rf = tmp_path / "r.json"; rf.write_text("{}")
    assert main(["check", "finalize", "--paper", str(p), "--rulings", str(rf)]) == 1
    cap = capsys.readouterr()
    assert json.loads(cap.out)["rulings_missing"] is True and "missing or empty" in cap.err


# --- P21: a number from the abstract of a paper cited in the same sentence ---------------

def _set_abstract(p, key, text):
    lib = json.loads((p / "references/library.json").read_text())
    for e in lib:
        if e["key"] == key:
            e["abstract"] = text
    (p / "references/library.json").write_text(json.dumps(lib))

ABSTRACT = "We study deep methods for benchmark X and reach 92.4% accuracy."

def _numbers(items):
    return [i for i in items if i.category == "numbers"]

def test_number_from_cited_abstract_passes(tmp_path):
    p, root = setup(tmp_path, lambda md: md.replace(
        "## Conclusion", "Deep methods reach 92.4%\non X [@Kim2024Own; @Smith2023Deep].\n\n## Conclusion"))
    _set_abstract(p, "Smith2023Deep", ABSTRACT)
    [it] = _numbers(run_check(p, root))
    assert it.status == "pass" and it.data["key"] == "Smith2023Deep" and it.data["token"] == "92.4%"
    assert "from the abstract of [@Smith2023Deep]" in it.message
    out = finalize(p, {})
    assert out["ready"] and "from the abstract of [@Smith2023Deep]" in (p / "review.md").read_text()

def test_number_missing_from_cited_abstract_stays_unmatched(tmp_path):
    p, root = setup(tmp_path, lambda md: md.replace("## Conclusion", "Deep methods reach 93.5% on X [@Smith2023Deep].\n\n## Conclusion"))
    _set_abstract(p, "Smith2023Deep", ABSTRACT)
    assert [(i.status, i.data["token"]) for i in _numbers(run_check(p, root))] == [("needs_ruling", "93.5%")]

def test_number_in_abstract_of_entry_cited_elsewhere_stays_unmatched(tmp_path):
    p, root = setup(tmp_path, lambda md: md.replace(
        "## Conclusion", "Deep methods reach 92.4% on X [@Kim2024Own]. They are fast [@Smith2023Deep].\n\n## Conclusion"))
    _set_abstract(p, "Smith2023Deep", ABSTRACT)
    assert [i.status for i in _numbers(run_check(p, root))] == ["needs_ruling"]

def test_number_cited_to_title_only_entry_stays_unmatched(tmp_path):
    p, root = setup(tmp_path, lambda md: md.replace("## Conclusion", "Lee et al. report 92.4% accuracy [@Lee2022Graph].\n\n## Conclusion"))
    _set_abstract(p, "Smith2023Deep", ABSTRACT)
    assert [i.status for i in _numbers(run_check(p, root))] == ["needs_ruling"]


# --- C1: reference-manager exports are not materials ------------------------------------

def test_reference_exports_are_not_materials(tmp_path):
    p, root = setup(tmp_path, lambda md: md.replace(
        "## Conclusion", "Our method reaches 91.7 on X, a gain of 3.42 points.\n\n## Conclusion"))
    refs = p / "materials/references"; refs.mkdir()
    (refs / "library.json").write_text(json.dumps([{"id": "Other2023", "type": "article-journal",
        "title": "Another Method", "abstract": "It reaches 91.7 on X, a gain of 3.42 points.",
        "issued": {"date-parts": [[2023]]}}]))
    (refs / "must_cite.json").write_text(json.dumps([{"id": "Mine2024", "title": "My Work",
        "abstract": "We reach 91.7 and 3.42."}]))
    (refs / "notes.md").write_text("Numbers 91.7 and 3.42 copied from a PDF.\n")
    got = {i.data["token"]: i.status for i in run_check(p, root) if i.category == "numbers"}
    assert got == {"91.7": "needs_ruling", "3.42": "needs_ruling"}


# --- I1 / P32: a crash exits 2; Check never reports from a stale run ---------------------

def _break_library(p):
    lib = p / "references/library.json"
    lib.write_text(lib.read_text().rstrip().rstrip("]") + ",]")  # a trailing comma, as a hand edit might leave


def _missing_style(p):
    (p / "style.md").unlink()
    (p / "settings.md").write_text((p / "settings.md").read_text().replace("ml-conference", "my-venue"))


import pytest


@pytest.mark.parametrize("breakage", [_break_library, _missing_style])
def test_failed_check_run_exits_2_and_leaves_no_report(tmp_path, capsys, breakage):
    p, root = setup(tmp_path, lambda md: md.replace("## Conclusion", "We reach 99.9 [@Fake2024Paper].\n\n## Conclusion"))
    assert main(["check", "run", "--paper", str(p)]) == 0
    capsys.readouterr()
    breakage(p)
    assert main(["check", "run", "--paper", str(p)]) == 2
    cap = capsys.readouterr()
    assert cap.out == "" and "Traceback" not in cap.err and cap.err.count("\n") == 1
    assert cap.err.split(":")[0] in ("LibraryError", "StyleNotFound")
    assert ("library.json" if breakage is _break_library else "my-venue") in cap.err
    assert not (p / "check/report.json").exists()
    assert main(["check", "finalize", "--paper", str(p)]) == 2
    cap = capsys.readouterr()
    assert cap.out == "" and "check run" in cap.err
    assert not (p / "review.md").exists()


def test_finalize_refuses_a_report_older_than_paper_md(tmp_path, capsys):
    p, root = setup(tmp_path)
    assert main(["check", "run", "--paper", str(p)]) == 0
    assert finalize(p, {})["ready"]
    (p / "review.md").unlink()
    md = p / "paper.md"
    md.write_text(md.read_text().replace("## Conclusion", "We reach 99.9 [@Fake2024Paper].\n\n## Conclusion"))
    capsys.readouterr()
    assert main(["check", "finalize", "--paper", str(p)]) == 2
    cap = capsys.readouterr()
    assert cap.out == "" and "paper.md changed" in cap.err
    assert not (p / "review.md").exists()
    # a report without the paper.md hash (an older one) is not trusted either
    assert main(["check", "run", "--paper", str(p)]) == 0
    rep = p / "check/report.json"
    data = json.loads(rep.read_text())
    assert len(data.pop("paper_sha256")) == 64
    rep.write_text(json.dumps(data))
    assert main(["check", "finalize", "--paper", str(p)]) == 2


def test_finalize_errors_go_to_stderr(tmp_path, capsys):
    p, root = setup(tmp_path)
    assert main(["check", "run", "--paper", str(p)]) == 0
    capsys.readouterr()
    rf = tmp_path / "r.json"
    for bad in ("{oops", "[1]"):
        rf.write_text(bad)
        assert main(["check", "finalize", "--paper", str(p), "--rulings", str(rf)]) == 2
        cap = capsys.readouterr()
        assert cap.out == "" and "rulings file" in cap.err


def test_main_turns_any_exception_into_exit_2(monkeypatch, capsys):
    import po.cli as cli
    monkeypatch.setattr(cli, "COMMAND_MODULES", cli.COMMAND_MODULES + ["no_such_module"])
    assert cli.main(["version"]) == 2
    cap = capsys.readouterr()
    assert cap.out == "" and cap.err.startswith("ModuleNotFoundError: ") and "Traceback" not in cap.err


# --- m2 / P37: DBLP keys; bare @key citations -------------------------------------------------

def _add_entry(p, key, must_cite=False):
    lib = json.loads((p / "references/library.json").read_text())
    lib.append({"key": key, "title": "Attention", "authors": ["A V"], "venue": "NeurIPS", "year": 2017,
                "abstract": "Transformers.", "abstract_source": "openalex", "verified_by": "openalex",
                "must_cite": must_cite, "found_in_section": "Introduction", "reason": "r"})
    (p / "references/library.json").write_text(json.dumps(lib))


def test_dblp_must_cite_key_is_read_whole(tmp_path):
    key = "DBLP:conf/nips/VaswaniSPUJGKP17"
    p, root = setup(tmp_path, lambda md: md.replace("## Conclusion", f"Attention helps [@{key}].\n\n## Conclusion"))
    _add_entry(p, key, must_cite=True)
    assert not [i.message for i in run_check(p, root) if i.category == "citations" and i.status == "fail"]


def test_bare_keys_in_check(tmp_path):
    # a bare library key cites (must-cite satisfied); a bare unknown key is a warning, not a FAIL
    p, root = setup(tmp_path, lambda md: md.replace("[@Kim2024Own]", "").replace(
        "## Conclusion", "As @Kim2024Own showed, and as @Someone2020 says, Recall@10 rises.\n\n## Conclusion"))
    items = run_check(p, root)
    cit = [(i.status, i.message) for i in items if i.category == "citations"]
    assert not [m for s, m in cit if s == "fail"]
    [w] = [m for s, m in cit if s == "warn" and "Someone2020" in m]
    assert "@Someone2020" in w and "Recall" not in " ".join(m for _, m in cit)


# --- m11 / P37: one period at the end of each Check line ---------------------------------------

def test_check_lines_end_in_one_period(tmp_path):
    p, root = setup(tmp_path, lambda md: md.replace(
        "## Conclusion", "This improves by 2.3 points. We reach 99.9 on Y.\n\n## Conclusion") + "\nMy note.\n")
    a, b = [i.id for i in run_check(p, root) if i.status == "needs_ruling"]
    finalize(p, {a: {"ruling": "allow", "reason": "A difference.", "arithmetic": "87.3 - 85.0 = 2.3"},
                 b: {"ruling": "fail", "reason": "Not in the materials!", "arithmetic": None}})
    text = (p / "review.md").read_text()
    lines = [l for l in text.splitlines() if l.startswith("- ")]
    assert lines and all(l.endswith((".", "!", "?", "2.3")) for l in lines), lines
    assert ".." not in text and "Reason: A difference. Arithmetic: 87.3 - 85.0 = 2.3" in text
    assert "Reason: Not in the materials!" in text


def test_reference_exports_are_skipped_in_any_letter_case(tmp_path):
    # macOS file systems ignore case by default, so materials/References/ is still the import folder
    p, root = setup(tmp_path, lambda md: md.replace("## Conclusion", "Our method reaches 91.7 on X.\n\n## Conclusion"))
    refs = p / "materials/References"; refs.mkdir()
    (refs / "library.json").write_text(json.dumps([{"id": "Other2023", "title": "Another Method",
                                                    "abstract": "It reaches 91.7 on X."}]))
    got = {i.data["token"]: i.status for i in run_check(p, root) if i.category == "numbers"}
    assert got == {"91.7": "needs_ruling"}
