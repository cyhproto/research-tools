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


# --- fix round 1 -------------------------------------------------------------
from po.cli import main as _main


@pytest.mark.parametrize("md", [
    "# T\r\n\r\n## Introduction\r\n\r\nA.\r\n\r\n## Method\r\n\r\nC.\r\n",
    "# T\n\n## Method\n\nno trailing newline",
    "",
    "~~~\n## in tilde fence\n~~~\n\n## A\n\nx\n```\n## unclosed\n",
])
def test_roundtrip_edge_cases(md):
    assert assemble(*split_sections(md)) == md

def test_fence_rules():
    md = "## A\n\n```\n~~~\n## still inside\n```\n\n## B\n\nb\n"
    assert [s.name for s in split_sections(md)[1]] == ["A", "B"]
    assert [s.name for s in split_sections("## A\n\n~~~\n## in\n~~~\n\n## B\n")[1]] == ["A", "B"]
    assert [s.name for s in split_sections("## A\n\n```\n## unclosed\n")[1]] == ["A"]
    assert [s.name for s in split_sections("## A\n\n````\n```\n## in\n````\n\n## B\n")[1]] == ["A", "B"]

def test_h3_stays_in_section():
    assert [s.name for s in split_sections("## A\n\n### Sub\n\nx\n\n## B\n")[1]] == ["A", "B"]

def test_duplicate_section_names_first_replaced():
    cur = "## Method\n\nfirst\n\n## Method\n\nsecond\n"
    merged, _ = replace_owned(cur, "## Method\n\nNEW\n", "section-writer", ML, tool_md=cur)
    assert "NEW" in merged and "second" in merged and "first" not in merged

def test_title_conflict_and_only():
    cur = MD.replace("Lead.", "Lead mine.")
    new = "# New title\n\nNew lead.\n\n## Method\n\nX.\n"
    with pytest.raises(HandEditConflict) as e:
        replace_owned(cur, new, "section-writer", ML, tool_md=MD)
    assert e.value.sections == ["Title"]
    merged, _ = replace_owned(cur, new, "section-writer", ML, tool_md=MD, only=["Method"])
    assert "Lead mine." in merged and "X." in merged
    merged, _ = replace_owned(cur, new, "section-writer", ML, tool_md=MD, force_sections=["Title"])
    assert "New lead." in merged and "Lead mine." not in merged

def test_preamble_ignored_for_other_owner_with_warning():
    merged, warns = replace_owned(MD, "# X\n\n## Introduction\n\nA2.\n", "literature-writer", ML, tool_md=MD)
    assert "# Title" in merged and any("title" in w.lower() for w in warns)

def test_save_version_numbering(tmp_path):
    (tmp_path / "drafts").mkdir()
    (tmp_path / "drafts/v1.md").write_text("a")
    (tmp_path / "drafts/v4-user.md").write_text("b")
    p = save_version(tmp_path, "x", "tool")
    assert p.name == "v5.md"
    u = save_version(tmp_path, "y", "user")
    assert u.name == "v6-user.md"
    from po.state import last_tool_version
    assert last_tool_version(tmp_path).name == "v5.md"

def test_insert_after_nearest_preceding_style_section():
    cur = "## Introduction\n\nA.\n\n## Notes\n\nN.\n\n## Method\n\nC.\n"
    merged, _ = replace_owned(cur, "## Experiments\n\nE.\n", "section-writer", ML)
    names = [s.name for s in split_sections(merged)[1]]
    assert names == ["Introduction", "Notes", "Method", "Experiments"]

def test_insert_before_first_following_and_before_references():
    cur = "## Method\n\nC.\n\n## References\n\n- r\n"
    merged, _ = replace_owned(cur, "## Abstract\n\nZ.\n\n## Limitations\n\nL.\n", "section-writer", ML)
    assert [s.name for s in split_sections(merged)[1]] == ["Abstract", "Method", "Limitations", "References"]

def test_untouched_sections_byte_identical_and_crlf_kept():
    cur = "# T\r\n\r\n## Introduction\r\n\r\nA.\r\n\r\n\r\n\r\n## Method\r\n\r\nC.\r\n"
    merged, _ = replace_owned(cur, "## Introduction\n\nNew.\n\nmore\n", "literature-writer", ML)
    assert merged.endswith("## Method\r\n\r\nC.\r\n") and "\n" not in merged.replace("\r\n", "")
    assert "New.\r\n\r\nmore\r\n\r\n## Method" in merged
    cur2 = "## Introduction\n\nA.\n\n\n\n## Method\n\nC.\n\n\n"
    merged2, _ = replace_owned(cur2, "## Introduction\n\nB.\n", "literature-writer", ML)
    assert merged2.endswith("## Method\n\nC.\n\n\n")

def test_forced_flow_protection_across_replaces(tmp_path, capsys):
    import json
    paper = tmp_path / "paper"
    paper.mkdir()
    src = tmp_path / "n.md"
    base = ["--paper", str(paper)]
    src.write_text("# T\n\n## Introduction\n\nA.\n\n## Method\n\nC.\n")
    assert _main(["paper", "replace", *base, "--owner", "section-writer", "--from", str(src)]) == 0
    (paper / "paper.md").write_text((paper / "paper.md").read_text().replace("C.", "C mine."))
    src.write_text("## Introduction\n\nA2.\n")
    assert _main(["paper", "replace", *base, "--owner", "literature-writer", "--from", str(src)]) == 0
    capsys.readouterr()
    assert _main(["paper", "edits", *base]) == 0
    assert json.loads(capsys.readouterr().out)["sections"] == ["Method"]
    src.write_text("## Method\n\nNEW\n")
    assert _main(["paper", "replace", *base, "--owner", "section-writer", "--from", str(src)]) == 1
    assert json.loads(capsys.readouterr().out) == {"conflict": ["Method"]}
    assert _main(["paper", "replace", *base, "--owner", "section-writer", "--from", str(src), "--force", "Method"]) == 0
    capsys.readouterr()
    from po.state import get_protected
    assert get_protected(paper) == []
    src.write_text("## Method\n\nNEWER\n")
    assert _main(["paper", "replace", *base, "--owner", "section-writer", "--from", str(src)]) == 0

def test_edits_without_style_file(tmp_path, capsys):
    (tmp_path / "settings.md").write_text("---\nstyle: no-such-style\n---\n")
    assert _main(["paper", "edits", "--paper", str(tmp_path)]) == 0


# --- P13: paper accept -------------------------------------------------------
ACCEPT_TOOL = ("# T\n\n## Introduction\n\nIntro para.\n\n## Method\n\nMethod one.\n\nMethod two.\n\n"
               "## Experiments\n\nExp one.\n")


def test_accept_records_user_edits_not_reviser_text(tmp_path, capsys):
    import json
    from po.state import get_protected, last_tool_version
    paper = tmp_path / "paper"
    paper.mkdir()
    base = ["--paper", str(paper)]
    save_version(paper, ACCEPT_TOOL, "tool")
    (paper / "paper.md").write_text(ACCEPT_TOOL.replace("Exp one.", "Exp one, in my own words."))
    # keep mode: protect, the reviser rewrites Method, restore
    assert _main(["review", "protect", *base, "--out", str(paper / "drafts/marked_v0.md")]) == 0
    marked = (paper / "drafts/marked_v0.md").read_text()
    cand = paper / "drafts/candidate_v1.md"
    cand.write_text(marked.replace("Method two.", "Method two, revised.\n\nA new reviser paragraph."))
    assert _main(["review", "restore", *base, "--candidate", str(cand), "--map",
                  str(paper / "reviews/protected_v0.json"), "--pre", str(paper / "drafts/marked_v0.md")]) == 0
    capsys.readouterr()
    assert _main(["paper", "accept", *base, "--from", str(cand)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert (paper / "paper.md").read_text() == cand.read_text()
    assert "Exp one, in my own words." in (paper / "paper.md").read_text()
    assert out["version"].endswith("v2.md") and last_tool_version(paper).read_text() == cand.read_text()
    assert get_protected(paper) == ["Exp one, in my own words."]
    assert _main(["paper", "edits", *base]) == 0
    assert json.loads(capsys.readouterr().out)["sections"] == ["Experiments"]
    # a later write of the reviser-changed section is no conflict; the user's section still is
    new = tmp_path / "w.md"
    new.write_text("## Method\n\nMethod rewritten by a later write.\n")
    assert _main(["paper", "replace", *base, "--owner", "section-writer", "--from", str(new)]) == 0
    assert "Method rewritten by a later write." in (paper / "paper.md").read_text()
    capsys.readouterr()
    new.write_text("## Experiments\n\nExp rewritten.\n")
    assert _main(["paper", "replace", *base, "--owner", "section-writer", "--from", str(new)]) == 1
    assert json.loads(capsys.readouterr().out) == {"conflict": ["Experiments"]}


def test_accept_missing_file(tmp_path, capsys):
    (tmp_path / "paper.md").write_text(ACCEPT_TOOL)
    assert _main(["paper", "accept", "--paper", str(tmp_path), "--from", str(tmp_path / "nope.md")]) == 2
    assert "not found" in capsys.readouterr().err
    assert (tmp_path / "paper.md").read_text() == ACCEPT_TOOL


# --- fix round 1: accept refuses late hand edits; references --file ----------
def _accept_setup(tmp_path):
    paper = tmp_path / "paper"
    paper.mkdir()
    save_version(paper, ACCEPT_TOOL, "tool")
    (paper / "paper.md").write_text(ACCEPT_TOOL.replace("Exp one.", "Exp one, in my own words."))
    base = ["--paper", str(paper)]
    assert _main(["review", "protect", *base, "--out", str(paper / "drafts/marked_v0.md")]) == 0
    return paper, base, (paper / "drafts/marked_v0.md").read_text(), paper / "drafts/candidate_v1.md"


def test_accept_refuses_edits_made_after_protect(tmp_path, capsys):
    import json
    from pathlib import Path
    paper, base, marked, cand = _accept_setup(tmp_path)
    cand.write_text(marked.replace("Method two.", "Method two, revised."))
    assert _main(["review", "restore", *base, "--candidate", str(cand), "--map",
                  str(paper / "reviews/protected_v0.json"), "--pre", str(paper / "drafts/marked_v0.md")]) == 0
    late = (paper / "paper.md").read_text().replace("Intro para.", "Intro para, edited during the review.")
    (paper / "paper.md").write_text(late)
    capsys.readouterr()
    assert _main(["paper", "accept", *base, "--from", str(cand)]) == 1
    out = json.loads(capsys.readouterr().out)
    assert out["hand_edits_after_review"] == ["Intro para, edited during the review."]
    assert Path(out["saved"]).read_text() == late and (paper / "paper.md").read_text() == late
    assert _main(["paper", "accept", *base, "--from", str(cand), "--force"]) == 0
    assert (paper / "paper.md").read_text() == cand.read_text()
    assert [p.name for p in (paper / "drafts").glob("v*-user.md")] == [Path(out["saved"]).name]


def test_accept_revise_mode_rewritten_user_paragraph(tmp_path, capsys):
    from po.state import get_protected
    paper, base, marked, cand = _accept_setup(tmp_path)
    cand.write_text(marked.replace("Exp one, in my own words.", "Exp one, reworded by the reviser."))
    assert _main(["review", "changes", *base, "--candidate", str(cand), "--map",
                  str(paper / "reviews/protected_v0.json")]) == 0
    assert _main(["paper", "accept", *base, "--from", str(cand)]) == 0
    assert (paper / "paper.md").read_text() == cand.read_text() and "po:keep" not in cand.read_text()
    assert get_protected(paper) == []


def test_references_file_rewrites_only_that_file(tmp_path, capsys):
    import dataclasses
    import json
    from po.library import LibraryEntry
    paper = tmp_path / "paper"
    (paper / "references").mkdir(parents=True)
    e = LibraryEntry("Kim2024Own", "Own Title", ["J. Kim"], "Venue", 2024, None, None, "openalex", False,
                     "Introduction", "")
    (paper / "references/library.json").write_text(json.dumps([dataclasses.asdict(e)]))
    (paper / "paper.md").write_text("# T\n\n## Method\n\nNo citations.\n")
    cand = paper / "drafts/candidate_v1.md"
    cand.parent.mkdir()
    cand.write_text("# T\n\n## Method\n\nAs shown [@Kim2024Own].\n\n## References\n\n- stale entry\n")
    assert _main(["paper", "references", "--paper", str(paper), "--file", str(cand)]) == 0
    assert "- [@Kim2024Own] J. Kim." in cand.read_text() and "stale entry" not in cand.read_text()
    assert (paper / "paper.md").read_text() == "# T\n\n## Method\n\nNo citations.\n"
    capsys.readouterr()
    assert _main(["paper", "references", "--paper", str(paper), "--file", str(paper / "nope.md")]) == 2
    assert "not found" in capsys.readouterr().err
