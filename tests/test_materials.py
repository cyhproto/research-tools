from po.materials import validate_materials
from po.cli import main

IDEA = "## Problem Statement\nx\n## Core Hypothesis\nx\n## Proposed Methodology\nx\n## Expected Contribution\nx\n"


def write(tmp_path, log, idea=IDEA):
    m = tmp_path / "paper/materials"; m.mkdir(parents=True)
    (m / "idea.md").write_text(idea); (m / "experiment_log.md").write_text(log); return tmp_path / "paper"


def test_complete(tmp_path):
    p = write(tmp_path, "## 1. Experimental Setup\nx\n## 2. Raw Numeric Data\nacc 87.3 [manual: x]\n## 3. Qualitative Observations\nx\n")
    r = validate_materials(p, tmp_path)
    assert r.missing == {"idea.md": [], "experiment_log.md": []} and r.has_results


def test_no_results_exit_2(tmp_path):
    p = write(tmp_path, "## Experimental Setup\nx\n## Raw Numeric Data\n\n## Qualitative Observations\nx\n")
    assert not validate_materials(p, tmp_path).has_results
    assert main(["materials", "validate", "--paper", str(p)]) == 2


def test_figures_captions(tmp_path):
    p = write(tmp_path, "## Experimental Setup\n## Raw Numeric Data\n12.5 [manual: x]\n## Qualitative Observations\n")
    f = p / "materials/figures"; f.mkdir(); (f / "fig.png").write_bytes(b"x"); (f / "captions.md").write_text("")
    assert validate_materials(p, tmp_path).captions_missing == ["fig.png"]


LOG_OK = "## Experimental Setup\nx\n## Raw Numeric Data\n12.5 [manual: x]\n## Qualitative Observations\nx\n"


def test_heading_prefix_match(tmp_path):
    idea = IDEA.replace("## Proposed Methodology", "## 2.3 Proposed Methodology (High-Level Technical Approach)")
    p = write(tmp_path, LOG_OK, idea)
    assert validate_materials(p, tmp_path).missing["idea.md"] == []


def test_missing_heading_exit_1(tmp_path):
    p = write(tmp_path, LOG_OK, "## Problem Statement\nx\n")
    r = validate_materials(p, tmp_path)
    assert r.missing["idea.md"] == ["Core Hypothesis", "Proposed Methodology", "Expected Contribution"]
    assert main(["materials", "validate", "--paper", str(p)]) == 1


def test_ok_exit_0_and_captions(tmp_path):
    p = write(tmp_path, LOG_OK)
    f = p / "materials/figures"; f.mkdir(); (f / "a.svg").write_bytes(b"x")
    (f / "captions.md").write_text("- a.svg: A caption\n")
    r = validate_materials(p, tmp_path)
    assert r.figures == ["a.svg"] and r.captions_missing == []
    assert main(["materials", "validate", "--paper", str(p)]) == 0


def test_mismatch_exit_1(tmp_path):
    (tmp_path / "r.json").write_text('{"a": 50.0}')
    log = LOG_OK.replace("12.5 [manual: x]", "12.5 [src: r.json | path=a]")
    p = write(tmp_path, log)
    r = validate_materials(p, tmp_path)
    assert r.verify["mismatch"] == 1
    assert main(["materials", "validate", "--paper", str(p)]) == 1


def test_non_utf8_log_exit_2(tmp_path):
    p = write(tmp_path, LOG_OK)
    (p / "materials/experiment_log.md").write_bytes(b"\xff\xfe\x00bad")
    assert validate_materials(p, tmp_path).unreadable_log
    assert main(["materials", "validate", "--paper", str(p)]) == 2
