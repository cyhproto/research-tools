"""Venue style guides: lookup and loading."""
from dataclasses import dataclass
from pathlib import Path

from .frontmatter import parse_frontmatter
from .settings import PLUGIN_DIR

USER_STYLE_DIR = Path("~/.claude/paper-orchestra/styles").expanduser()


CITATION_STYLES = ("author-year", "numbered")


class StyleNotFound(FileNotFoundError):
    pass


class StyleError(ValueError):
    """A style file that cannot be used; the message names the file and the problem."""


@dataclass
class StyleGuide:
    name: str
    sections: list[str]
    optional_sections: list[str]
    literature_sections: list[str]
    length_words: tuple[int, int]
    blind_review: bool
    citation_style: str
    required_statements: list[str]
    language: str
    body: str
    path: Path


def find_style(name: str, paper_dir: Path, user_dir: Path = USER_STYLE_DIR,
               plugin_dir: Path = PLUGIN_DIR) -> Path:
    candidates = [Path(paper_dir) / "style.md", Path(user_dir) / f"{name}.md",
                  Path(plugin_dir) / "styles" / f"{name}.md"]
    for c in candidates:
        if c.is_file():
            return c
    raise StyleNotFound(f"style {name!r} not found; searched: " + ", ".join(str(c) for c in candidates))


def _names(data: dict, key: str, required: bool, fail) -> list[str]:
    v = data.get(key, None if required else [])
    if not (isinstance(v, list) and all(isinstance(x, str) and x.strip() for x in v)) or (required and not v):
        fail(f"{key} must be a list of section names, such as [Abstract, Introduction], got {v!r}")
    return list(v)


def load_style(path: Path) -> StyleGuide:
    """Load a style guide; raises StyleError, naming the file, when its front matter is unusable."""
    path = Path(path)

    def fail(msg: str):
        raise StyleError(f"style file {path}: {msg}")

    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as e:
        fail(f"not valid UTF-8 ({e}); save it as UTF-8")
    data, body = parse_frontmatter(text)

    if not data:
        fail("no front matter: start the file with a '---' line, then the settings, then a closing '---' line")
    sections = _names(data, "sections", True, fail)
    lists = {k: _names(data, k, False, fail) for k in ("optional_sections", "literature_sections",
                                                       "required_statements")}
    words = data.get("length_words")
    if not (isinstance(words, list) and len(words) == 2
            and all(isinstance(w, int) and not isinstance(w, bool) and w >= 0 for w in words)
            and words[0] <= words[1]):
        fail(f"length_words must be two whole numbers [min, max] with min <= max, such as [5500, 7500], got {words!r}")
    blind = data.get("blind_review", False)
    if not isinstance(blind, bool):
        fail(f"blind_review must be true or false, got {blind!r}")
    citation = data.get("citation_style", "author-year")
    if citation not in CITATION_STYLES:
        fail(f"citation_style must be one of {', '.join(CITATION_STYLES)}, got {citation!r}")
    return StyleGuide(
        name=str(data.get("name", path.stem)),
        sections=sections,
        optional_sections=lists["optional_sections"],
        literature_sections=lists["literature_sections"],
        length_words=(words[0], words[1]),
        blind_review=blind,
        citation_style=citation,
        required_statements=lists["required_statements"],
        language=str(data.get("language", "English")),
        body=body,
        path=path,
    )
