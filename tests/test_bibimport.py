from po.bibimport import parse_bibtex, parse_csl_json, clean_latex, load_imports

BIB = r"""
@string{nips = "NeurIPS"}
% comment line
@inproceedings{devlin2019bert,
  title = {{BERT}: Pre-training of Deep Bidirectional Transformers for Language Understanding},
  author = {Devlin, Jacob and Chang, Ming-Wei and Lee, Kenton and Toutanova, Kristina},
  booktitle = {Proceedings of NAACL},
  year = {2019},
  doi = {https://doi.org/10.18653/V1/N19-1423},
  abstract = {We introduce a new language
  representation model called {BERT}.}
}
@comment{ignored}
@article{broken, title = {Unclosed
"""

def test_parse_bibtex():
    refs, warns = parse_bibtex(BIB, "library.bib")
    [r] = refs
    assert r.key == "devlin2019bert" and r.source_file == "library.bib"
    assert r.title == "BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding"
    assert r.authors[:2] == ["Jacob Devlin", "Ming-Wei Chang"] and r.year == 2019
    assert r.doi == "10.18653/v1/n19-1423" and r.venue == "Proceedings of NAACL"
    assert r.abstract == "We introduce a new language representation model called BERT."
    assert any("broken" in w for w in warns)

def test_clean_latex():
    assert clean_latex(r"M{\"u}ller \& {\'E}cole \emph{deep}") == "Müller & École deep"
    assert clean_latex(r"M\"uller \'Ecole \`a \^o \~n 1--2") == "Müller École à ô ñ 1–2"

def test_csl_and_load(tmp_path):
    refs, _ = parse_csl_json(open("tests/fixtures/bib/csl.json").read())
    assert (refs[0].year, refs[0].venue, refs[0].authors[0]) == (2021, "Applied Energy", "Ana Silva")
    assert refs[0].key == "silva2021battery" and refs[1].abstract is None
    d = tmp_path / "materials/references"; d.mkdir(parents=True)
    (d / "library.json").write_text(open("tests/fixtures/bib/csl.json").read()); (d / "must_cite.bib").write_text(BIB)
    imp = load_imports(tmp_path)
    assert len(imp["library"]) == len(refs) and len(imp["must_cite"]) == 1 and imp["warnings"]

def test_csl_missing_id():
    refs, warns = parse_csl_json('[{"title": "A"}, {"citation-key": "ck", "title": "B"}]')
    assert [r.key for r in refs] == ["", "ck"] and len(warns) == 1


def test_latin1_bib_and_bom_json(tmp_path):
    d = tmp_path / "materials/references"; d.mkdir(parents=True)
    (d / "library.bib").write_bytes("@article{k1, title = {Café}, year = {2020}}".encode("latin-1"))
    (d / "must_cite.json").write_bytes(b"\xef\xbb\xbf" + b'[{"id": "a", "title": "T"}]')
    imp = load_imports(tmp_path)
    assert imp["library"][0].title == "Café"
    assert any("library.bib" in w and "latin-1" in w for w in imp["warnings"])
    assert [r.key for r in imp["must_cite"]] == ["a"]


def test_csl_non_string_fields():
    txt = ('[{"id": "x", "title": "T", "DOI": ["10.1/X"], "abstract": 5, "author": [{"given": 3, "family": ["Doe"]}]},'
           ' {"id": "y", "title": {"a": 1}, "DOI": {"b": 1}, "abstract": ["A"]}]')
    refs, _ = parse_csl_json(txt)
    assert len(refs) == 2 and refs[0].doi == "10.1/x" and refs[0].abstract == "5"
    assert refs[0].authors == ["3 Doe"] or refs[0].authors == ["Doe"]
    assert refs[1].doi is None and refs[1].title == "" and refs[1].abstract == "A"


def test_csl_dates():
    refs, _ = parse_csl_json('[{"id":"a"},{"id":"b","issued":{"date-parts":[[null]]}},{"id":"c","issued":{"date-parts":[["2019"]]}},{"id":"d","issued":"2018"}]')
    assert [r.year for r in refs] == [None, None, 2019, 2018]


def test_and_others_dropped():
    refs, _ = parse_bibtex("@article{k, author = {Doe, Jane and Roe, Rick and others}, title = {T}}")
    assert refs[0].authors == ["Jane Doe", "Rick Roe"]


def test_malformed_entries_do_not_swallow_neighbours():
    txt = ("@article{a, title = {A}}\n@article{bad title Missing equals}\n"
           "@article{unclosed, title = {Oops\n@article{c, title = {C}}\n")
    refs, warns = parse_bibtex(txt)
    assert [r.key for r in refs] == ["a", "c"]
    assert any("bad" in w for w in warns) and any("unclosed" in w for w in warns)


def test_bibtex_misc():
    txt = r"""
@string{jn = "Nature"}
@ARTICLE{Smith:2020/x,
  author = {{World Health Organization} and Smith, John},
  journal = jn # " Methods",
  title = {T},
  doi = {10.1002/x--y\_z},
}
"""
    [r], warns = parse_bibtex(txt)
    assert r.key == "Smith:2020/x" and not warns
    assert r.authors == ["World Health Organization", "John Smith"]
    assert r.venue == "Nature Methods"
    assert r.doi == "10.1002/x--y_z"


def test_clean_latex_extras():
    assert clean_latex(r"\v{S}koda \c{c} Stra\ss e \o{} {\o} \{x\} 50\% a\_b A~B 1---2") == "Skoda c Strasse o o {x} 50% a_b A B 1—2"
