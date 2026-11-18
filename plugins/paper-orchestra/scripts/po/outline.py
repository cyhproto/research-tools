"""Outline schema checks, rendering, literature search tasks, size estimate and citation injection."""
import dataclasses
import hashlib
import json
import re
import sys
from pathlib import Path

from .cli import common_parent, emit

ASPECT_RATIOS = ["1:1", "1:4", "2:3", "3:2", "3:4", "4:1", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"]
DATA_SOURCES = {"idea.md", "experiment_log.md", "both"}
PLOT_TYPES = ("plot", "diagram")
TOP_KEYS = ("plotting_plan", "intro_related_work_plan", "section_plan")
RW_KEYS = ("methodology_cluster", "sota_investigation_mission", "limitation_hypothesis",
           "limitation_search_queries", "bridge_to_our_method")
HINT_RE = re.compile(r"^.+ \(.+\)$")
HINT_PREFIXES = ("research paper or technical report introducing '", "research paper introducing '")
NUMBERING_RE = re.compile(r"^\s*\d+(?:\.\d+)*\.?\s+")


def _norm(name) -> str:
    return NUMBERING_RE.sub("", str(name)).strip().lower()


def _dicts(value) -> list[dict]:
    return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []


def _obj(value) -> dict:
    return value if isinstance(value, dict) else {}


def _strs(value) -> list[str]:
    return [v for v in value if isinstance(v, str)] if isinstance(value, list) else []


def _is_str_list(value) -> bool:
    return isinstance(value, list) and all(isinstance(v, str) for v in value)


def _blank(value) -> bool:
    return not isinstance(value, str) or not value.strip()


def _validate_figures(plan, project_root, errors: list[str]) -> None:
    root = (Path(project_root) if project_root is not None else Path(".")).resolve()
    seen: set[str] = set()
    for i, fig in enumerate(_dicts(plan)):
        fid = fig.get("figure_id")
        label = f"plotting_plan[{i}]"
        if not isinstance(fid, str) or not fid.strip():
            errors.append(f"{label}: figure_id is missing")
        else:
            if "figure" in fid.lower():
                errors.append(f"{label}: figure_id {fid!r} must not contain the word 'figure'")
            if fid in seen:
                errors.append(f"{label}: duplicate figure_id {fid!r}")
            seen.add(fid)
        ptype = fig.get("plot_type")
        if not isinstance(ptype, str) or ptype not in PLOT_TYPES:
            errors.append(f"{label}: plot_type must be 'plot' or 'diagram', got {ptype!r}")
        if not isinstance(fig.get("data_source"), str) or fig["data_source"] not in DATA_SOURCES:
            errors.append(f"{label}: data_source must be one of {sorted(DATA_SOURCES)}, "
                          f"got {fig.get('data_source')!r}")
        ratio = fig.get("aspect_ratio")
        if ratio is None and ptype == "plot":
            errors.append(f"{label}: aspect_ratio is required for a plot")
        elif ratio is not None and (not isinstance(ratio, str) or ratio not in ASPECT_RATIOS):
            errors.append(f"{label}: aspect_ratio must be one of {ASPECT_RATIOS}, got {ratio!r}")
        files = fig.get("data_files", [])
        if not isinstance(files, list):
            errors.append(f"{label}: data_files must be a list of project-relative paths")
            continue
        for f in files:
            if not isinstance(f, str):
                errors.append(f"{label}: data_files entries must be strings, got {f!r}")
                continue
            target = (root / f).resolve()
            if not target.is_relative_to(root):
                errors.append(f"{label}: data_files path {f!r} is outside the project root")
            elif not target.is_file():
                errors.append(f"{label}: data_files path not found: {f!r}")


def _validate_intro_rw(plan, errors: list[str]) -> None:
    plan = plan if isinstance(plan, dict) else {}
    intro = plan.get("introduction_strategy")
    intro = intro if isinstance(intro, dict) else {}
    for key in ("hook_hypothesis", "problem_gap_hypothesis"):
        if _blank(intro.get(key)):
            errors.append(f"introduction_strategy: {key} must be a non-empty string")
    dirs = intro.get("search_directions")
    if not _is_str_list(dirs):
        errors.append("introduction_strategy: search_directions must be a list of strings")
        dirs = None
    n = len(dirs) if dirs is not None else 0
    if not 3 <= n <= 5:
        errors.append(f"introduction_strategy: search_directions needs 3 to 5 entries, got {n}")
    rw = plan.get("related_work_strategy")
    rw = rw if isinstance(rw, dict) else {}
    subs = rw.get("subsections")
    subs = subs if isinstance(subs, list) else []
    if not 2 <= len(subs) <= 4:
        errors.append(f"related_work_strategy.subsections needs 2 to 4 entries, got {len(subs)}")
    for i, sub in enumerate(subs):
        sub = sub if isinstance(sub, dict) else {}
        label = f"related_work_strategy.subsections[{i}]"
        for key in RW_KEYS:
            if key not in sub:
                errors.append(f"{label}: missing {key}")
            elif key == "limitation_search_queries":
                if not _is_str_list(sub[key]):
                    errors.append(f"{label}: limitation_search_queries must be a list of strings")
            elif _blank(sub[key]):
                errors.append(f"{label}: {key} must be a non-empty string")


def _validate_sections(plan, style, must_cite_keys, errors: list[str]) -> None:
    sections = _dicts(plan)
    have = {_norm(s.get("section_title", "")) for s in sections}
    lit = {_norm(s) for s in style.literature_sections}
    for name in style.sections:
        if _norm(name) not in lit and _norm(name) not in have:
            errors.append(f"missing section: {name}")
    assigned: set[str] = set()
    for sec in sections:
        title = sec.get("section_title", "")
        subs = _dicts(sec.get("subsections"))
        if len(subs) == 1 and re.match(r"\d+\.\d+", str(subs[0].get("subsection_title", "")).strip()):
            errors.append(f"orphan subsection: {title!r} has only {subs[0].get('subsection_title')!r}")
        for sub in subs:
            where = f"{title} - {sub.get('subsection_title', '')}"
            hints = sub.get("citation_hints", [])
            if not _is_str_list(hints):
                errors.append(f"{where}: citation_hints must be a list of strings")
                hints = []
            if not _is_str_list(sub.get("content_bullets", [])):
                errors.append(f"{where}: content_bullets must be a list of strings")
            for hint in hints:
                if not (isinstance(hint, str) and (HINT_RE.match(hint) or hint.startswith(HINT_PREFIXES))):
                    errors.append(f"citation hint format in {where}: {hint!r}; use "
                                  "'Author (Exact Title)' or \"research paper or technical report "
                                  "introducing '<Name>'\"")
            mc = sub.get("must_cite", [])
            if _is_str_list(mc):
                assigned.update(mc)
            else:
                errors.append(f"{where}: must_cite must be a list of strings")
    for key in must_cite_keys:
        if key not in assigned:
            errors.append(f"must-cite not assigned: {key}")


def validate_outline(outline: dict, style, must_cite_keys: list[str],
                     project_root: Path | None = None) -> list[str]:
    if not isinstance(outline, dict):
        return ["outline must be a JSON object"]
    errors = [f"missing key: {k}" for k in TOP_KEYS if k not in outline]
    if "plotting_plan" in outline:
        _validate_figures(outline["plotting_plan"], project_root, errors)
    if "intro_related_work_plan" in outline:
        _validate_intro_rw(outline["intro_related_work_plan"], errors)
    if "section_plan" in outline:
        _validate_sections(outline["section_plan"], style, must_cite_keys, errors)
    return errors


def render_outline_md(outline: dict) -> str:
    out = ["# Outline", "", "## Figure plan", ""]
    for f in _dicts(outline.get("plotting_plan")):
        out.append(f"- **{f.get('figure_id', '')}** ({f.get('plot_type', '')}, {f.get('aspect_ratio', '-')}, "
                   f"source: {f.get('data_source', '')}): {f.get('title', '')}")
        out.append(f"  - Objective: {f.get('objective', '')}")
        if _strs(f.get("data_files")):
            out.append(f"  - Data files: {', '.join(_strs(f['data_files']))}")
    plan = _obj(outline.get("intro_related_work_plan"))
    intro = _obj(plan.get("introduction_strategy"))
    out += ["", "## Introduction plan", "", f"- Hook: {intro.get('hook_hypothesis', '')}",
            f"- Problem gap: {intro.get('problem_gap_hypothesis', '')}", "- Search directions:"]
    out += [f"  - {d}" for d in _strs(intro.get("search_directions"))]
    rw = _obj(plan.get("related_work_strategy"))
    out += ["", "## Related Work plan", "", rw.get("overview", "")]
    for sub in _dicts(rw.get("subsections")):
        out += ["", f"### {sub.get('subsection_title', '')}", "",
                f"- Cluster: {sub.get('methodology_cluster', '')}",
                f"- Mission: {sub.get('sota_investigation_mission', '')}",
                f"- Limitation hypothesis: {sub.get('limitation_hypothesis', '')}",
                "- Limitation queries:"]
        out += [f"  - {q}" for q in _strs(sub.get("limitation_search_queries"))]
        out.append(f"- Bridge: {sub.get('bridge_to_our_method', '')}")
    out += ["", "## Section plan"]
    for sec in _dicts(outline.get("section_plan")):
        out += ["", f"### {sec.get('section_title', '')}"]
        for sub in _dicts(sec.get("subsections")):
            out += ["", f"#### {sub.get('subsection_title', '')}", ""]
            out += [f"- {b}" for b in _strs(sub.get("content_bullets"))]
            for label, key in (("Citation hints", "citation_hints"),
                               ("Citation hints (injected)", "citation_hints_injected"),
                               ("Must cite", "must_cite"),
                               ("Citation candidates", "citation_candidates")):
                if _strs(sub.get(key)):
                    out.append(f"- {label}: " + "; ".join(_strs(sub[key])))
    return "\n".join(out) + "\n"


def _task(section: str, focus: str, context: str, search_type: str) -> dict:
    tid = "t" + hashlib.sha1(f"{section}|{focus}".encode()).hexdigest()[:10]
    return {"id": tid, "section": section, "focus": focus, "context": context,
            "search_type": search_type}


def collect_search_tasks(outline: dict) -> list[dict]:
    tasks = []
    plan = _obj(outline.get("intro_related_work_plan"))
    intro = _obj(plan.get("introduction_strategy"))
    for direction in _strs(intro.get("search_directions")):
        tasks.append(_task("Introduction", direction,
                           f"Hook: {intro.get('hook_hypothesis', '')}. "
                           f"Gap: {intro.get('problem_gap_hypothesis', '')}", "exploration"))
    for sub in _dicts(_obj(plan.get("related_work_strategy")).get("subsections")):
        queries = _strs(sub.get("limitation_search_queries")) or [
            f"{sub.get('subsection_title', '')} {sub.get('methodology_cluster', '')}"]
        for q in queries:
            tasks.append(_task(f"Related Work: {sub.get('subsection_title', 'General')}", q,
                               f"Mission: {sub.get('sota_investigation_mission', '')}. "
                               f"Hypothesis: {sub.get('limitation_hypothesis', '')}", "exploration"))
    for section in _dicts(outline.get("section_plan")):
        title = section.get("section_title", "Unknown Section")
        for sub in _dicts(section.get("subsections")):
            context = " ".join(_strs(sub.get("content_bullets")))
            # inject_candidates moves the hints to citation_hints_injected; keep tasks stable
            hints = _strs(sub.get("citation_hints") or sub.get("citation_hints_injected"))
            for hint in hints:
                tasks.append(_task(f"{title} - {sub.get('subsection_title', 'General')}", hint,
                                   f"Must-have citation for section covering: {context}", "targeted"))
    seen: set[str] = set()
    unique = []
    for t in tasks:
        if t["id"] not in seen:
            seen.add(t["id"])
            unique.append(t)
    return unique


def estimate(outline: dict, profile) -> dict:
    tasks = collect_search_tasks(outline)
    figs = _dicts(outline.get("plotting_plan"))
    n_fig = len(figs)
    passes = 1 + profile.revision_rounds
    return {
        "search_tasks": len(tasks),
        "exploration": sum(t["search_type"] == "exploration" for t in tasks),
        "targeted": sum(t["search_type"] == "targeted" for t in tasks),
        "figures": n_fig,
        "plots": sum(f.get("plot_type") == "plot" for f in figs),
        "diagrams": sum(f.get("plot_type") == "diagram" for f in figs),
        "critic_runs_max": n_fig * profile.critic_rounds,
        "review_passes_max": passes,
        "reviewer_runs_max": passes * (profile.reviewers + int(profile.meta_review)),
        "revisions_max": profile.revision_rounds,
    }


def inject_candidates(outline: dict, entries: list[dict]) -> dict:
    by_section: dict[str, list[str]] = {}
    for e in entries:
        keys = by_section.setdefault(e.get("found_in_section", ""), [])
        if e["key"] not in keys:
            keys.append(e["key"])
    if not isinstance(outline.get("intro_related_work_plan"), dict):
        outline["intro_related_work_plan"] = {}
    plan = outline["intro_related_work_plan"]
    if not isinstance(plan.get("introduction_strategy"), dict):
        plan["introduction_strategy"] = {}
    plan["introduction_strategy"]["citation_candidates"] = list(by_section.get("Introduction", []))
    for sub in _dicts(_obj(plan.get("related_work_strategy")).get("subsections")):
        sub["citation_candidates"] = list(
            by_section.get(f"Related Work: {sub.get('subsection_title', 'General')}", []))
    for section in _dicts(outline.get("section_plan")):
        title = section.get("section_title", "Unknown Section")
        for sub in _dicts(section.get("subsections")):
            cands = list(by_section.get(f"{title} - {sub.get('subsection_title', 'General')}", []))
            cands += [k for k in _strs(sub.get("must_cite")) if k not in cands]
            sub["citation_candidates"] = cands
            if "citation_hints" in sub:  # kept, so a literature rerun still finds its targeted tasks
                sub["citation_hints_injected"] = sub.pop("citation_hints")
    return outline


# ---- CLI ----

def _load(paper: Path):
    path = paper / "outline.json"
    if not path.is_file():
        print(f"{path} does not exist; run the outline stage first", file=sys.stderr)
        return None, 2
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as e:
        return {"__invalid__": str(e)}, 1
    if not isinstance(data, dict):
        return {"__invalid__": "the top level must be a JSON object"}, 1
    return data, 0


def _need(paper: Path):
    """The outline for a command that needs a sound file; None after a message on stderr."""
    outline, rc = _load(paper)
    if rc == 1:
        print(f"{paper / 'outline.json'} is invalid: {outline['__invalid__']}", file=sys.stderr)
    return None if rc else outline


def _cmd_validate(args) -> int:
    from .bibimport import load_imports
    from .settings import SettingsError, load_settings
    from .style import StyleError, StyleNotFound, find_style, load_style
    paper = Path(args.paper)
    project = Path(args.project) if args.project else paper.resolve().parent
    outline, rc = _load(paper)
    if rc == 2:
        return 2
    if rc == 1:
        errors = [f"outline.json is invalid: {outline['__invalid__']}"]
    else:
        try:
            s = load_settings(paper)
            style = load_style(find_style(s.style, paper))
        except (SettingsError, StyleNotFound, StyleError) as e:
            print(e, file=sys.stderr)
            return 2
        keys = [r.key for r in load_imports(paper)["must_cite"]]
        errors = validate_outline(outline, style, keys, project)
    emit({"ok": not errors, "errors": errors})
    return 1 if errors else 0


def _cmd_render(args) -> int:
    outline = _need(Path(args.paper))
    if outline is None:
        return 2
    out = Path(args.paper) / "outline.md"
    out.write_text(render_outline_md(outline), encoding="utf-8")
    emit({"written": str(out)})
    return 0


def _cmd_tasks(args) -> int:
    outline = _need(Path(args.paper))
    if outline is None:
        return 2
    tasks = collect_search_tasks(outline)
    out = Path(args.paper) / "references" / "tasks.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(tasks, ensure_ascii=False, indent=2), encoding="utf-8")
    emit({"written": str(out), "tasks": len(tasks)})
    return 0


def _cmd_estimate(args) -> int:
    from .settings import SettingsError, load_settings
    outline = _need(Path(args.paper))
    if outline is None:
        return 2
    try:
        s = load_settings(Path(args.paper))
        profile = dataclasses.replace(s.profile_obj, revision_rounds=s.max_review_rounds)
    except SettingsError as e:
        print(e, file=sys.stderr)
        return 2
    emit(estimate(outline, profile))
    return 0


def _cmd_inject(args) -> int:
    paper = Path(args.paper)
    outline = _need(paper)
    if outline is None:
        return 2
    lib = paper / "references" / "library.json"
    if not lib.is_file():
        print(f"{lib} does not exist; run the literature stage first", file=sys.stderr)
        return 2
    try:
        entries = json.loads(lib.read_text(encoding="utf-8"))
        if not isinstance(entries, list) or not all(isinstance(e, dict) and "key" in e for e in entries):
            raise ValueError("expected a JSON array of entries with a key")
    except ValueError as e:
        print(f"{lib}: {e}", file=sys.stderr)
        return 2
    inject_candidates(outline, entries)
    (paper / "outline.json").write_text(json.dumps(outline, ensure_ascii=False, indent=2),
                                        encoding="utf-8")
    emit({"injected": len(entries)})
    return 0


def register(sub) -> None:
    group = sub.add_parser("outline", help="outline checks and helpers")
    cmds = group.add_subparsers(dest="outline_command")
    for name, fn, h in (("validate", _cmd_validate, "check outline.json"),
                        ("render", _cmd_render, "write outline.md"),
                        ("tasks", _cmd_tasks, "write references/tasks.json"),
                        ("estimate", _cmd_estimate, "estimate the run size"),
                        ("inject", _cmd_inject, "add citation candidates from references/library.json")):
        cmds.add_parser(name, parents=[common_parent()], help=h).set_defaults(func=fn)
