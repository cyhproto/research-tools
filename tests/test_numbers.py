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
