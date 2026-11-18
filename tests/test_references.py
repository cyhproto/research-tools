from po.references import cited_keys, update_references
from po.library import LibraryEntry

def E(key, n_auth=2):
    return LibraryEntry(key, f"Title {key}", [f"A{i} B" for i in range(n_auth)], "Venue", 2020, None, None,
                        "openalex", False, "Introduction", "", "10.1/" + key, {}, None, None, None, None, 0)

def test_cited_keys():
    assert cited_keys("x [@b; @a, p. 3] then [@b] `[@code]`") == ["b", "a"]

def test_update_references_numbered_and_appendix():
    md = "## Intro\n\n[@b] and [@a].\n\n## References\n\n- [@zz] Old, stale entry.\n\n## Appendix\n\nZ.\n"
    out = update_references(md, {"a": E("a", 8), "b": E("b")}, "numbered")
    assert out.index("[@b] A0 B") < out.index("[@a] A0 B") < out.index("## Appendix")
    assert "stale" not in out and "[@zz]" not in out and "et al." in out and "https://doi.org/10.1/a" in out

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


def test_text_under_references_is_kept_after_the_list():
    from po.references import kept_reference_lines
    md = ("## Intro\n\n[@b].\n\n## References\n\n- [@zz] Old entry.\nMy note on [@a] with 91.7.\nIts second line.\n"
          "- [@b] Old b.\n\nAnother note.\n\n## Appendix\n\nZ.\n")
    assert kept_reference_lines(md) == ["My note on [@a] with 91.7.", "Its second line.", "Another note."]
    assert cited_keys(md) == ["b", "a"]  # a citation in kept text counts; entry lines do not
    out = update_references(md, {"a": E("a"), "b": E("b")}, "numbered")
    refs = out.split("## References")[1].split("## Appendix")[0]
    assert refs.index("- [@b] A0 B") < refs.index("- [@a] A0 B") < refs.index("My note on [@a] with 91.7.")
    assert "My note on [@a] with 91.7.\nIts second line.\n\nAnother note.\n\n" in refs
    assert "Old entry" not in out and "Old b" not in out
    assert update_references(out, {"a": E("a"), "b": E("b")}, "numbered") == out
    crlf = update_references(md.replace("\n", "\r\n"), {"a": E("a"), "b": E("b")}, "numbered")
    assert crlf == out.replace("\n", "\r\n")


# --- m2 / P37: pandoc key characters; bare @key citations ----------------------------------
def test_pandoc_key_characters_and_trailing_punctuation():
    md = "As shown [@DBLP:conf/nips/VaswaniSPUJGKP17; @a+b, p. 3] and [-@c.d] [@e.]: [@f?]"
    assert cited_keys(md) == ["DBLP:conf/nips/VaswaniSPUJGKP17", "a+b", "c.d", "e", "f"]


def test_at_inside_words_is_not_a_citation():
    md = "Recall@10 is 0.4 and mAP@0.5 is 0.3 [see Recall@10]; mail me@x.org or [me@x.org]."
    assert cited_keys(md) == [] and cited_keys(md, {"10", "0.5", "x.org"}) == []


def test_bare_keys_count_only_when_they_are_library_keys():
    md = ("@Kim2024Own shows it, unlike @nobody and [@b].\n\n`@code` <https://x.org/@a> "
          "https://y.org/@a [link](https://z.org/@a) <!-- @a -->\n\n```\n@a\n```\n")
    lib = {"Kim2024Own", "a", "b"}
    assert cited_keys(md) == ["b"]
    assert cited_keys(md, lib) == ["Kim2024Own", "b"]
    from po.references import bare_unknown_keys
    assert bare_unknown_keys(md, lib) == ["nobody"]


def test_references_include_bare_library_keys_in_order():
    md = "## Intro\n\n@a found it [@b], and @c too.\n"
    out = update_references(md, {"a": E("a"), "b": E("b")}, "numbered")
    refs = out.split("## References")[1]
    assert refs.index("- [@a] A0 B") < refs.index("- [@b] A0 B") and "[@c]" not in refs
