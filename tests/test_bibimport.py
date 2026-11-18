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
