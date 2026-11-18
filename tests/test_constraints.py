import ast, re, sys
from pathlib import Path
PLUGIN = Path("plugins/paper-orchestra")
FORBIDDEN = re.compile(r"gemini|openai|generativelanguage|google\.genai|anthropic|ANTHROPIC_API_KEY", re.I)

def test_no_other_providers():
    roots = ["scripts", "agents", "skills", "styles", "prompts", "templates"]
    hits = [str(f) for r in roots if (PLUGIN / r).is_dir() for f in (PLUGIN / r).rglob("*")
            if f.is_file() and f.suffix in {".py", ".md", ".json"} and FORBIDDEN.search(f.read_text(errors="ignore"))]
    assert hits == []

def test_scripts_use_stdlib_only():
    allowed = set(sys.stdlib_module_names) | {"po"}
    for f in (PLUGIN / "scripts").rglob("*.py"):
        for node in ast.walk(ast.parse(f.read_text())):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else \
                    [node.module] if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module else []
            for n in names:
                assert n.split(".")[0] in allowed, f"{f}: third-party import {n}"
