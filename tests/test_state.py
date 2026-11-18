import os

import pytest

from po.state import *  # noqa: F401,F403


def test_input_change_makes_stage_stale(tmp_path):
    (tmp_path / "outline.json").write_text("{}")
    mark_stage(tmp_path, "figures", "done", now=100.0)
    assert stale_stages(tmp_path) == []
    (tmp_path / "outline.json").write_text('{"x": 1}')
    assert stale_stages(tmp_path) == ["figures"]


def test_upstream_finished_later(tmp_path):
    mark_stage(tmp_path, "write", "done", now=100.0)
    mark_stage(tmp_path, "literature", "done", now=200.0)
    assert "write" in stale_stages(tmp_path)


def test_staleness_is_transitive(tmp_path):
    (tmp_path / "outline.json").write_text("{}")
    mark_stage(tmp_path, "figures", "done", now=100.0)
    mark_stage(tmp_path, "write", "done", now=200.0)
    mark_stage(tmp_path, "review", "done", now=300.0)
    mark_stage(tmp_path, "check", "done", now=300.0)
    assert stale_stages(tmp_path) == []
    (tmp_path / "outline.json").write_text('{"x": 1}')
    assert stale_stages(tmp_path) == ["figures", "write", "review", "check"]


def test_transitive_when_own_inputs_unchanged(tmp_path):
    (tmp_path / "outline.json").write_text("{}")
    mark_stage(tmp_path, "figures", "done", now=100.0)
    mark_stage(tmp_path, "write", "done", now=200.0)
    mark_stage(tmp_path, "review", "done", now=300.0)
    (tmp_path / "outline.json").write_text('{"x": 1}')
    # review's own input (paper.md) is untouched, yet it is stale via write
    assert stale_stages(tmp_path) == ["figures", "write", "review"]


def test_tasks_versions_protected(tmp_path):
    assert not is_task_done(tmp_path, "lit:t1")
    task_done(tmp_path, "lit:t1")
    assert is_task_done(tmp_path, "lit:t1") and clear_tasks(tmp_path, "lit:") == 1
    record_tool_version(tmp_path, "drafts/v0.md")
    assert last_tool_version(tmp_path) == tmp_path / "drafts/v0.md"
    set_protected(tmp_path, ["para"])
    assert get_protected(tmp_path) == ["para"]


def test_corrupt_state_recovers(tmp_path):
    (tmp_path / ".state.json").write_text('{"stages": {"outl')
    st = load_state(tmp_path)
    assert st["stages"] == {} and st["warnings"]
    assert list(tmp_path.glob(".state.json.corrupt-*"))


def test_failed_save_keeps_old_file(tmp_path, monkeypatch):
    save_state(tmp_path, {"stages": {"gather": {"status": "done"}}})

    def boom(*a):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        save_state(tmp_path, {"stages": {}})
    assert load_state(tmp_path)["stages"]["gather"]["status"] == "done"


def test_cli_state(tmp_path, capsys):
    from po.cli import main
    p = str(tmp_path)
    assert main(["state", "is-done", "lit:a", "--paper", p]) == 1
    assert main(["state", "task-done", "lit:a", "--paper", p]) == 0
    assert main(["state", "is-done", "lit:a", "--paper", p]) == 0
    assert main(["state", "mark", "gather", "done", "--paper", p]) == 0
    capsys.readouterr()
    assert main(["state", "show", "--paper", p]) == 0
    out = capsys.readouterr().out
    assert '"next_stage": "outline"' in out
    assert main(["state", "clear-tasks", "lit:", "--paper", p]) == 0
    assert main(["state", "mark", "bogus", "done", "--paper", p]) == 2
