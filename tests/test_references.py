from po.references import cited_keys, update_references
from po.library import LibraryEntry

def E(key, n_auth=2):
    return LibraryEntry(key, f"Title {key}", [f"A{i} B" for i in range(n_auth)], "Venue", 2020, None, None,
                        "openalex", False, "Introduction", "", "10.1/" + key, {}, None, None, None, None, 0)

def test_cited_keys():
    assert cited_keys("x [@b; @a, p. 3] then [@b] `[@code]`") == ["b", "a"]

def test_update_references_numbered_and_appendix():
    md = "## Intro\n\n[@b] and [@a].\n\n## References\n\nold\n\n## Appendix\n\nZ.\n"
    out = update_references(md, {"a": E("a", 8), "b": E("b")}, "numbered")
    assert out.index("[@b] A0 B") < out.index("[@a] A0 B") < out.index("## Appendix")
    assert "old" not in out and "et al." in out and "https://doi.org/10.1/a" in out

def test_author_year_alphabetical_missing_skipped_no_appendix():
    md = "## Intro\n\n[@b] [@a] [@gone].\n"
    out = update_references(md, {"a": E("a"), "b": E("b")}, "author-year")
    assert out.index("[@a]") < out.index("[@b] A0") and "gone]" not in out.split("## References")[1]
    assert out.rstrip().endswith("https://doi.org/10.1/b")
