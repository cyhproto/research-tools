import pytest
from po.style import find_style, load_style, StyleNotFound
from po.settings import PLUGIN_DIR

def test_lookup_order(tmp_path):
    paper, user, plugin = tmp_path / "paper", tmp_path / "user", tmp_path / "plugin"
    for d in (paper, user, plugin / "styles"): d.mkdir(parents=True)
    (plugin / "styles/ml-conference.md").write_text("---\nname: ml-conference\n---\n")
    assert find_style("ml-conference", paper, user, plugin) == plugin / "styles/ml-conference.md"
    (user / "ml-conference.md").write_text("---\nname: mine\n---\n")
    assert find_style("ml-conference", paper, user, plugin) == user / "ml-conference.md"
    (paper / "style.md").write_text("---\nname: project\n---\n")
    assert find_style("anything", paper, user, plugin) == paper / "style.md"
    with pytest.raises(StyleNotFound, match="nope"): find_style("nope", tmp_path / "none", user, plugin)

def test_shipped_styles():
    ml = load_style(PLUGIN_DIR / "styles/ml-conference.md")
    assert ml.sections == ["Abstract", "Introduction", "Related Work", "Method", "Experiments", "Conclusion", "Limitations"]
    assert ml.literature_sections == ["Introduction", "Related Work"] and ml.optional_sections == ["Appendix"]
    assert (ml.length_words, ml.blind_review, ml.citation_style) == ((5500, 7500), True, "author-year")
    j = load_style(PLUGIN_DIR / "styles/journal.md")
    assert (j.length_words, j.blind_review, j.citation_style) == ((6000, 10000), False, "numbered")
    assert j.required_statements == ["Data and code availability", "Declaration of competing interests"]


# --- T2: a malformed style.md is a clear error that names the file ----------------------------
@pytest.mark.parametrize("front, problem", [
    (None, "front matter"),
    ("name: x\nlength_words: [1, 2]\n", "sections"),
    ("name: x\nsections: Abstract\nlength_words: [1, 2]\n", "sections"),
    ("name: x\nsections: [A]\n", "length_words"),
    ("name: x\nsections: [A]\nlength_words: 5000\n", "length_words"),
    ("name: x\nsections: [A]\nlength_words: [5000]\n", "length_words"),
    ("name: x\nsections: [A]\nlength_words: [a, b]\n", "length_words"),
    ("name: x\nsections: [A]\nlength_words: [9, 2]\n", "length_words"),
    ("name: x\nsections: [A]\nlength_words: [1, 2]\nliterature_sections: Introduction\n", "literature_sections"),
    ("name: x\nsections: [A]\nlength_words: [1, 2]\nblind_review: maybe\n", "blind_review"),
    ("name: x\nsections: [A]\nlength_words: [1, 2]\ncitation_style: author_year\n", "citation_style"),
])
def test_malformed_style_is_a_clear_error(tmp_path, front, problem):
    from po.style import StyleError
    f = tmp_path / "style.md"
    f.write_text("# a style without front matter\n" if front is None else f"---\n{front}---\n# body\n")
    with pytest.raises(StyleError) as e:
        load_style(f)
    assert str(f) in str(e.value) and problem in str(e.value)


def test_malformed_style_stops_commands_with_exit_2(tmp_path, capsys):
    import shutil
    from po.cli import main
    paper = tmp_path / "paper"
    paper.mkdir()
    (paper / "style.md").write_text("---\nsections: [Abstract]\nlength_words: 5000\n---\n")
    (paper / "paper.md").write_text("# T\n\n## Abstract\n\nText.\n")
    shutil.copy("tests/fixtures/outline_valid.json", paper / "outline.json")
    for cmd in (["settings", "init"], ["paper", "references"], ["outline", "validate"], ["check", "run"]):
        assert main([*cmd, "--paper", str(paper)]) == 2, cmd
        err = capsys.readouterr().err
        assert str(paper / "style.md") in err and "length_words" in err and "Traceback" not in err, cmd
        assert err.startswith("StyleError: ") == (cmd[0] == "check"), cmd  # check run: the catch-all
    assert not (paper / "settings.md").exists()
