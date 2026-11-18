import json
import pytest
from po.review import *
from po.cli import main

OLD = {"Overall": 5, "Originality": 2, "Quality": 2, "Clarity": 2, "Significance": 2,
       "Soundness": 2, "Presentation": 2, "Contribution": 2, "Confidence": 4}

def test_decide():
    assert decide(OLD, {**OLD, "Overall": 6})["outcome"] == "ACCEPTED_SCORE_INCREASE"
    assert decide(OLD, {**OLD, "Overall": 4})["outcome"] == "REJECTED_SCORE_DECREASE"
    assert decide(OLD, {**OLD, "Clarity": 3, "Quality": 1})["outcome"] == "ACCEPTED_NEUTRAL_IMPROVEMENT"
    assert decide(OLD, {**OLD, "Clarity": 1})["outcome"] == "REJECTED_DEGRADATION"
    assert decide(OLD, {**OLD, "Confidence": 1})["outcome"] == "ACCEPTED_NEUTRAL_IMPROVEMENT"

def test_decide_fields():
    d = decide(OLD, {**OLD, "Clarity": 3, "Quality": 1})
    assert (d["total_gain"], d["total_drop"], d["deltas"]["Clarity"]) == (1, 1, 1)
    assert set(COMPARE_AXES) == set(SCORE_FIELDS) - {"Overall", "Confidence"}

def test_aggregate():
    rs = [{**OLD, "Overall": 5, "Clarity": 2}, {**OLD, "Overall": 6, "Clarity": 3}, {**OLD, "Overall": 6, "Clarity": "x"}]
    a = aggregate(rs, {"Summary": "meta"})
    assert (a["Overall"], a["Clarity"], a["Summary"]) == (6, 2, "meta")
    assert aggregate([{**OLD, "Overall": 5}, {**OLD, "Overall": 11}], None)["Overall"] == 5
    assert aggregate([{**OLD, "Summary": "first"}], None)["Summary"] == "first"

def test_parse_review():
    assert parse_review('THOUGHT:\nx\nREVIEW JSON:\n```json\n{"Overall": 7}\n```')["Overall"] == 7
    assert parse_review('```json\n{"a": 1}\n```\nREVIEW JSON:\n```json\n{"a": 2}\n```')["a"] == 2
    assert parse_review('x\n```json\n{"a": 3}\n```')["a"] == 3
    with pytest.raises(ValueError):
        parse_review("no json here")

PRE = "## Method\n\nTool para one.\n\nMy own words here.\n\nTool para three.\n"
def test_restore_paths():
    marked, orig = protect(PRE, ["My own words here."])
    assert "po:keep" in marked
    out, acts = restore(marked.replace("My own words here.", "Rewritten."), orig, marked)
    assert "My own words here." in out and acts[0]["action"] == "restored" and "po:keep" not in out
    out, acts = restore(PRE.replace("My own words here.", "My own words here!"), orig, marked)
    assert acts[0]["action"] == "restored-fuzzy"
    out, acts = restore("## Method\n\nTool para one.\n\nTool para three.\n", orig, marked)
    assert acts[0]["action"] == "reinserted" and out.index("Tool para one.") < out.index("My own words here.") < out.index("Tool para three.")
    out, acts = restore("## Other\n\nX.\n", orig, marked)
    assert acts[0]["action"] == "missing"

def test_restore_unchanged_and_section_end():
    marked, orig = protect(PRE, ["My own words here."])
    out, acts = restore(marked, orig, marked)
    assert acts[0]["action"] == "unchanged" and out == PRE
    first = "## Method\n\nMy own words here.\n\nTool para.\n\n## Next\n\nZ.\n"
    marked, orig = protect(first, ["My own words here."])
    out, acts = restore("## Method\n\nTool para.\n\n## Next\n\nZ.\n", orig, marked)
    assert acts[0]["action"] == "reinserted" and out.index("My own words") < out.index("## Next")

def test_protected_set_and_changes():
    assert protected_set(PRE, PRE.replace("My own words here.", "orig"), ["Gone para."]) == ["My own words here."]
    assert protected_set(PRE, None, ["My  own words here."]) == ["My own words here."]
    marked, orig = protect(PRE, ["My own words here."])
    assert changed_protected(marked.replace("My own words here.", "New."), orig) == [{"before": "My own words here.", "after": "New."}]

def test_render_review_md():
    md = render_review_md([{"version": 1, "overall_before": 5, "overall_after": 6, "outcome": "ACCEPTED_SCORE_INCREASE"}],
                          ["Add ablation on k", "Add ablation on k"], [], [], None)
    heads = ["## Review rounds", "## What changed", "## Experiments reviewers asked for",
             "## Suggestions for your edited paragraphs", "## Protected paragraphs", "## Check"]
    assert [md.index(h) for h in heads] == sorted(md.index(h) for h in heads)
    assert md.count("Add ablation on k") == 1

def test_cli_flow(tmp_path, capsys):
    paper = tmp_path / "paper"
    (paper / "reviews" / "v1").mkdir(parents=True)
    (paper / "drafts").mkdir()
    base = ["--paper", str(paper)]
    for i, o in ((1, 5), (2, 6)):
        (paper / "reviews/v1" / f"r{i}.md").write_text('REVIEW JSON:\n```json\n' + json.dumps({**OLD, "Overall": o}) + '\n```')
    assert main(["review", "aggregate", *base, "--version", "1"]) == 0
    assert json.loads((paper / "reviews/review_v1.json").read_text())["Overall"] == 6
    (paper / "reviews/v1/r3.md").write_text("garbage")
    assert main(["review", "aggregate", *base, "--version", "1"]) == 2
    assert "r3.md" in capsys.readouterr().err
    # protect / restore / changes: PRE's middle paragraph is a hand edit of the tool version
    from po.paper import save_version
    from po.state import get_protected
    (paper / "paper.md").write_text(PRE)
    save_version(paper, PRE.replace("My own words here.", "orig"), "tool")
    assert main(["review", "protect", *base, "--out", "drafts/marked_v1.md"]) == 0
    marked = (paper / "drafts/marked_v1.md").read_text()
    assert "<!-- po:keep 1 -->" in marked
    assert get_protected(paper) == ["My own words here."]
    assert json.loads((paper / "reviews/protected_v1.json").read_text()) == {"1": "My own words here."}
    cand = paper / "cand.md"
    cand.write_text(marked.replace("My own words here.", "Rewritten."))
    assert main(["review", "changes", *base, "--candidate", str(cand), "--map", "reviews/protected_v1.json"]) == 0
    assert "po:keep" not in cand.read_text() and "Rewritten." in cand.read_text()
    cand.write_text(marked.replace("My own words here.", "Rewritten."))
    assert main(["review", "restore", *base, "--candidate", str(cand), "--map", "reviews/protected_v1.json",
                 "--pre", "drafts/marked_v1.md"]) == 0
    assert cand.read_text() == PRE
    # decide + render
    (paper / "reviews/review_v2.json").write_text(json.dumps({**OLD, "Overall": 7}))
    assert main(["review", "decide", *base, "--old", str(paper / "reviews/review_v1.json"),
                 "--new", str(paper / "reviews/review_v2.json"), "--record", "1"]) == 0
    assert json.loads((paper / "reviews/rounds.json").read_text())[0]["outcome"] == "ACCEPTED_SCORE_INCREASE"
    (paper / "reviews/worklog_v1.json").write_text(json.dumps({
        "addressed_weaknesses": ["w"], "integrated_answers": [], "actions_taken": ["Tightened intro"],
        "experiments_requested": ["Ablate k"], "suggestions_for_protected": ["Cite X"]}))
    (paper / "review.md").write_text("old\n\n## Check\n\nAll good.\n")
    assert main(["review", "render", *base]) == 0
    md = (paper / "review.md").read_text()
    assert "Tightened intro" in md and "Ablate k" in md and "Cite X" in md and "All good." in md


def test_reinsert_stays_in_own_section():
    pre = "## Intro\n\nA para.\n\n## Method\n\nMy own words.\n\nTool para.\n"
    marked, orig = protect(pre, ["My own words."])
    out, acts = restore("## Intro\n\nA para.\n\n## Method\n\nTool para.\n", orig, marked)
    assert acts[0]["action"] == "reinserted"
    assert out.index("## Method") < out.index("My own words.") < out.index("Tool para.")
    assert out.index("A para.") < out.index("## Method")
    assert "\n\n\n" not in out


def test_aggregate_coerces_like_original():
    rs = [{**OLD, "Clarity": "3"}, {**OLD, "Clarity": 3.0}, {**OLD, "Clarity": True}, {**OLD, "Clarity": "9"}]
    assert aggregate(rs, None)["Clarity"] == 3


def test_decide_never_raises():
    d = decide({"Overall": "x", "Clarity": None}, {"Clarity": "bad", "Quality": 2})
    assert d["outcome"] == "ACCEPTED_NEUTRAL_IMPROVEMENT" and d["deltas"]["Quality"] == 2


def test_duplicate_protected_paragraphs():
    md = "## A\n\nSame.\n\nTool.\n\n## B\n\nSame.\n"
    marked, orig = protect(md, ["Same."])
    assert marked.count("<!-- po:keep") == 2 and len(orig) == 2 and set(orig.values()) == {"Same."}
    out, acts = restore("## A\n\nTool.\n\n## B\n\nOther.\n", orig, marked)
    assert len(acts) == 2
    assert out.count("Same.") == 2 and "po:keep" not in out
    assert out.index("Same.") < out.index("Tool.") and out.index("## B") < out.rindex("Same.")


def test_changed_protected_reports_deleted():
    marked, orig = protect(PRE, ["My own words here."])
    gone = KEEP_RE.sub("", marked)
    assert changed_protected(gone, orig) == [{"before": "My own words here.", "after": None}]


def test_parse_review_uppercase_fence():
    assert parse_review('REVIEW JSON:\n```JSON\n{"a": 1}\n```')["a"] == 1


def test_cli_edge_cases(tmp_path, capsys):
    paper = tmp_path / "paper"
    paper.mkdir()
    base = ["--paper", str(paper)]
    assert main(["review", "protect", *base, "--out", "drafts/marked_v1.md"]) == 2
    (paper / "o.json").write_text('{"Overall": "x"}')
    (paper / "n.json").write_text('[1]')
    assert main(["review", "decide", *base, "--old", "o.json", "--new", "n.json"]) == 2
    (paper / "n.json").write_text('{"Clarity": "z"}')
    assert main(["review", "decide", *base, "--old", "o.json", "--new", "n.json"]) == 0
    assert "Traceback" not in capsys.readouterr().err
    # restorations keyed by version: rerun overwrites
    (paper / "paper.md").write_text(PRE)
    main(["review", "protect", *base, "--out", "drafts/marked_v1.md"])
    (paper / "reviews/protected_v1.json").write_text('{"1": "My own words here."}')
    (paper / "c.md").write_text("## Method\n\nTool para one.\n")
    for _ in range(2):
        (paper / "c.md").write_text("## Method\n\nTool para one.\n")
        assert main(["review", "restore", *base, "--candidate", "c.md", "--map", "reviews/protected_v1.json",
                     "--pre", "paper.md"]) == 0
    assert list(json.loads((paper / "reviews/restorations.json").read_text())) == ["v1"]
    assert len(json.loads((paper / "reviews/restorations.json").read_text())["v1"]) == 1
    assert main(["review", "render", *base]) == 0
    assert "reinserted" in (paper / "review.md").read_text()
