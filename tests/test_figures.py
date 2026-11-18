import json
from po.figures import collect_figures

def test_collect(tmp_path):
    (tmp_path / "figures/meta").mkdir(parents=True); (tmp_path / "materials/figures").mkdir(parents=True)
    (tmp_path / "figures/fig_a.png").write_bytes(b"x"); (tmp_path / "figures/fig_b.mmd").write_text("flowchart LR\nA-->B")
    for i, kind, f in [("fig_a", "plot", "figures/fig_a.png"), ("fig_b", "diagram", "figures/fig_b.mmd")]:
        (tmp_path / f"figures/meta/{i}.json").write_text(json.dumps(dict(id=i, kind=kind, file=f, caption="ok cap", description="d", critic_rounds=[])))
    (tmp_path / "materials/figures/overview.png").write_bytes(b"x")
    (tmp_path / "materials/figures/captions.md").write_text("- overview.png: Overview of the method.\n")
    info, errors = collect_figures(tmp_path)
    assert [x["kind"] for x in info] == ["plot", "diagram", "supplied"] and errors == []
    assert (tmp_path / "figures/overview.png").exists()
    assert (tmp_path / "figures/info.json").is_file()
    (tmp_path / "figures/meta/fig_a.json").write_text(json.dumps(dict(id="fig_a", kind="plot", file="figures/fig_a.png", caption="Figure 2: x", description="d", critic_rounds=[])))
    assert collect_figures(tmp_path)[1]

def test_collect_errors(tmp_path):
    (tmp_path / "figures/meta").mkdir(parents=True); (tmp_path / "materials/figures").mkdir(parents=True)
    (tmp_path / "figures/meta/a.json").write_text(json.dumps(dict(id="a", kind="plot", file="figures/a.png", caption="fine", description="d", critic_rounds=[])))
    (tmp_path / "materials/figures/pic.png").write_bytes(b"x")
    (tmp_path / "materials/figures/captions.md").write_text("- pic.png: Fig. 3 something\n")
    _, errors = collect_figures(tmp_path)
    assert any("a.png" in e for e in errors) and any("pic.png" in e for e in errors)
    (tmp_path / "figures/meta/a.json").write_text(json.dumps(dict(id="a", kind="plot", file="figures/a.png", caption=" ", description="d", critic_rounds=[])))
    assert any("empty caption" in e for e in collect_figures(tmp_path)[1])

def test_cli_collect(tmp_path, capsys):
    from po.cli import main
    (tmp_path / "figures/meta").mkdir(parents=True)
    assert main(["figures", "collect", "--paper", str(tmp_path)]) == 0
    assert json.loads(capsys.readouterr().out)["figures"] == []
