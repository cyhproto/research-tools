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
