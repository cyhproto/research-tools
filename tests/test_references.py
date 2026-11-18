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


def test_reference_line_missing_fields_and_doi_url():
    from po.references import render_references
    e = E("a")
    e.year, e.venue, e.doi = None, None, None
    line = render_references({"a": e}, ["a"], "numbered").splitlines()[-1]
    assert line == "- [@a] A0 B, A1 B. (n.d.). Title a."
    e2 = E("b")
    e2.doi = "https://doi.org/10.5/x"
    assert render_references({"b": e2}, ["b"], "numbered").endswith("*Venue*. https://doi.org/10.5/x\n")
    e2.doi = "doi:10.5/x"
    assert "doi.org/10.5/x" in render_references({"b": e2}, ["b"], "numbered")

def test_cited_keys_skip_tilde_fence_and_keep_crlf():
    assert cited_keys("[@a]\n\n~~~\n[@b]\n~~~\n\n[@c]") == ["a", "c"]
    md = "## Intro\r\n\r\n[@a].\r\n"
    out = update_references(md, {"a": E("a")}, "numbered")
    assert out.startswith(md) and "\n" not in out.replace("\r\n", "")
