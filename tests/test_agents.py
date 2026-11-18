from pathlib import Path

import pytest

from po.frontmatter import parse_frontmatter

PLUGIN = Path("plugins/paper-orchestra")
GROUND_RULES = (PLUGIN / "prompts/ground-rules.md").read_text(encoding="utf-8").strip()

AGENTS = {"materials-drafter": dict(model="inherit", tools="Read, Glob, Grep, Write, Bash",
          rules=["M1", "M2", "M3", "M4", "M5", "M6", "M7"], ground_rules=True, ported=False)}


@pytest.mark.parametrize("name", sorted(AGENTS))
def test_agent(name):
    spec = AGENTS[name]
    path = PLUGIN / "agents" / f"{name}.md"
    assert path.is_file()
    meta, body = parse_frontmatter(path.read_text(encoding="utf-8"))
    assert set(meta) == {"name", "description", "model", "tools"}
    assert meta["name"] == path.stem
    assert meta["model"] == spec["model"]
    assert meta["tools"] == spec["tools"]
    for rule in spec["rules"]:
        assert f"[{rule}]" in body, rule
    if spec["ground_rules"]:
        assert GROUND_RULES in body
    if spec["ported"]:
        assert "Adapted from PaperOrchestra (Apache-2.0)" in body
