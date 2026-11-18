from po.frontmatter import parse_frontmatter, dump_frontmatter

def test_frontmatter_types():
    text = "---\nname: x\nblind_review: true\nlength_words: [5500, 7500]\nsections:\n  - Abstract\n  - Method\n# note\n---\nBody\n"
    data, body = parse_frontmatter(text)
    assert data == {"name": "x", "blind_review": True, "length_words": [5500, 7500], "sections": ["Abstract", "Method"]}
    assert body == "Body\n"
    assert parse_frontmatter("plain") == ({}, "plain")
    assert parse_frontmatter(dump_frontmatter({"a": 1, "b": ["x y", "z"]}, "B"))[0] == {"a": 1, "b": ["x y", "z"]}

def test_quotes_and_roundtrip_of_tricky_strings():
    data, _ = parse_frontmatter('---\na: "true"\nb: \'12\'\nc: []\n---\n')
    assert data == {"a": "true", "b": "12", "c": []}
    tricky = {"s": "true", "t": "a: b", "u": "7", "v": ["a, b", "c"], "w": []}
    assert parse_frontmatter(dump_frontmatter(tricky, ""))[0] == tricky
