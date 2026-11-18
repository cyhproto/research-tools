# tests/test_skill.py
import re
from pathlib import Path
from po.cli import build_parser
from po.frontmatter import parse_frontmatter
SKILL = Path("plugins/paper-orchestra/skills/paper-orchestra/SKILL.md")

def test_frontmatter():
    fm, body = parse_frontmatter(SKILL.read_text())
    assert fm["name"] == "paper-orchestra" and "/paper-orchestra" in fm["description"]

def test_every_agent_dispatched():
    body = SKILL.read_text()
    for f in Path("plugins/paper-orchestra/agents").glob("*.md"):
        assert f"paper-orchestra:{f.stem}" in body, f.stem

def test_every_po_command_exists():
    groups = build_parser()._subparsers._group_actions[0].choices
    for g, c in set(re.findall(r"\$PO ([a-z-]+)(?: ([a-z-]+))?", SKILL.read_text())):
        assert g in groups, g
        if c and g not in ("doctor", "plot-run", "version"):
            assert c in groups[g]._subparsers._group_actions[0].choices, f"{g} {c}"

def test_required_phrases():
    body = SKILL.read_text()
    for s in ["gather", "outline", "lit-review", "figures", "write", "review", "check", "status",
              "4 agents", "Run /paper-orchestra again to continue", "--hand-edits", "--profile", "--only"]:
        assert s in body, s
