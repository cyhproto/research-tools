"""Resumable pipeline state (`.state.json`), input hashes and stale stages."""
import hashlib
import json
import os
import tempfile
import time
from pathlib import Path

from .cli import common_parent, emit

STAGES = ["gather", "outline", "literature", "figures", "write", "review", "check"]

STAGE_INPUTS: dict[str, list[str]] = {
    "gather": [],
    "outline": ["settings.md", "materials/idea.md", "materials/experiment_log.md",
                "materials/references/must_cite.*"],
    "literature": ["outline.json", "settings.md", "materials/references/*"],
    "figures": ["outline.json#plotting_plan", "materials/idea.md", "materials/experiment_log.md",
                "materials/figures/*"],
    "write": ["outline.json", "references/library.json", "figures/info.json",
              "materials/idea.md", "materials/experiment_log.md"],
    "review": ["paper.md"],
    "check": ["paper.md", "references/library.json", "materials/idea.md",
              "materials/experiment_log.md", "figures/info.json"],
}

UPSTREAM: dict[str, list[str]] = {
    "outline": ["gather"],
    "literature": ["outline"],
    "figures": ["outline"],
    "write": ["literature", "figures"],
    "review": ["write"],
    "check": ["write"],
}

STATUSES = ("running", "done", "failed")
STATE_FILE = ".state.json"
OPTION_PREFIX = "opt:"  # task ids recording a stage's run options, e.g. opt:review:hand-edits=revise


def _fresh() -> dict:
    return {"stages": {}, "tasks": [], "tool_versions": [], "protected": [], "warnings": []}


def load_state(paper_dir) -> dict:
    path = Path(paper_dir) / STATE_FILE
    if not path.exists():
        return _fresh()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("state is not an object")
    except (ValueError, OSError) as e:
        backup = path.with_name(f"{STATE_FILE}.corrupt-{int(time.time())}")
        path.rename(backup)
        state = _fresh()
        state["warnings"].append(f"{STATE_FILE} was unreadable ({e}); moved to {backup.name}")
        return state
    for key, default in _fresh().items():
        data.setdefault(key, default)
    return data


def save_state(paper_dir, state: dict) -> None:
    paper_dir = Path(paper_dir)
    paper_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=paper_dir, prefix=STATE_FILE + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        os.replace(tmp, paper_dir / STATE_FILE)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _select(paper_dir: Path, spec: str) -> bytes:
    """`path#key`: one top-level key of a JSON file, canonically dumped.

    A missing file or key gives b""; an unparseable file gives its raw bytes, so any edit still counts."""
    rel, _, key = spec.partition("#")
    p = paper_dir / rel
    if not p.is_file():
        return b""
    raw = p.read_bytes()
    try:
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return raw
    if not isinstance(data, dict) or key not in data:
        return b""
    return json.dumps(data[key], sort_keys=True, ensure_ascii=False).encode("utf-8")


def hash_inputs(paper_dir, stage: str) -> str:
    """Hash of a stage's inputs: glob patterns, or `path#key` selectors (no glob) for one JSON key."""
    paper_dir = Path(paper_dir)
    parts: dict[str, bytes] = {}
    for pattern in STAGE_INPUTS[stage]:
        if "#" in pattern:
            parts[pattern] = _select(paper_dir, pattern)
            continue
        for p in paper_dir.glob(pattern):
            if p.is_file():
                parts[p.relative_to(paper_dir).as_posix()] = p.read_bytes()
    h = hashlib.sha256()
    for name in sorted(parts):
        h.update(name.encode("utf-8") + b"\0")
        h.update(parts[name] + b"\0")
    return h.hexdigest()


def mark_stage(paper_dir, stage: str, status: str, now: float | None = None) -> None:
    if stage not in STAGES:
        raise ValueError(f"unknown stage {stage!r}; expected one of {STAGES}")
    if status not in STATUSES:
        raise ValueError(f"unknown status {status!r}; expected one of {list(STATUSES)}")
    state = load_state(paper_dir)
    entry: dict = {"status": status}
    if status == "done":
        entry["inputs_hash"] = hash_inputs(paper_dir, stage)
        entry["finished_at"] = time.time() if now is None else now
    state["stages"][stage] = entry
    save_state(paper_dir, state)


def stale_stages(paper_dir) -> list[str]:
    """Done stages whose inputs changed, or whose upstream finished later or is stale."""
    stages = load_state(paper_dir)["stages"]
    done = {s for s in STAGES if stages.get(s, {}).get("status") == "done"}
    stale: set[str] = set()
    for s in STAGES:  # STAGES is topological, so upstream is decided first
        if s not in done:
            continue
        entry = stages[s]
        if entry.get("inputs_hash") != hash_inputs(paper_dir, s):
            stale.add(s)
            continue
        for u in UPSTREAM.get(s, []):
            if u in stale or (u in done and stages[u].get("finished_at", 0)
                              > entry.get("finished_at", 0)):
                stale.add(s)
                break
    return [s for s in STAGES if s in stale]


def task_done(paper_dir, task_id: str) -> None:
    state = load_state(paper_dir)
    if task_id not in state["tasks"]:
        state["tasks"].append(task_id)
        save_state(paper_dir, state)


def is_task_done(paper_dir, task_id: str) -> bool:
    return task_id in load_state(paper_dir)["tasks"]


def clear_tasks(paper_dir, prefix: str) -> int:
    state = load_state(paper_dir)
    keep = [t for t in state["tasks"] if not t.startswith(prefix)]
    removed = len(state["tasks"]) - len(keep)
    if removed:
        state["tasks"] = keep
        save_state(paper_dir, state)
    return removed


def record_tool_version(paper_dir, rel_path: str) -> None:
    state = load_state(paper_dir)
    state["tool_versions"].append(rel_path)
    save_state(paper_dir, state)


def last_tool_version(paper_dir) -> Path | None:
    versions = load_state(paper_dir)["tool_versions"]
    return Path(paper_dir) / versions[-1] if versions else None


def get_protected(paper_dir) -> list[str]:
    return list(load_state(paper_dir)["protected"])


def set_protected(paper_dir, paragraphs: list[str]) -> None:
    state = load_state(paper_dir)
    state["protected"] = list(paragraphs)
    save_state(paper_dir, state)


def next_stage(paper_dir) -> str | None:
    stages = load_state(paper_dir)["stages"]
    stale = set(stale_stages(paper_dir))
    for s in STAGES:
        if stages.get(s, {}).get("status") != "done" or s in stale:
            return s
    return None


def _cmd_show(args) -> int:
    state = load_state(args.paper)
    emit({"stages": {s: state["stages"].get(s, {}).get("status", "pending") for s in STAGES},
          "stale": stale_stages(args.paper), "tasks_done": len(state["tasks"]),
          "options": [t for t in state["tasks"] if t.startswith(OPTION_PREFIX)],
          "next_stage": next_stage(args.paper), "warnings": state["warnings"]})
    return 0


def _cmd_mark(args) -> int:
    mark_stage(args.paper, args.stage, args.status)
    emit({"stage": args.stage, "status": args.status})
    return 0


def _cmd_task_done(args) -> int:
    task_done(args.paper, args.id)
    emit({"task": args.id, "done": True})
    return 0


def _cmd_is_done(args) -> int:
    done = is_task_done(args.paper, args.id)
    emit({"task": args.id, "done": done})
    return 0 if done else 1


def _cmd_clear_tasks(args) -> int:
    emit({"cleared": clear_tasks(args.paper, args.prefix)})
    return 0


def register(sub) -> None:
    group = sub.add_parser("state", help="pipeline state and checkpoints")
    cmds = group.add_subparsers(dest="state_command")
    cmds.add_parser("show", parents=[common_parent()], help="stages, stale stages, next stage"
                    ).set_defaults(func=_cmd_show)
    mark = cmds.add_parser("mark", parents=[common_parent()], help="set a stage status")
    mark.add_argument("stage", choices=STAGES)
    mark.add_argument("status", choices=list(STATUSES))
    mark.set_defaults(func=_cmd_mark)
    td = cmds.add_parser("task-done", parents=[common_parent()], help="record a checkpoint")
    td.add_argument("id")
    td.set_defaults(func=_cmd_task_done)
    isd = cmds.add_parser("is-done", parents=[common_parent()],
                          help="exit 0 if the checkpoint is done, else 1")
    isd.add_argument("id")
    isd.set_defaults(func=_cmd_is_done)
    ct = cmds.add_parser("clear-tasks", parents=[common_parent()],
                         help="forget checkpoints starting with PREFIX")
    ct.add_argument("prefix")
    ct.set_defaults(func=_cmd_clear_tasks)
