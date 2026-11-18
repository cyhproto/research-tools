# tests/test_fixtures.py
from pathlib import Path
from po.materials import validate_materials

def test_tsam_materials_validate():
    p = Path("tests/fixtures/tsam/paper")
    r = validate_materials(p, p.parent)
    assert r.missing == {"idea.md": [], "experiment_log.md": []} and r.has_results
    assert r.figures == ["tsam_overview.png"] and r.captions_missing == []
