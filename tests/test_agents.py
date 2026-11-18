from pathlib import Path

import pytest

from po.frontmatter import parse_frontmatter

PLUGIN = Path("plugins/paper-orchestra")
GROUND_RULES = (PLUGIN / "prompts/ground-rules.md").read_text(encoding="utf-8").strip()

AGENTS = {"materials-drafter": dict(model="inherit", tools="Read, Glob, Grep, Write, Bash",
          rules=["M1", "M2", "M3", "M4", "M5", "M6", "M7"], ground_rules=True, ported=False),
          "outline-planner": dict(model="inherit", tools="Read, Write",
          rules=[f"O{i}" for i in range(1, 11)], ground_rules=True, ported=True),
          "literature-scout": dict(model="sonnet", tools="WebSearch, WebFetch, Read, Write",
          rules=[f"S{i}" for i in range(1, 8)], ground_rules=False, ported=True),
          "literature-writer": dict(model="inherit", tools="Read, Write",
          rules=[f"L{i}" for i in range(1, 8)], ground_rules=True, ported=True),
          "figure-maker": dict(model="inherit", tools="Read, Write, Edit, Bash",
          rules=[f"F{i}" for i in range(1, 9)], ground_rules=True, ported=True),
          "figure-critic": dict(model="sonnet", tools="Read, Write",
          rules=[f"C{i}" for i in range(1, 9)], ground_rules=False, ported=True),
          "section-writer": dict(model="inherit", tools="Read, Write",
          rules=[f"W{i}" for i in range(1, 12)], ground_rules=True, ported=True),
          "reviewer": dict(model="inherit", tools="Read, Write",
          rules=[f"V{i}" for i in range(1, 8)], ground_rules=False, ported=True),
          "meta-reviewer": dict(model="inherit", tools="Read, Write",
          rules=[f"A{i}" for i in range(1, 4)], ground_rules=False, ported=True),
          "reviser": dict(model="inherit", tools="Read, Write",
          rules=[f"X{i}" for i in range(1, 11)], ground_rules=True, ported=True),
          "checker": dict(model="inherit", tools="Read, Write",
          rules=[f"K{i}" for i in range(1, 5)], ground_rules=False, ported=False)}


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


def test_reviewer_has_original_top_rubric():
    text = (PLUGIN / "agents/reviewer.md").read_text(encoding="utf-8")
    assert ("This study is among the top 2% of all papers. It is one of the most thorough I have seen. "
            "It changed my thinking on this topic. I would fight for it to be accepted") in text
