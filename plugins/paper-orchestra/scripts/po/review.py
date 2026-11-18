"""Review scoring, keep-or-undo, hand-edit protection and review.md.

Bookkeeping files written under <paper>/reviews/ (all JSON, read by `render`):
  review_v<K>.json     aggregate of the reviews of draft v<K> (`aggregate`)
  protected_v<K>.json  {id: paragraph text} map of the marked draft (`protect`)
  rounds.json          [{version, overall_before, overall_after, outcome}], one
                       entry per version, written by `decide --record K`
  restorations.json    {"v<K>": [{id, action}]}, replaced per version by `restore`
  changes_v<K>.json    [{before, after}] for the protected paragraphs a revise-mode
                       revision of v<K> changed (`changes`; K comes from the
                       map's name, protected_v<K>.json; after is null when removed).
                       `render` labels them, and the restorations, with the
                       candidate version K+1 and that round's outcome
  worklog_v<K>.json    the reviser's worklog for the round on v<K>, with keys
                       addressed_weaknesses, integrated_answers, actions_taken,
                       experiments_requested, suggestions_for_protected
"""
import json
import re
import statistics
import sys
from difflib import SequenceMatcher
from pathlib import Path

from .cli import common_parent, emit
from .paper import _collapse, _read, _write, assemble, paragraphs, split_sections, tool_baseline
from .state import get_protected, set_protected

SCORE_FIELDS = {"Originality": (1, 4), "Quality": (1, 4), "Clarity": (1, 4), "Significance": (1, 4),
                "Soundness": (1, 4), "Presentation": (1, 4), "Contribution": (1, 4),
                "Overall": (1, 10), "Confidence": (1, 5)}
COMPARE_AXES = [k for k in SCORE_FIELDS if k not in ("Overall", "Confidence")]
WORKLOG_KEYS = ["addressed_weaknesses", "integrated_answers", "actions_taken",
                "experiments_requested", "suggestions_for_protected"]
FUZZY = 0.6

JSON_BLOCK_RE = re.compile(r"```json[ \t]*\r?\n(.*?)```", re.S | re.I)
KEEP_RE = re.compile(r"<!-- po:keep (\d+) -->\s*(.*?)\s*<!-- /po:keep \1 -->", re.S)
MARKER_RE = re.compile(r"[ \t]*<!-- /?po:keep \d+ -->[ \t]*\n?")
HEADINGS = ["## Review rounds", "## What changed", "## Experiments reviewers asked for",
            "## Suggestions for your edited paragraphs", "## Changes to your edited paragraphs",
            "## Protected paragraphs", "## Check"]


# ---- scoring -------------------------------------------------------------

def parse_review(text: str) -> dict:
    """First fenced json block after `REVIEW JSON:`, else the first fenced json block."""
    i = text.find("REVIEW JSON:")
    m = JSON_BLOCK_RE.search(text, i) if i >= 0 else None
    m = m or JSON_BLOCK_RE.search(text)
    if not m:
        raise ValueError("no fenced json block found")
    data = json.loads(m.group(1))
    if not isinstance(data, dict):
        raise ValueError("review json is not an object")
    return data


def _as_int(v) -> int | None:
    """int(v) as the original does; None when that fails (bools and None included)."""
    if isinstance(v, bool) or v is None:
        return None
    try:
        return int(v)
    except (ValueError, TypeError, OverflowError):
        return None


def aggregate(reviews: list[dict], meta: dict | None) -> dict:
    text_src = meta if meta is not None else (reviews[0] if reviews else {})
    out = {k: v for k, v in text_src.items() if k not in SCORE_FIELDS}
    for field, (lo, hi) in SCORE_FIELDS.items():
        vals = [v for v in (_as_int(r.get(field)) for r in reviews) if v is not None and lo <= v <= hi]
        if vals:
            out[field] = round(statistics.mean(vals))
    return out


def decide(old: dict, new: dict) -> dict:
    def num(d, k):
        v = _as_int(d.get(k))
        return 0 if v is None else v

    deltas = {k: num(new, k) - num(old, k) for k in COMPARE_AXES}
    gain = sum(d for d in deltas.values() if d > 0)
    drop = sum(-d for d in deltas.values() if d < 0)
    o, n = num(old, "Overall"), num(new, "Overall")
    if n > o:
        outcome = "ACCEPTED_SCORE_INCREASE"
    elif n < o:
        outcome = "REJECTED_SCORE_DECREASE"
    elif gain >= drop:
        outcome = "ACCEPTED_NEUTRAL_IMPROVEMENT"
    else:
        outcome = "REJECTED_DEGRADATION"
    return {"outcome": outcome, "deltas": deltas, "total_gain": gain, "total_drop": drop}


# ---- protection ----------------------------------------------------------

def protected_set(current_md: str, tool_md: str | None, previous: list[str]) -> list[str]:
    """Hand-edited paragraphs (vs tool_md; "" makes every paragraph the user's), plus the
    previously protected ones still present. tool_md None detects nothing new."""
    from .paper import hand_edited_paragraphs
    edited = hand_edited_paragraphs(current_md, tool_md) if tool_md is not None else []
    present = {_collapse(p): p for p in paragraphs(current_md)}
    out, seen = [], set()
    for p in list(edited) + [present[_collapse(q)] for q in previous if _collapse(q) in present]:
        c = _collapse(p)
        if c not in seen:
            seen.add(c)
            out.append(p)
    return out


def _spans(text: str) -> list[tuple[int, int, str]]:
    """(start, end, paragraph) of every paragraph of text, found in order."""
    out, pos = [], 0
    for p in paragraphs(text):
        i = text.find(p, pos)
        if i < 0:
            continue
        out.append((i, i + len(p), p))
        pos = i + len(p)
    return out


def _block(i, text: str) -> str:
    return f"<!-- po:keep {i} -->\n{text}\n<!-- /po:keep {i} -->"


def strip_markers(md: str) -> str:
    return MARKER_RE.sub("", md)


def protect(md: str, protected: list[str]) -> tuple[str, dict[str, str]]:
    md = md.replace("\r\n", "\n")
    want = {_collapse(p) for p in protected}
    out, last, n = [], 0, 0
    originals: dict[str, str] = {}
    for s, e, p in _spans(md):
        c = _collapse(p)
        if c in want:
            n += 1
            originals[str(n)] = p
            out += [md[last:s], _block(n, p)]
            last = e
    out.append(md[last:])
    return "".join(out), originals


def _best(target: str, cands: list[tuple[int, int, str]], used: set[int]):
    """Index and ratio of the candidate paragraph most like target."""
    t = _collapse(target)
    best, ratio = None, 0.0
    for j, (_, _, p) in enumerate(cands):
        if j in used:
            continue
        r = SequenceMatcher(None, t, _collapse(p)).ratio()
        if r > ratio:
            best, ratio = j, r
    return best, ratio


def _plain(p: str) -> str:
    return strip_markers(p)


def restore(revised_md: str, originals: dict[str, str], pre_revision_md: str) -> tuple[str, list[dict]]:
    crlf = "\r\n" in revised_md
    text = revised_md.replace("\r\n", "\n")
    pre = strip_markers(pre_revision_md.replace("\r\n", "\n"))
    actions: list[dict] = []
    seen_text: dict[str, int] = {}
    for id_ in sorted(originals, key=int):
        orig = originals[id_]
        occ = seen_text.get(_collapse(orig), 0)
        seen_text[_collapse(orig)] = occ + 1
        action = None
        # 1. markers present
        m = next((m for m in KEEP_RE.finditer(text) if m.group(1) == id_), None)
        if m:
            action = "unchanged" if _collapse(m.group(2)) == _collapse(orig) else "restored"
            text = text[:m.start()] + _block(id_, orig) + text[m.end():]
        else:
            # 2. markers absent: best paragraph
            cands = [c for c in _spans(text) if "po:keep" not in c[2]]
            j, r = _best(orig, cands, set())
            if j is not None and r >= FUZZY:
                s, e, p = cands[j]
                action = "unchanged" if _collapse(p) == _collapse(orig) else "restored-fuzzy"
                text = text[:s] + _block(id_, orig) + text[e:]
            else:
                # 3. reinsert
                text, action = _reinsert(text, id_, orig, pre, occ)
        actions.append({"id": id_, "action": action})
    text = strip_markers(text)
    return (text.replace("\n", "\r\n") if crlf else text), actions


def _locate(pre: str, orig: str, occ: int):
    """(section name, paragraphs of that section, index) of the occ-th copy of orig in pre."""
    o, seen = _collapse(orig), 0
    _, secs = split_sections(pre)
    for s in secs:
        paras = paragraphs(s.text)
        for k, p in enumerate(paras):
            if _collapse(p) == o:
                if seen == occ:
                    return s.name, paras, k
                seen += 1
    return None


def _reinsert(text: str, id_: str, orig: str, pre: str, occ: int = 0) -> tuple[str, str]:
    loc = _locate(pre, orig, occ)
    if loc is None:
        return text, "missing"
    name, paras, idx = loc
    block = _block(id_, orig)
    preamble, secs = split_sections(text)
    sec = next((s for s in secs if s.name == name), None)
    if sec is None:
        return text, "missing"
    if idx > 0:
        prev = _collapse(paras[idx - 1])
        cands = [(s, e, _plain(p)) for s, e, p in _spans(sec.text)]
        j = next((k for k, c in enumerate(cands) if _collapse(c[2]) == prev), None)
        if j is None:
            j, r = _best(paras[idx - 1], cands, set())
            if r < FUZZY:
                j = None
        if j is not None:
            e = cands[j][1]
            sec.text = sec.text[:e] + "\n\n" + block + sec.text[e:]
        else:
            sec.text = sec.text.rstrip("\n") + "\n\n" + block + "\n" + ("\n" if sec is not secs[-1] else "")
    else:
        body = sec.text.lstrip("\n")
        sec.text = "\n\n" + block + ("\n\n" + body if body else "\n")
    return assemble(preamble, secs), "reinserted"


def changed_protected(revised_md: str, originals: dict[str, str]) -> list[dict]:
    """Changed protected paragraphs; `after` is None when the paragraph was removed (its marker
    pair emptied, or marker and text both deleted).

    A paragraph whose markers were dropped but whose text is still present verbatim is unchanged."""
    text = revised_md.replace("\r\n", "\n")
    found = {m.group(1): m.group(2) for m in KEEP_RE.finditer(text)}
    present = {_collapse(p) for p in paragraphs(strip_markers(text))}
    out = []
    for id_ in sorted(originals, key=int):
        orig = originals[id_]
        if id_ not in found:
            if _collapse(orig) not in present:
                out.append({"before": orig, "after": None})
        elif _collapse(found[id_]) != _collapse(orig):
            out.append({"before": orig, "after": found[id_] if found[id_].strip() else None})
    return out


# ---- review.md -----------------------------------------------------------

def _dedup(items: list[str]) -> list[str]:
    seen, out = set(), []
    for i in items:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out


def _bullets(items: list[str], empty: str) -> str:
    return "\n".join(f"- {i}" for i in items) if items else empty


def _change_lines(changes: list[dict], rounds: list[dict]) -> list[str]:
    """`version` of a change is the candidate it belongs to; its round outcome says if it stuck."""
    outcome = {r.get("version"): str(r.get("outcome", "")) for r in rounds}
    out = []
    for c in changes:
        o = outcome.get(c.get("version"), "")
        status = ("kept" if o.startswith("ACCEPTED") else
                  "undone, not applied" if o.startswith("REJECTED") else "not decided yet")
        after = c.get("after")
        removed = after is None or not str(after).strip()
        out.append(f"- Round v{c.get('version')} ({status}): "
                   + ("paragraph removed." if removed else "paragraph rewritten."))
        out.append(f"  - Before: {_collapse(str(c.get('before', '')))}")
        if not removed:
            out.append(f"  - After: {_collapse(str(after))}")
    return out


def render_review_md(rounds: list[dict], todo: list[str], suggestions: list[str],
                     restorations: list[dict], check_md: str | None,
                     changes: list[dict] | None = None) -> str:
    kept = lambda r: str(r.get("outcome", "")).startswith("ACCEPTED")
    table = ["| Round | Overall before | Overall after | Outcome |", "| --- | --- | --- | --- |"]
    table += [f"| v{r['version']} | {r.get('overall_before')} | {r.get('overall_after')} | {r.get('outcome')} |"
              for r in rounds]
    changed = []
    for r in rounds:
        verdict = "kept" if kept(r) else "undone"
        changed.append(f"- Round v{r['version']}: revision {verdict} ({r.get('outcome')}).")
        changed += [f"  - {a}" for a in r.get("actions_taken", [])]
    acts = [r for r in restorations if r.get("action") != "unchanged"]
    prot = [f"- Paragraph {r.get('id')}"
            + (f" (round v{r['version']})" if r.get("version") is not None else "")
            + f": {r.get('action')}" for r in acts]
    n_same = len(restorations) - len(acts)
    prot_body = _bullets(prot, "No protected paragraph needed repair." if restorations else "None.")
    if n_same:
        prot_body += f"\n\n{n_same} protected paragraph(s) came back unchanged."
    parts = [
        "# Review\n",
        "## Review rounds\n\n" + "\n".join(table) if rounds else "## Review rounds\n\nNo review rounds yet.",
        "## What changed\n\n" + ("\n".join(changed) if changed else "Nothing yet."),
        "## Experiments reviewers asked for\n\n" + _bullets(_dedup(todo), "None."),
        "## Suggestions for your edited paragraphs\n\n" + _bullets(_dedup(suggestions), "None."),
        "## Changes to your edited paragraphs\n\n" + ("\n".join(_change_lines(changes or [], rounds)) or "None."),
        "## Protected paragraphs\n\n" + prot_body,
        "## Check\n\n" + ((check_md or "").strip("\n") or "Not run yet."),
    ]
    return "\n\n".join(parts) + "\n"


def _existing_check(review_md: str) -> str | None:
    m = re.search(r"^## Check[ \t]*\n(.*?)(?=^## |\Z)", review_md, re.S | re.M)
    body = m.group(1).strip("\n") if m else ""
    return None if not body or body == "Not run yet." else body


# ---- CLI -----------------------------------------------------------------

def _load(p: Path, default):
    if not p.is_file():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        return default


def _dump(p: Path, obj) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _resolve(paper: Path, s: str, must_exist: bool = True) -> Path:
    p = Path(s)
    if p.is_absolute() or (must_exist and p.exists()):
        return p
    return paper / p


def _version_of(path: Path) -> int | None:
    m = re.search(r"_v(\d+)", path.name)
    return int(m.group(1)) if m else None


def _cmd_aggregate(args) -> int:
    paper = Path(args.paper)
    d = paper / "reviews" / f"v{args.version}"
    files = sorted(d.glob("r*.md"), key=lambda p: (len(p.stem), p.stem))
    if not files:
        print(f"no review files in {d}", file=sys.stderr)
        return 2
    try:
        reviews = []
        for f in files:
            reviews.append(parse_review(_read(f)))
        meta = None
        mf = d / "meta.md"
        if mf.is_file():
            f = mf
            meta = parse_review(_read(mf))
    except ValueError as e:
        print(f"{f}: {e}", file=sys.stderr)
        return 2
    agg = aggregate(reviews, meta)
    _dump(paper / "reviews" / f"review_v{args.version}.json", agg)
    emit({"version": args.version, "reviews": len(reviews), "aggregate": agg})
    return 0


def _cmd_decide(args) -> int:
    paper = Path(args.paper)
    try:
        old = json.loads(_read(_resolve(paper, args.old)))
        new = json.loads(_read(_resolve(paper, args.new)))
        if not isinstance(old, dict) or not isinstance(new, dict):
            raise ValueError("a review aggregate must be a JSON object")
    except (OSError, ValueError) as e:
        print(f"cannot read review aggregate: {e}", file=sys.stderr)
        return 2
    res = decide(old, new)
    if args.record is not None:
        p = paper / "reviews" / "rounds.json"
        rounds = [r for r in _load(p, []) if r.get("version") != args.record]
        rounds.append({"version": args.record, "overall_before": old.get("Overall"),
                       "overall_after": new.get("Overall"), "outcome": res["outcome"]})
        _dump(p, sorted(rounds, key=lambda r: r["version"]))
    emit(res)
    return 0


def _cmd_protect(args) -> int:
    paper = Path(args.paper)
    out = Path(args.out)
    out = out if out.is_absolute() else paper / out
    k = _version_of(out)
    if k is None:
        print("--out must be named like drafts/marked_v<K>.md", file=sys.stderr)
        return 2
    pm = paper / "paper.md"
    if not pm.is_file():
        print(f"{pm} not found", file=sys.stderr)
        return 2
    md = _read(pm)
    prot = protected_set(md, tool_baseline(paper, md), get_protected(paper))
    marked, originals = protect(md, prot)
    out.parent.mkdir(parents=True, exist_ok=True)
    _write(out, marked)
    _dump(paper / "reviews" / f"protected_v{k}.json", originals)
    set_protected(paper, prot)
    emit({"marked": str(out), "protected": len(originals)})
    return 0


def _cmd_restore(args) -> int:
    paper = Path(args.paper)
    cand, mp, pre = (_resolve(paper, s) for s in (args.candidate, args.map, args.pre))
    try:
        originals = json.loads(_read(mp))
        text, acts = restore(_read(cand), originals, _read(pre))
    except (OSError, ValueError) as e:
        print(f"restore failed: {e}", file=sys.stderr)
        return 2
    _write(cand, text)
    v = _version_of(mp)
    log = paper / "reviews" / "restorations.json"
    data = _load(log, {})
    data = data if isinstance(data, dict) else {}
    data[f"v{v}" if v is not None else "unversioned"] = acts
    _dump(log, data)
    emit({"actions": acts})
    return 0


def _cmd_changes(args) -> int:
    paper = Path(args.paper)
    cand, mp = _resolve(paper, args.candidate), _resolve(paper, args.map)
    k = _version_of(mp)
    if k is None:
        print("--map must be named like reviews/protected_v<K>.json (K names changes_v<K>.json)",
              file=sys.stderr)
        return 2
    try:
        originals = json.loads(_read(mp))
        text = _read(cand)
    except (OSError, ValueError) as e:
        print(f"changes failed: {e}", file=sys.stderr)
        return 2
    changes = changed_protected(text, originals)
    _write(cand, strip_markers(text))
    out = paper / "reviews" / f"changes_v{k}.json"
    _dump(out, changes)
    emit({"changes": changes, "written": str(out)})
    return 0


def _load_changes(rev: Path) -> list[dict]:
    """Changes from every changes_v<K>.json, labelled with the candidate version K+1."""
    out = []
    files = [(k, f) for f in rev.glob("changes_v*.json") if (k := _version_of(f)) is not None]
    for k, f in sorted(files):
        data = _load(f, [])
        if isinstance(data, list):
            out += [{**c, "version": k + 1} for c in data if isinstance(c, dict)]
    return out


def _cmd_render(args) -> int:
    paper = Path(args.paper)
    rev = paper / "reviews"
    rounds = _load(rev / "rounds.json", [])
    resto = _load(rev / "restorations.json", {})
    if isinstance(resto, dict):  # keyed by the protected draft v<K>; label with its candidate K+1
        resto = [{"version": int(k[1:]) + 1 if k[1:].isdigit() else None, **a}
                 for k, v in sorted(resto.items(), key=lambda kv: (len(kv[0]), kv[0])) for a in v]
    else:
        resto = []
    todo, sugg = [], []
    for r in rounds:
        wl = _load(rev / f"worklog_v{r['version']}.json", {})
        if isinstance(wl, dict):
            r["actions_taken"] = list(wl.get("actions_taken", []))
            todo += wl.get("experiments_requested", [])
            sugg += wl.get("suggestions_for_protected", [])
    target = paper / "review.md"
    check = _existing_check(_read(target)) if target.is_file() else None
    _write(target, render_review_md(rounds, todo, sugg, resto, check, _load_changes(rev)))
    emit({"review": str(target), "rounds": len(rounds)})
    return 0


def register(sub) -> None:
    group = sub.add_parser("review", help="review scores, keep-or-undo, protection, review.md")
    cmds = group.add_subparsers(dest="review_command")
    a = cmds.add_parser("aggregate", parents=[common_parent()], help="average the reviews of draft vK")
    a.add_argument("--version", type=int, required=True)
    a.set_defaults(func=_cmd_aggregate)
    d = cmds.add_parser("decide", parents=[common_parent()], help="keep or undo a revision")
    d.add_argument("--old", required=True)
    d.add_argument("--new", required=True)
    d.add_argument("--record", type=int, default=None, metavar="K",
                   help="append the round for draft vK to reviews/rounds.json")
    d.set_defaults(func=_cmd_decide)
    p = cmds.add_parser("protect", parents=[common_parent()], help="write a marked draft")
    p.add_argument("--out", required=True)
    p.set_defaults(func=_cmd_protect)
    r = cmds.add_parser("restore", parents=[common_parent()], help="repair changed protected paragraphs")
    for flag in ("--candidate", "--map", "--pre"):
        r.add_argument(flag, required=True)
    r.set_defaults(func=_cmd_restore)
    c = cmds.add_parser("changes", parents=[common_parent()],
                        help="list changed protected paragraphs and save reviews/changes_v<K>.json")
    c.add_argument("--candidate", required=True)
    c.add_argument("--map", required=True, help="reviews/protected_v<K>.json; its K names the output")
    c.set_defaults(func=_cmd_changes)
    cmds.add_parser("render", parents=[common_parent()], help="write review.md").set_defaults(func=_cmd_render)
