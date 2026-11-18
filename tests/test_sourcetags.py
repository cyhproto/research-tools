import shutil
from pathlib import Path
from po.sourcetags import verify_log, untagged_numbers

LOG = """## 2. Raw Numeric Data
| Ours | 87.3 [src#a1: results/metrics.csv | row=seed_1 | col=val_acc | scale=100] |
| Ours (seed 2) | 87.9 [src#a2: results/metrics.csv | row=#2 | col=val_acc | scale=100] |
| Mean | 87.6 [calc: mean(a1, a2)] | Std | 0.42 [calc: std(a1, a2)] |
F1 0.95 [src: results/summary.json | path=test.per_class.1]
Loss 0.4123 [src: logs/train.log | line=3 | pattern=val_loss=([0-9.]+)]
Wrong 88.1 [src: results/metrics.csv | row=seed_1 | col=val_acc | scale=100]
Missing 1.0 [src: results/none.csv | row=#1 | col=x]
Notebook 0.5 [src: notebooks/analysis.ipynb | line=1]
Dataset size 20000 [manual: dataset paper, Table 1]
We trained for 100 epochs.
"""

def make(tmp_path):
    root = tmp_path / "proj"; shutil.copytree("tests/fixtures/toyproject", root)
    log = root / "paper/materials/experiment_log.md"; log.parent.mkdir(parents=True); log.write_text(LOG)
    return root, log

def test_verify_log_statuses(tmp_path):
    root, log = make(tmp_path)
    res = verify_log(log, root)
    assert [r.status for r in res] == ["ok", "ok", "ok", "ok", "ok", "ok", "mismatch",
                                       "unreadable", "unreadable", "manual"]
    assert res[8].reason.startswith("unsupported file type")

def test_untagged(tmp_path):
    assert untagged_numbers(LOG) == [(11, "100")]

def test_tsv_and_last_row(tmp_path):
    root = tmp_path; (root / "r.tsv").write_text("run\tacc\nA\t0.5\nB\t0.7\n")
    log = root / "log.md"; log.write_text("x 70.0 [src: r.tsv | row=last | col=acc | scale=100]\n")
    assert verify_log(log, root)[0].status == "ok"


import json
import pytest
from po.cli import main
from po.sourcetags import Unreadable, parse_tags, resolve_src


def one(tmp_path, line, files=None):
    root = tmp_path
    for name, content in (files or {}).items():
        (root / name).write_text(content, encoding="utf-8")
    log = root / "log.md"; log.write_text(line + "\n", encoding="utf-8")
    return verify_log(log, root)


CSV = {"r.csv": "run,a,b\nx,1,2\ny,3,4\n"}


def test_calc_functions(tmp_path):
    line = ("A 1.0 [src#p: r.csv | row=x | col=a] B 3.0 [src#q: r.csv | row=y | col=a]\n"
            "pstd 1.0 [calc: pstd(p, q)]\nsub -2.0 [calc: sub(p, q)]\ndiv 0.33 [calc: div(p, q)]")
    res = one(tmp_path, line, CSV)
    assert [r.status for r in res] == ["ok"] * 5


def test_calc_unreadable(tmp_path):
    res = one(tmp_path, "A 1.0 [src#p: nope.csv | row=x | col=a]\nB 1.0 [calc: mean(p)]\nC 1.0 [calc: mean(zz)]")
    assert [r.status for r in res] == ["unreadable"] * 3


def test_unreadable_locators(tmp_path):
    files = dict(CSV, **{"j.json": json.dumps({"a": [1]})})
    lines = ("1.0 [src: r.csv | row=#9 | col=a]\n1.0 [src: r.csv | row=x | col=zz]\n"
             "1.0 [src: j.json | path=a.5]\n1.0 [src: j.json | path=q.r]")
    assert [r.status for r in one(tmp_path, lines, files)] == ["unreadable"] * 4


def test_scale(tmp_path):
    assert one(tmp_path, "x 10.0 [src: r.csv | row=x | col=a | scale=10]", CSV)[0].status == "ok"


def test_pipe_without_spaces(tmp_path):
    r = one(tmp_path, "1.0 [src: r.csv|row=x|col=a]", CSV)[0]
    assert r.status == "unreadable" and r.reason == "fields must be separated by ' | ' (with spaces)"


def test_pattern_with_bare_pipe(tmp_path):
    r = one(tmp_path, "1.5 [src: t.txt | line=1 | pattern=(?:a|b)=([0-9.]+)]", {"t.txt": "b=1.5\n"})[0]
    assert r.status == "ok"


def test_unmatched_optional_group(tmp_path):
    r = one(tmp_path, "1.0 [src: t.txt | line=1 | pattern=x(\\d)?y]", {"t.txt": "xy\n"})[0]
    assert r.status == "unreadable" and "group" in r.reason


def test_bom_and_blank_rows(tmp_path):
    files = {"r.csv": "﻿run,a\nx,1\n\n,\ny,3\n\n"}
    res = one(tmp_path, "1.0 [src: r.csv | row=x | col=a]\n3.0 [src: r.csv | row=#2 | col=a]\n"
                        "3.0 [src: r.csv | row=last | col=a]", files)
    assert [r.status for r in res] == ["ok"] * 3


def test_invalid_utf8_log(tmp_path, capsys):
    (tmp_path / "paper/materials").mkdir(parents=True)
    (tmp_path / "paper/materials/experiment_log.md").write_bytes(b"\xff\xfe\xfa bad")
    with pytest.raises(Unreadable):
        verify_log(tmp_path / "paper/materials/experiment_log.md", tmp_path)
    rc = main(["log", "verify", "--paper", str(tmp_path / "paper")])
    assert rc == 2 and "UTF-8" in capsys.readouterr().out


def test_cli_verify(tmp_path, capsys):
    root, log = make(tmp_path)
    rc = main(["log", "verify", "--paper", str(root / "paper")])
    out = json.loads(capsys.readouterr().out)
    assert rc == 1 and set(out) >= {"ok", "mismatch", "unreadable", "manual", "untagged", "items"}
    assert out["mismatch"] == 1
    log.write_text("x 87.3 [src: results/metrics.csv | row=seed_1 | col=val_acc | scale=100]\n")
    rc = main(["log", "verify", "--paper", str(root / "paper"), "--project", str(root)])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0 and out["ok"] == 1


def test_mask_tags_hides_tag_numbers():
    from po.numtok import find_numbers
    from po.sourcetags import mask_tags
    text = "x 87.3 [src#a100: r.csv | row=#2 | col=a | scale=100]\ny 55.5 [manual: n 12.5]"
    assert [n.token for n in find_numbers(mask_tags(text))] == ["87.3", "55.5"]
