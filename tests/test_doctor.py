import json
from po.doctor import doctor
from po.scholar import LookupOutcome


def test_doctor_reports(tmp_path):
    r = doctor(tmp_path, env={"OPENALEX_API_KEY": "secret123"}, which=lambda c: None,
               probe=lambda c: False, python_version=(3, 12, 3))
    assert r["python_ok"] and r["openalex_key"] is True and r["s2_key"] is False and r["plot_python"] is None
    assert any("matplotlib" in p for p in r["problems"]) and "secret123" not in json.dumps(r)
    assert r["network"] is None
    assert not doctor(tmp_path, env={}, which=lambda c: None, probe=lambda c: True, python_version=(3, 9, 6))["python_ok"]


def test_doctor_network(tmp_path):
    class L:
        def __init__(self, out):
            self.out, self.calls = out, []

        def openalex_title(self, t):
            self.calls.append(t)
            return self.out

    kw = dict(env={}, which=lambda c: "/x", probe=lambda c: True, python_version=(3, 12, 0), network=True)
    ok = L(LookupOutcome(records=[object()]))
    assert doctor(tmp_path, lookup=ok, **kw)["network"] is True
    assert ok.calls == ["Attention Is All You Need"]
    assert doctor(tmp_path, lookup=L(LookupOutcome(failed=True)), **kw)["network"] is False
    assert doctor(tmp_path, lookup=L(LookupOutcome()), **kw)["network"] is False


def test_old_python_is_reported_on_stderr(monkeypatch, capsys):
    import runpy
    import sys
    import pytest
    monkeypatch.setattr(sys, "version_info", (3, 9, 6, "final", 0))
    with pytest.raises(SystemExit) as e:
        runpy.run_path("plugins/paper-orchestra/scripts/po.py", run_name="__main__")
    cap = capsys.readouterr()
    assert e.value.code == 2 and cap.out == "" and "3.10" in cap.err and "3.9.6" in cap.err


def test_doctor_exit_2_says_why_on_stderr(monkeypatch, capsys):
    import po.doctor as d
    from po.cli import main
    real = d.doctor
    monkeypatch.setattr(d, "doctor", lambda project, network=False: real(
        project, env={}, which=lambda c: None, probe=lambda c: False, python_version=(3, 9, 6)))
    assert main(["doctor", "--paper", "paper"]) == 2
    cap = capsys.readouterr()
    assert json.loads(cap.out)["python_ok"] is False and "3.10" in cap.err
