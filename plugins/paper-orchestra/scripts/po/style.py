"""Venue style guides: lookup and loading."""
from dataclasses import dataclass
from pathlib import Path

from .frontmatter import parse_frontmatter
from .settings import PLUGIN_DIR

USER_STYLE_DIR = Path("~/.claude/paper-orchestra/styles").expanduser()


class StyleNotFound(FileNotFoundError):
    pass


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


def load_style(path: Path) -> StyleGuide:
    data, body = parse_frontmatter(Path(path).read_text(encoding="utf-8"))
    words = data.get("length_words", [0, 0])
    return StyleGuide(
        name=str(data.get("name", Path(path).stem)),
        sections=list(data.get("sections", [])),
        optional_sections=list(data.get("optional_sections", [])),
        literature_sections=list(data.get("literature_sections", [])),
        length_words=(words[0], words[1]),
        blind_review=bool(data.get("blind_review", False)),
        citation_style=str(data.get("citation_style", "author-year")),
        required_statements=list(data.get("required_statements", [])),
        language=str(data.get("language", "English")),
        body=body,
        path=Path(path),
    )
