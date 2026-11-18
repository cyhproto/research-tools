"""Merge per-figure meta files and supplied images into figures/info.json."""
import json
import re
import shutil
import sys
from pathlib import Path

from .cli import common_parent, emit
from .materials import FIGURE_EXTS

BAD_CAPTION = re.compile(r"^(Figure|Fig\.)\s*\d")
CAPTION_LINE = re.compile(r"^\s*[-*]\s+(.+?):\s*(\S.*)$")


def _check_caption(label: str, caption, errors: list[str]) -> None:
    if not isinstance(caption, str) or not caption.strip():
        errors.append(f"{label}: empty caption")
    elif BAD_CAPTION.match(caption.strip()):
        errors.append(f"{label}: caption must not start with 'Figure N' or 'Fig. N': {caption!r}")


def collect_figures(paper_dir: Path) -> tuple[list[dict], list[str]]:
    paper = Path(paper_dir)
    info: list[dict] = []
    errors: list[str] = []
    taken: set[str] = set()
    for meta in sorted((paper / "figures/meta").glob("*.json")):
        try:
            m = json.loads(meta.read_text(encoding="utf-8"))
            if not isinstance(m, dict):
                raise ValueError("not an object")
        except (ValueError, OSError) as e:
            errors.append(f"{meta.name}: unreadable meta file ({e})")
            continue
        fid = m.get("id", meta.stem)
        if m.get("kind") not in ("plot", "diagram"):
            errors.append(f"{fid}: kind must be 'plot' or 'diagram'")
        f = m.get("file")
        if not isinstance(f, str) or not (paper / f).is_file():
            errors.append(f"{fid}: figure file missing: {f}")
        else:
            taken.add(Path(f).name)
        _check_caption(fid, m.get("caption"), errors)
        info.append({"id": fid, "kind": m.get("kind"), "file": f, "caption": m.get("caption", ""),
                     "description": m.get("description", ""),
                     "critic_rounds": m.get("critic_rounds", [])})
    src = paper / "materials/figures"
    captions: dict[str, str] = {}
    cap = src / "captions.md"
    if cap.is_file():
        for line in cap.read_text(encoding="utf-8", errors="replace").splitlines():
            mt = CAPTION_LINE.match(line)
            if mt:
                captions[mt.group(1).strip()] = mt.group(2).strip()
    images = sorted(p for p in src.iterdir() if p.is_file() and p.suffix.lower() in FIGURE_EXTS) \
        if src.is_dir() else []
    for name in captions:
        if not (src / name).is_file():
            errors.append(f"{name}: captioned image missing from materials/figures")
    for img in images:
        if img.name in taken:
            errors.append(f"{img.name}: supplied image collides with a generated figure")
            continue
        _check_caption(img.name, captions.get(img.name, ""), errors)
        (paper / "figures").mkdir(exist_ok=True)
        shutil.copy2(img, paper / "figures" / img.name)
        info.append({"id": img.stem, "kind": "supplied", "file": f"figures/{img.name}",
                     "caption": captions.get(img.name, ""), "description": "", "critic_rounds": []})
    (paper / "figures").mkdir(exist_ok=True)
    (paper / "figures/info.json").write_text(json.dumps(info, indent=2, ensure_ascii=False) + "\n",
                                             encoding="utf-8")
    return info, errors


def _cmd_collect(args) -> int:
    info, errors = collect_figures(Path(args.paper))
    emit({"figures": info, "errors": errors})
    for e in errors:
        print(e, file=sys.stderr)
    return 1 if errors else 0


def register(sub) -> None:
    group = sub.add_parser("figures", help="figure collection")
    cmds = group.add_subparsers(dest="figures_command")
    cmds.add_parser("collect", parents=[common_parent()],
                    help="merge meta files and supplied images into figures/info.json"
                    ).set_defaults(func=_cmd_collect)
