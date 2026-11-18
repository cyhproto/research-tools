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
