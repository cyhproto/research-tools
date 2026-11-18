import json
from pathlib import Path

def test_marketplace_lists_plugin():
    m = json.loads(Path(".claude-plugin/marketplace.json").read_text())
    assert m["name"] == "research-tools"
    [p] = m["plugins"]
    assert p["name"] == "paper-orchestra" and p["source"] == "./plugins/paper-orchestra"
    assert Path(p["source"], ".claude-plugin/plugin.json").is_file()

def test_plugin_manifest():
    pj = json.loads(Path("plugins/paper-orchestra/.claude-plugin/plugin.json").read_text())
    assert (pj["name"], pj["version"], pj["license"]) == ("paper-orchestra", "0.1.0", "Apache-2.0")

def test_cli_version(capsys):
    from po.cli import main
    assert main(["version"]) == 0
    assert json.loads(capsys.readouterr().out) == {"version": "0.1.0"}
