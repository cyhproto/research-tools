# tests/test_fixtures.py
from pathlib import Path
from po.materials import validate_materials

def test_tsam_materials_validate():
    p = Path("tests/fixtures/tsam/paper")
    r = validate_materials(p, p.parent)
    assert r.missing == {"idea.md": [], "experiment_log.md": []} and r.has_results
    assert r.figures == ["tsam_overview.png"] and r.captions_missing == []


def test_journal_topic_fixture(capsys):
    import json
    from po.bibimport import load_imports
    from po.cli import main
    p = Path("tests/fixtures/journal_topic/paper")
    r = validate_materials(p, p.parent)
    assert r.missing == {"idea.md": [], "experiment_log.md": []} and r.has_results
    imp = load_imports(p)
    assert [len(imp["library"]), len(imp["must_cite"]), imp["warnings"]] == [2, 1, []]
    assert all(ref.abstract for ref in imp["library"]) and imp["must_cite"][0].key == "hu2020battery"
    assert "9.1% test error" in imp["library"][0].abstract  # the paraphrase keeps the number the scenario quotes
    assert main(["outline", "validate", "--paper", str(p)]) == 0
    assert json.loads(capsys.readouterr().out)["ok"]
