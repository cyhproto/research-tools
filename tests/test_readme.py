from pathlib import Path
R = Path("plugins/paper-orchestra/README.md")
HEADS = ["Install", "Requirements", "Optional keys", "Usage", "What it writes", "Profiles and usage limits",
         "Your edits", "Importing your references", "Privacy", "Limitations", "Credits", "License"]

def test_readme():
    t = R.read_text()
    idx = [t.index(f"## {h}") for h in HEADS]; assert idx == sorted(idx)
    for s in ["/plugin install paper-orchestra@research-tools", "OPENALEX_API_KEY", "SEMANTIC_SCHOLAR_API_KEY",
              "same model family", "song2026paperorchestra"]:
        assert s in t, s
