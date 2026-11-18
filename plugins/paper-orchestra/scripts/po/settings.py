"""Per-paper settings, usage profiles and the `po settings` command group."""
import argparse
import re
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .cli import common_parent, emit
from .frontmatter import format_value, parse_frontmatter, parse_value

PLUGIN_DIR = Path(__file__).resolve().parents[2]
HAND_EDITS = ("keep", "revise")
SETTINGS_KEYS = ("style", "cutoff", "blind_review", "language", "profile",
                 "max_review_rounds", "hand_edits", "authors")


@dataclass(frozen=True)
class Profile:
    intro_papers: tuple[int, int]
    related_papers: tuple[int, int]
    critic_rounds: int
    reviewers: int
    meta_review: bool
    revision_rounds: int


PROFILES: dict[str, Profile] = {
    "full": Profile((10, 20), (30, 50), 3, 3, True, 3),
    "light": Profile((5, 10), (15, 25), 1, 1, False, 1),
}


class SettingsError(ValueError):
    pass


@dataclass
class Settings:
    style: str
    cutoff: str
    blind_review: bool
    language: str
    profile: str
    max_review_rounds: int
    hand_edits: str
    authors: list[str] = field(default_factory=list)

    @property
    def profile_obj(self) -> Profile:
        return PROFILES[self.profile]


def _check(cond: bool, key: str, msg: str) -> None:
    if not cond:
        raise SettingsError(f"settings: {key}: {msg}")


def load_settings(paper_dir: Path, today: date | None = None) -> Settings:
    path = Path(paper_dir) / "settings.md"
    data = parse_frontmatter(path.read_text(encoding="utf-8"))[0] if path.exists() else {}
    today = today or date.today()
    profile = data.get("profile", "full")
    _check(profile in PROFILES, "profile", f"must be one of {sorted(PROFILES)}, got {profile!r}")
    cutoff = data.get("cutoff", today.strftime("%Y-%m"))
    m = re.fullmatch(r"(\d{4})-(\d{2})", cutoff) if isinstance(cutoff, str) else None
    _check(bool(m) and 1 <= int(m.group(2)) <= 12, "cutoff", f"must be YYYY-MM, got {cutoff!r}")
    blind = data.get("blind_review", True)
    _check(isinstance(blind, bool), "blind_review", "must be true or false")
    hand_edits = data.get("hand_edits", "keep")
    _check(hand_edits in HAND_EDITS, "hand_edits", f"must be one of {list(HAND_EDITS)}, got {hand_edits!r}")
    rounds = data.get("max_review_rounds", PROFILES[profile].revision_rounds)
    _check(isinstance(rounds, int) and not isinstance(rounds, bool) and rounds >= 0,
           "max_review_rounds", "must be a non-negative integer")
    style, language = data.get("style", "ml-conference"), data.get("language", "English")
    _check(isinstance(style, str) and style != "", "style", "must be a non-empty name")
    _check(isinstance(language, str) and language != "", "language", "must be a non-empty string")
    authors = data.get("authors", [])
    _check(isinstance(authors, list), "authors", "must be a list")
    return Settings(style, cutoff, blind, language, profile, rounds, hand_edits, [str(a) for a in authors])


def write_settings(paper_dir: Path, s: Settings) -> Path:
    """Fill templates/settings.md with the values of `s` and write paper/settings.md."""
    text = (PLUGIN_DIR / "templates/settings.md").read_text(encoding="utf-8")
    for key in SETTINGS_KEYS:
        if key == "max_review_rounds" and s.max_review_rounds == s.profile_obj.revision_rounds:
            text = _drop_line(text, key)  # leave unset so it follows the profile
        else:
            text = _replace_line(text, key, getattr(s, key))
    path = Path(paper_dir) / "settings.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _drop_line(text: str, key: str) -> str:
    return "".join(l for l in text.splitlines(keepends=True) if not l.startswith(f"{key}:"))


def _has_frontmatter(text: str) -> bool:
    lines = text.splitlines()
    return bool(lines) and lines[0].strip() == "---" and any(l.strip() == "---" for l in lines[1:])


def _replace_line(text: str, key: str, value) -> str:
    """Set `key` in front-matter text, keeping comments; append it if absent."""
    lines = text.splitlines()
    new = f"{key}: {format_value(value)}"
    close = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), len(lines))
    for i in range(1, close):
        if lines[i].startswith(f"{key}:"):
            j = i + 1
            while j < close and lines[j].startswith((" ", "\t")):
                j += 1  # drop block-list items of the old value
            lines[i:j] = [new]
            break
    else:
        lines.insert(close, new)
    return "\n".join(lines) + "\n"


def _style_path(s: Settings, paper_dir: Path) -> str:
    from .style import StyleNotFound, find_style
    try:
        return str(find_style(s.style, paper_dir))
    except StyleNotFound as e:
        return f"NOT FOUND: {e}"


def _style_blind_review(s: Settings, paper_dir: Path) -> tuple[bool, list[str]]:
    """The chosen style's blind_review, the default when no --blind-review is given (Ruling P36).

    A style that is not found yet falls back to the general default, with a warning."""
    from .style import StyleNotFound, find_style, load_style
    try:
        return load_style(find_style(s.style, paper_dir)).blind_review, []
    except StyleNotFound as e:
        return s.blind_review, [f"{e}; blind_review is set to {format_value(s.blind_review)}"]


def _cmd_init(args: argparse.Namespace) -> int:
    paper = Path(args.paper)
    if (paper / "settings.md").exists():
        print(f"settings.md already exists in {paper}", file=sys.stderr)
        return 2
    defaults = load_settings(Path(args.paper) / "__none__")
    values = {k: v for k, v in {"style": args.style, "cutoff": args.cutoff,
              "blind_review": None if args.blind_review is None else args.blind_review == "true",
              "profile": args.profile, "hand_edits": args.hand_edits,
              "language": args.language}.items() if v is not None}
    s = Settings(**{**defaults.__dict__, **values})
    warnings: list[str] = []
    if "blind_review" not in values:
        s.blind_review, warnings = _style_blind_review(s, paper)
    if "profile" in values:
        s.max_review_rounds = s.profile_obj.revision_rounds
    try:
        write_settings(paper, s)
        load_settings(paper)
    except SettingsError as e:
        (paper / "settings.md").unlink(missing_ok=True)
        print(e, file=sys.stderr)
        return 2
    emit({"written": str(paper / "settings.md"), "warnings": warnings})
    return 0


def _cmd_show(args: argparse.Namespace) -> int:
    paper = Path(args.paper)
    try:
        s = load_settings(paper)
    except SettingsError as e:
        print(e, file=sys.stderr)
        return 2
    p = s.profile_obj
    emit({**s.__dict__, "profile_values": p.__dict__, "style_path": _style_path(s, paper)})
    return 0


def _cmd_set(args: argparse.Namespace) -> int:
    path = Path(args.paper) / "settings.md"
    if not path.exists():
        print(f"{path} does not exist; run `settings init` first", file=sys.stderr)
        return 2
    if args.key not in SETTINGS_KEYS:
        print(f"unknown setting {args.key!r}; known: {', '.join(SETTINGS_KEYS)}", file=sys.stderr)
        return 2
    old = path.read_text(encoding="utf-8")
    if not _has_frontmatter(old):
        print(f"{path} has no front matter (a leading and a closing '---' line); fix the file first",
              file=sys.stderr)
        return 2
    path.write_text(_replace_line(old, args.key, parse_value(args.value)), encoding="utf-8")
    try:
        load_settings(Path(args.paper))
    except SettingsError as e:
        path.write_text(old, encoding="utf-8")
        print(e, file=sys.stderr)
        return 2
    emit({"set": args.key, "value": parse_value(args.value)})
    return 0


def register(sub) -> None:
    group = sub.add_parser("settings", help="paper settings")
    cmds = group.add_subparsers(dest="settings_command")
    init = cmds.add_parser("init", parents=[common_parent()], help="create settings.md")
    init.add_argument("--style")
    init.add_argument("--cutoff", help="YYYY-MM")
    init.add_argument("--blind-review", choices=["true", "false"])
    init.add_argument("--profile", choices=sorted(PROFILES))
    init.add_argument("--hand-edits", choices=list(HAND_EDITS))
    init.add_argument("--language")
    init.set_defaults(func=_cmd_init)
    show = cmds.add_parser("show", parents=[common_parent()], help="print settings")
    show.set_defaults(func=_cmd_show)
    st = cmds.add_parser("set", parents=[common_parent()], help="change one setting")
    st.add_argument("key")
    st.add_argument("value")
    st.set_defaults(func=_cmd_set)
