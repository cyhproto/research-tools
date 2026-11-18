import sys
from pathlib import Path
from po.plotrun import find_plot_python, run_plot

def test_python_order(tmp_path):
    env = {"VIRTUAL_ENV": "/venv"}
    assert find_plot_python(tmp_path, env, lambda c: "/bin/uv", lambda cmd: cmd[0] == "/venv/bin/python") == ["/venv/bin/python"]
    uv = find_plot_python(tmp_path, {}, lambda c: "/bin/uv", lambda cmd: cmd[0] == "uv")
    assert uv[:2] == ["uv", "run"] and "matplotlib" in uv and "pip" not in uv
    assert find_plot_python(tmp_path, {}, lambda c: None, lambda cmd: False) is None

def script(tmp_path, body):
    (tmp_path / "figures/src").mkdir(parents=True, exist_ok=True)
    s = tmp_path / "figures/src/fig_a.py"; s.write_text(body); return s

def test_run_plot_ok(tmp_path):
    s = script(tmp_path, "open('figures/fig_a.png','wb').write(b'png')\n")
    r = run_plot(s, tmp_path, [sys.executable]); assert r.ok and r.png.name == "fig_a.png"

def test_run_plot_failure_and_timeout(tmp_path):
    r = run_plot(script(tmp_path, "raise SystemExit('boom')\n"), tmp_path, [sys.executable])
    assert not r.ok and "boom" in r.stderr_tail
    r = run_plot(script(tmp_path, "import time; time.sleep(5)\n"), tmp_path, [sys.executable], timeout_s=1)
    assert not r.ok

def test_python_candidate_order(tmp_path):
    seen = []
    def probe(cmd):
        seen.append(cmd[0]); return False
    find_plot_python(tmp_path, {"VIRTUAL_ENV": "/v"}, lambda c: "/bin/uv", probe)
    assert seen == ["/v/bin/python", str(tmp_path / ".venv/bin/python"),
                    str(tmp_path / "venv/bin/python"), "python3", "uv"]

def test_stale_png_is_not_ok(tmp_path):
    (tmp_path / "figures").mkdir()
    (tmp_path / "figures/fig_a.png").write_bytes(b"old")
    r = run_plot(script(tmp_path, "pass\n"), tmp_path, [sys.executable])
    assert not r.ok

def test_cli_exit_2_without_python(tmp_path, monkeypatch, capsys):
    import po.plotrun as pr
    from po.cli import main
    script(tmp_path, "pass\n")
    monkeypatch.setattr(pr, "find_plot_python", lambda *a, **k: None)
    assert main(["plot-run", "--paper", str(tmp_path), "--script", "figures/src/fig_a.py"]) == 2
    assert "install matplotlib in this project's environment, or install uv" in capsys.readouterr().err

def test_cli_ok_and_fail(tmp_path, monkeypatch, capsys):
    import json, po.plotrun as pr
    from po.cli import main
    monkeypatch.setattr(pr, "find_plot_python", lambda *a, **k: [sys.executable])
    script(tmp_path, "open('figures/fig_a.png','wb').write(b'p')\n")
    assert main(["plot-run", "--paper", str(tmp_path), "--script", "figures/src/fig_a.py"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True
    script(tmp_path, "raise SystemExit('bad')\n")
    assert main(["plot-run", "--paper", str(tmp_path), "--script", "figures/src/fig_a.py"]) == 1
    assert "bad" in json.loads(capsys.readouterr().out)["stderr_tail"]
