import pytest
from datetime import date
from po.cli import main
from po.settings import load_settings, PROFILES, Profile, SettingsError

def test_defaults(tmp_path):
    s = load_settings(tmp_path, today=date(2026, 11, 18))
    assert (s.style, s.cutoff, s.blind_review, s.language, s.profile, s.hand_edits) == \
           ("ml-conference", "2026-11", True, "English", "full", "keep")
    assert s.max_review_rounds == 3 and s.authors == []

def test_profiles_exact():
    assert PROFILES["full"] == Profile((10, 20), (30, 50), 3, 3, True, 3)
    assert PROFILES["light"] == Profile((5, 10), (15, 25), 1, 1, False, 1)

def test_validation(tmp_path):
    f = tmp_path / "settings.md"
    f.write_text("---\ncutoff: 2026-13\n---\n")
    with pytest.raises(SettingsError, match="cutoff"): load_settings(tmp_path)
    f.write_text("---\nprofile: light\nhand_edits: revise\n---\n")
    s = load_settings(tmp_path); assert s.max_review_rounds == 1 and s.hand_edits == "revise"
    f.write_text("---\nhand_edits: maybe\n---\n")
    with pytest.raises(SettingsError, match="hand_edits"): load_settings(tmp_path)

def test_cli_init_show(tmp_path, capsys):
    paper = tmp_path / "paper"
    assert main(["settings", "init", "--paper", str(paper), "--profile", "light", "--cutoff", "2026-05"]) == 0
    s = load_settings(paper)
    assert (s.profile, s.cutoff, s.max_review_rounds) == ("light", "2026-05", 1)
    assert main(["settings", "init", "--paper", str(paper)]) == 2
    capsys.readouterr()
    assert main(["settings", "show", "--paper", str(paper)]) == 0
    out = capsys.readouterr().out
    assert '"profile": "light"' in out and "ml-conference.md" in out

def test_cli_set(tmp_path):
    paper = tmp_path / "paper"
    assert main(["settings", "set", "profile", "light", "--paper", str(paper)]) == 2  # no file yet
    main(["settings", "init", "--paper", str(paper)])
    assert main(["settings", "set", "profile", "light", "--paper", str(paper)]) == 0
    assert load_settings(paper).profile == "light"
    before = (paper / "settings.md").read_text()
    assert main(["settings", "set", "hand_edits", "maybe", "--paper", str(paper)]) == 2
    assert (paper / "settings.md").read_text() == before
    assert main(["settings", "set", "bogus", "1", "--paper", str(paper)]) == 2
    assert (paper / "settings.md").read_text() == before

def test_set_profile_follows_profile_rounds(tmp_path):
    paper = tmp_path / "paper"
    main(["settings", "init", "--paper", str(paper)])
    assert main(["settings", "set", "profile", "light", "--paper", str(paper)]) == 0
    assert load_settings(paper).max_review_rounds == 1
    main(["settings", "set", "max_review_rounds", "2", "--paper", str(paper)])
    assert load_settings(paper).max_review_rounds == 2

def test_set_requires_front_matter(tmp_path, capsys):
    paper = tmp_path / "paper"
    paper.mkdir()
    for content in ("", "style: x\n", "---\nstyle: x\n"):
        (paper / "settings.md").write_text(content)
        assert main(["settings", "set", "profile", "light", "--paper", str(paper)]) == 2
        assert (paper / "settings.md").read_text() == content
    assert "front matter" in capsys.readouterr().err


# --- I5 / P36: blind review defaults to the chosen style's value ------------------------------
@pytest.mark.parametrize("style, blind", [("journal", False), ("ml-conference", True)])
def test_init_blind_review_follows_the_style(tmp_path, style, blind):
    paper = tmp_path / "paper"
    assert main(["settings", "init", "--paper", str(paper), "--style", style]) == 0
    assert load_settings(paper).blind_review is blind
    other = tmp_path / "other"  # an explicit flag wins
    assert main(["settings", "init", "--paper", str(other), "--style", style,
                 "--blind-review", "false" if blind else "true"]) == 0
    assert load_settings(other).blind_review is (not blind)


def test_init_blind_review_default_style_own_style_and_unknown_style(tmp_path, capsys):
    import json
    paper = tmp_path / "paper"
    assert main(["settings", "init", "--paper", str(paper)]) == 0  # ml-conference
    assert load_settings(paper).blind_review is True
    own = tmp_path / "own"
    own.mkdir()
    (own / "style.md").write_text("---\nname: mine\nsections: [Abstract]\nlength_words: [100, 200]\n"
                                  "blind_review: false\n---\n")
    assert main(["settings", "init", "--paper", str(own)]) == 0
    assert load_settings(own).blind_review is False
    capsys.readouterr()
    unknown = tmp_path / "unknown"
    assert main(["settings", "init", "--paper", str(unknown), "--style", "my-venue"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert load_settings(unknown).blind_review is True
    assert len(out["warnings"]) == 1 and "my-venue" in out["warnings"][0]
