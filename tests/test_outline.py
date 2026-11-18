import copy
import json

import pytest

from po.cli import main
from po.outline import validate_outline, collect_search_tasks, estimate, inject_candidates
from po.settings import PROFILES, PLUGIN_DIR
from po.style import load_style

OUT = json.load(open("tests/fixtures/outline_valid.json"))
ML = load_style(PLUGIN_DIR / "styles/ml-conference.md")


def test_valid():
    assert validate_outline(OUT, ML, ["Kim2024Own"]) == []


@pytest.mark.parametrize("mutate,token", [
    (lambda o: o.pop("section_plan"), "missing key: section_plan"),
    (lambda o: o["plotting_plan"][0].update(figure_id="Figure_main"), "figure_id"),
    (lambda o: o["plotting_plan"][1].update(figure_id=o["plotting_plan"][0]["figure_id"]), "duplicate figure_id"),
    (lambda o: o["plotting_plan"][0].update(plot_type="chart"), "plot_type"),
    (lambda o: o["plotting_plan"][0].update(data_source="x.md"), "data_source"),
    (lambda o: o["plotting_plan"][0].update(aspect_ratio="7:3"), "aspect_ratio"),
    (lambda o: o["plotting_plan"][1].pop("aspect_ratio"), "aspect_ratio"),
    (lambda o: o["plotting_plan"][1].update(data_files=["nope/missing.csv"]), "data_files"),
    (lambda o: o["intro_related_work_plan"]["introduction_strategy"]["search_directions"].pop(), "search_directions"),
    (lambda o: o["intro_related_work_plan"]["introduction_strategy"].update(hook_hypothesis=" "), "hook_hypothesis"),
    (lambda o: o["intro_related_work_plan"]["related_work_strategy"]["subsections"].pop(), "related_work_strategy.subsections"),
    (lambda o: o["intro_related_work_plan"]["related_work_strategy"]["subsections"][0].pop("bridge_to_our_method"), "bridge_to_our_method"),
    (lambda o: o["section_plan"].pop(), "missing section: Limitations"),
    (lambda o: o["section_plan"][1]["subsections"].pop(), "orphan subsection"),
    (lambda o: o["section_plan"][2]["subsections"][0]["citation_hints"].append("ResNet paper"), "citation hint format"),
])
def test_invalid(mutate, token):
    o = copy.deepcopy(OUT)
    mutate(o)
    assert any(token in e for e in validate_outline(o, ML, ["Kim2024Own"]))


def test_data_files_exist(tmp_path):
    (tmp_path / "r.csv").write_text("a")
    o = copy.deepcopy(OUT)
    o["plotting_plan"][1]["data_files"] = ["r.csv"]
    assert validate_outline(o, ML, ["Kim2024Own"], tmp_path) == []


def test_must_cite_unassigned():
    assert "must-cite not assigned: Other2020X" in validate_outline(OUT, ML, ["Kim2024Own", "Other2020X"])


def test_tasks():
    t = collect_search_tasks(OUT)
    assert len(t) == 10 and [x["search_type"] for x in t].count("targeted") == 4
    sub = OUT["intro_related_work_plan"]["related_work_strategy"]["subsections"][1]
    assert t[5]["focus"] == f'{sub["subsection_title"]} {sub["methodology_cluster"]}'
    o = copy.deepcopy(OUT)
    o["intro_related_work_plan"]["introduction_strategy"]["search_directions"][0] = "changed"
    assert [a["id"] == b["id"] for a, b in zip(t, collect_search_tasks(o))].count(False) == 1


def test_estimate():
    f = estimate(OUT, PROFILES["full"])
    l = estimate(OUT, PROFILES["light"])
    assert (f["critic_runs_max"], f["review_passes_max"], f["reviewer_runs_max"], f["revisions_max"]) == (9, 4, 16, 3)
    assert (l["critic_runs_max"], l["review_passes_max"], l["reviewer_runs_max"], l["revisions_max"]) == (3, 2, 2, 1)
    assert (f["figures"], f["plots"], f["diagrams"], f["search_tasks"]) == (3, 2, 1, 10)


def test_inject():
    o = inject_candidates(copy.deepcopy(OUT), [{"key": "A2020X", "found_in_section": "Introduction"}])
    assert o["intro_related_work_plan"]["introduction_strategy"]["citation_candidates"] == ["A2020X"]
    subs = [s for sec in o["section_plan"] for s in sec["subsections"]]
    assert all("citation_hints" not in s for s in subs)
    assert any("Kim2024Own" in s["citation_candidates"] for s in subs)


def test_cli_roundtrip(tmp_path, capsys):
    paper = tmp_path / "paper"
    paper.mkdir()
    (paper / "outline.json").write_text(json.dumps(OUT))
    a = ["--paper", str(paper)]
    assert main(["outline", "validate", *a]) == 0
    assert main(["outline", "render", *a]) == 0
    assert "3.1 Temporal-Aware Attention Mechanism" in (paper / "outline.md").read_text()
    assert main(["outline", "tasks", *a]) == 0
    assert len(json.loads((paper / "references/tasks.json").read_text())) == 10
    assert main(["outline", "estimate", *a]) == 0
    assert main(["outline", "inject", *a]) == 2  # no library.json
    (paper / "references/library.json").write_text(
        json.dumps([{"key": "A2020X", "found_in_section": "Introduction"}]))
    assert main(["outline", "inject", *a]) == 0
    assert "citation_candidates" in json.loads((paper / "outline.json").read_text())["section_plan"][0]["subsections"][0]


def test_cli_validate_fails(tmp_path):
    paper = tmp_path / "paper"
    paper.mkdir()
    o = copy.deepcopy(OUT)
    o.pop("section_plan")
    (paper / "outline.json").write_text(json.dumps(o))
    assert main(["outline", "validate", "--paper", str(paper)]) == 1
