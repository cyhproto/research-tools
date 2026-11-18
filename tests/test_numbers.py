import pytest
from po.numbers import extract_paper_numbers, matches, materials_numbers, unmatched
from po.numtok import find_numbers


def vals(md):
    return [h.num.value for h in extract_paper_numbers(md)]


def test_exclusions():
    md = ("Our method reaches 87.3% (Table 2, Figure 3, Section 4.1, Eq. (3)) vs ResNet-50 85.0 [@He2016DeepResidual].\n"
          "```mermaid\nA-->B 99\n```\n<!-- note 42 -->\n## References\n- [@x] 2016. Vol 12.\n")
    assert [h.num.value for h in extract_paper_numbers(md)] == [87.3, 85.0]


def test_matches():
    mats = materials_numbers(["acc 87.31 and 0.8731 [src: r.csv | row=#1 | col=a] and 1,024"])
    assert matches(find_numbers("87.3")[0], mats) and not matches(find_numbers("88.0")[0], mats)
    assert matches(find_numbers("1024")[0], mats)
    assert all(n.value != 1 for n in mats)   # numbers inside tags are excluded


def test_unmatched_years():
    md = "As shown in 2017 [@Vaswani2017AttentionAll], we get 91.7 and 87.3."
    assert [h.num.value for h in unmatched(md, ["87.3"], {2017})] == [91.7]


def test_inline_code_and_multiline_comment():
    assert vals("Use `lr=0.001` and 55.5.\n<!-- a\n 77.7 \n-->\nok 66.6") == [55.5, 66.6]
    assert vals("Use ``a ` 123.4`` then 5.5") == [5.5]


def test_link_and_image_targets():
    assert vals("See [paper](http://x.org/v1.22/a) and ![f](img/fig12.5.png) 44.4") == [44.4]


def test_heading_numbering_and_list_markers():
    md = "## 3.1 Results\n12. 14.5 ms\n- 15.5 ms\n1) 16.5 ms\n"
    assert vals(md) == [14.5, 15.5, 16.5]


def test_cross_references():
    md = ("Fig. 4.1 and Equation (12) and Appendix 20 and Sec. 3.2 and Table 15 show 33.3; "
          "figure 77 too.")
    assert vals(md) == [33.3]


def test_tag_and_trivial():
    assert vals(r"$x \tag{12.5}$ is 3 or 3.0 or 50% or 1,200") == [3.0, 50.0, 1200.0]


def test_references_section_ends_at_next_h2():
    md = "## References\n- [@x] 2016 pp 123.4\n## Appendix\nvalue 88.8\n"
    assert vals(md) == [88.8]


def test_text_under_references_that_is_not_an_entry_is_body_text():
    assert vals("## References\n- [@x] 2016 pp 123.4\nMy note 77.7.\n") == [77.7]


def test_fence_in_references_and_tilde():
    md = "~~~\n99.9\n~~~\nreal 11.1\n"
    assert vals(md) == [11.1]


def test_hit_line_and_context():
    md = "First sentence. We got 42.5 here, nice.\nOther 17.5 line."
    hits = extract_paper_numbers(md)
    assert [(h.line_no, h.num.value) for h in hits] == [(1, 42.5), (2, 17.5)]
    assert hits[0].context == "We got 42.5 here, nice."


def test_context_trimmed():
    md = "word " * 100 + "99.5 end."
    h = extract_paper_numbers(md)[0]
    assert len(h.context) <= 200 and "99.5" in h.context


def test_matches_scaling_only():
    mats = materials_numbers(["x 0.873 and 45"])
    assert matches(find_numbers("87.3%")[0], mats)
    assert matches(find_numbers("4500")[0], mats)
    assert matches(find_numbers("0.45")[0], mats)
    assert not matches(find_numbers("450.0")[0], mats)


# --- m3 / P37: plural and list cross-references ------------------------------------------------
def test_plural_and_list_cross_references():
    md = ("Sections 4.1 and 4.2 show 33.3; Figures 12 and 14 agree; see Tables 2–4, Eqs. (13) and (14), "
          "Figs. 11, 12, and 13, Secs. 5.1 to 5.3 and Equations 21 & 22.")
    assert vals(md) == [33.3]


def test_a_result_after_a_cross_reference_is_still_checked():
    assert vals("In Figure 3, 12.5% of the samples fail.") == [12.5]
    assert vals("Tables 12 and 33.5% more errors.") == [33.5]
    assert vals("Sections 4.1 and 4.2, 57.5 on average.") == [57.5]


def test_ratio_checked_and_resolution_skipped():
    assert vals("It is 13.2x faster on 512x512 images than 12.5× before.") == [13.2, 12.5]
    assert matches(find_numbers("13.2x")[0], materials_numbers(["speedup 13.2x on 512x512 inputs"]))
    assert [h.num.value for h in unmatched("We get 13.2x and 14.1x on 512x512.", ["speedup 13.2x"], set())] == [14.1]


# --- P39 / NB1: a plural cross-reference list never swallows a result ------------------------
@pytest.mark.parametrize("md, keep", [
    ("Across Figures 3\u20135, 91.7 is the best.", [91.7]),
    ("(Tables 2\u20134), 87.3 on average.", [87.3]),
    ("Sections 4.1\u20134.3, 57.5 points.", [57.5]),
    ("Tables 2 to 4, 87.3 vs. 85.1.", [87.3, 85.1]),
    ("the figures 87.3 and 85.1 respectively", [87.3, 85.1]),
    # a range's end has its start's shape, and a spaced dash is punctuation, not a range
    ("Tuning lifts Tables 2 and 3 to 87.3 overall.", [87.3]),
    ("Tables 2 and 3 \u2013 87.3 overall.", [87.3]),
])
def test_cross_reference_lists_keep_results(md, keep):
    assert vals(md) == keep


def test_plural_names_are_case_sensitive_singular_names_are_not():
    assert vals("Figures 12 and 14 and Sections 4.1 and 4.2 agree.") == []
    assert vals("figure 77 and TABLE 15 and Section 4.1 too.") == []


def test_long_unclosed_lists_do_not_backtrack():
    import signal
    if not hasattr(signal, "SIGALRM"):
        pytest.skip("needs SIGALRM")

    def too_slow(*_):
        raise TimeoutError("the cross-reference pattern backtracks on a long list")
    old = signal.signal(signal.SIGALRM, too_slow)
    signal.alarm(5)
    try:
        assert vals("Tables " + "1, " * 40 + "2 vs 87.3 here.") == [87.3]
        # a percent cannot close the list, so only its first item is a cross-reference
        assert vals("Figures " + "1.1, " * 40 + "and 2.5% here.") == [1.1] * 39 + [2.5]
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)
