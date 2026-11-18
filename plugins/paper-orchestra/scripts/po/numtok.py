"""Number tokens: find the numbers in prose and compare them with source values."""
import re
from dataclasses import dataclass

_BODY = r"(?:(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|\.\d+)(?:[eE][-+]?\d+)?%?"
_NUM_RE = re.compile(_BODY)
_SIGNS = "-−+"
_SIGN_OK_AFTER = set("([=:,/")


@dataclass(frozen=True)
class Num:
    value: float
    decimals: int
    percent: bool
    token: str
    start: int
    end: int


def _is_name_char(c: str) -> bool:
    return c.isalpha() or c == "_"


def _ratio_x(text: str, e: int, body: str) -> bool:
    """A ratio written "3.2x" (read like "3.2×"): one x or X right after the number, then no
    letter or digit, so "512x512", "0x1F" and "3.2xl" stay names."""
    return (text[e] in "xX" and not body.endswith("%")
            and (e + 1 == len(text) or not (_is_name_char(text[e + 1]) or text[e + 1].isdigit())))


def find_numbers(text: str) -> list[Num]:
    out: list[Num] = []
    for m in _NUM_RE.finditer(text):
        s, e = m.start(), m.end()
        body = m.group()
        if s > 0:
            prev = text[s - 1]
            if _is_name_char(prev) or prev.isdigit():
                continue
            if prev in "-." and s > 1 and text[s - 2].isalpha():
                continue
            if body.startswith(".") and prev == ".":
                continue
        if e < len(text) and _is_name_char(text[e]) and not _ratio_x(text, e, body):
            continue
        start = s
        sign = 1.0
        if s > 0 and text[s - 1] in _SIGNS:
            before = text[s - 2] if s > 1 else None
            if before is None or before.isspace() or before in _SIGN_OK_AFTER:
                start = s - 1
                if text[s - 1] in "-−":
                    sign = -1.0
        percent = body.endswith("%")
        raw = body.rstrip("%").replace(",", "")
        mantissa = re.split(r"[eE]", raw)[0]
        decimals = len(mantissa.split(".")[1]) if "." in mantissa else 0
        out.append(Num(sign * float(raw), decimals, percent, text[start:e], start, e))
    return out


def is_trivial(n: Num) -> bool:
    return n.decimals == 0 and not n.percent and "." not in n.token and \
        "e" not in n.token.lower() and abs(n.value) < 10


def values_match(written: float, decimals: int, source: float) -> bool:
    return abs(written - source) <= 0.5 * 10 ** -decimals + 1e-9
