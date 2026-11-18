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
