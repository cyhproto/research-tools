import pytest
from po.paper import *
from po.style import load_style
from po.settings import PLUGIN_DIR
ML = load_style(PLUGIN_DIR / "styles/ml-conference.md")
MD = "# Title\n\nLead.\n\n## 1. Introduction\n\nA.\n\n## Related Work\n\nB.\n\n```python\n## not a heading\n```\n\n## Method\n\nC.\n"

def test_split_roundtrip():
    pre, secs = split_sections(MD)
    assert [s.name for s in secs] == ["Introduction", "Related Work", "Method"] and assemble(pre, secs) == MD

def test_owner_of():
    assert [owner_of(n, ML) for n in ("Introduction", "Method", "References")] == ["literature-writer", "section-writer", "script"]

def test_replace_only_owner_sections():
    new = "## Introduction\n\nA2.\n\n## Method\n\nX.\n"
    merged, warns = replace_owned(MD, new, "literature-writer", ML, tool_md=MD)
    assert "A2." in merged and "C." in merged and "X." not in merged and any("Method" in w for w in warns)

def test_replace_owned_refuses_hand_edited_sections():
    current = MD.replace("A.", "A edited by me.")
    with pytest.raises(HandEditConflict) as e:
        replace_owned(current, "## Introduction\n\nNew.\n", "literature-writer", ML, tool_md=MD)
    assert e.value.sections == ["Introduction"]
    merged, _ = replace_owned(current, "## Introduction\n\nNew.\n", "literature-writer", ML, tool_md=MD, force_sections=["Introduction"])
    assert "New." in merged
    assert hand_edited_paragraphs(current, MD) == ["A edited by me."]

def test_insert_missing_in_style_order():
    cur = "# T\n\n## Introduction\n\nA.\n\n## Method\n\nC.\n"
    merged, _ = replace_owned(cur, "## Related Work\n\nB.\n", "literature-writer", ML)
    assert merged.index("## Related Work") < merged.index("## Method")

def test_paragraphs_keep_fence_and_table():
    md = "# T\n\nP1\nline\n\n```\na\n\nb\n```\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n## S\n\nP2\n"
    assert paragraphs(md) == ["P1\nline", "```\na\n\nb\n```", "| a | b |\n|---|---|\n| 1 | 2 |", "P2"]

def test_hand_edits_ignore_references_and_whitespace():
    tool = "## Introduction\n\nA  b.\n\n## References\n\n- x\n"
    cur = "## Introduction\n\nA b.\n\n## References\n\n- y\n"
    assert hand_edited_paragraphs(cur, tool) == []
    assert sections_with_hand_edits(cur.replace("A b.", "Z."), tool) == ["Introduction"]


def test_cli_replace_conflict_edits_and_versions(tmp_path, capsys):
    import json
    from po.cli import main
    paper = tmp_path / "paper"
    paper.mkdir()
    src = tmp_path / "new.md"
    src.write_text("# T\n\n## Introduction\n\nA.\n\n## Method\n\nC.\n")
    base = ["--paper", str(paper)]
    assert main(["paper", "replace", *base, "--owner", "section-writer", "--from", str(src)]) == 0
    assert (paper / "drafts/v1.md").is_file() and "A." not in (paper / "drafts/v1.md").read_text()
    capsys.readouterr()
    (paper / "paper.md").write_text((paper / "paper.md").read_text().replace("C.", "C mine."))
    assert main(["paper", "edits", *base]) == 0
    assert json.loads(capsys.readouterr().out) == {"sections": ["Method"], "paragraphs": 1}
    src.write_text("## Method\n\nNew.\n")
    assert main(["paper", "replace", *base, "--owner", "section-writer", "--from", str(src)]) == 1
    assert json.loads(capsys.readouterr().out) == {"conflict": ["Method"]}
    assert main(["paper", "replace", *base, "--owner", "section-writer", "--from", str(src), "--force", "Method"]) == 0
    assert "New." in (paper / "paper.md").read_text()
