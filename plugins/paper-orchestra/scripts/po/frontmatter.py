"""Minimal front-matter reader/writer (a small YAML subset, standard library only)."""
import re

_INT = re.compile(r"-?\d+")


def _split_items(inner: str) -> list[str]:
    """Split on commas that are outside quotes."""
    items, cur, quote = [], "", ""
    for ch in inner:
        if quote:
            quote = "" if ch == quote else quote
        elif ch in "\"'":
            quote = ch
        elif ch == ",":
            items.append(cur)
            cur = ""
            continue
        cur += ch
    return items + [cur]


def parse_value(raw: str):
    """Parse one scalar or inline list."""
    raw = raw.strip()
    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1].strip()
        return [parse_value(p) for p in _split_items(inner)] if inner else []
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
        return raw[1:-1]
    if raw == "true":
        return True
    if raw == "false":
        return False
    if _INT.fullmatch(raw):
        return int(raw)
    return raw


def parse_frontmatter(text: str) -> tuple[dict, str]:
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return {}, text
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        return {}, text
    data: dict = {}
    key = None
    for line in lines[1:end]:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if line.startswith((" ", "\t")) and stripped.startswith("- ") and key is not None:
            if not isinstance(data[key], list):
                data[key] = []
            data[key].append(parse_value(stripped[2:]))
            continue
        name, sep, rest = line.partition(":")
        if not sep:
            continue
        key = name.strip()
        data[key] = parse_value(rest)
    return data, "".join(lines[end + 1:])


def _needs_quotes(s: str) -> bool:
    return (s == "" or s != s.strip() or s[0] in "[\"'#-" or ": " in s or s.endswith(":")
            or " #" in s or s in ("true", "false") or bool(_INT.fullmatch(s)))


def format_value(v) -> str:
    """Render one scalar or inline list for a front-matter line."""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(format_value(x) for x in v) + "]"
    s = str(v)
    return '"' + s + '"' if _needs_quotes(s) or "," in s or "]" in s else s


def dump_frontmatter(data: dict, body: str) -> str:
    lines = ["---"] + [f"{k}: {format_value(v)}" for k, v in data.items()] + ["---"]
    return "\n".join(lines) + "\n" + body
