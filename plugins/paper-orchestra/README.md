# paper-orchestra

A Claude Code plugin that drafts a research paper in Markdown from your project's code, results and notes. It gathers your materials, plans an outline, searches and verifies the literature, builds figures, writes the sections, runs a simulated peer review, and checks the result. It is a port of Google Research's [PaperOrchestra](https://github.com/google-research/paper-orchestra) to Claude Code agents.

## Install

```
/plugin marketplace add cyhproto/research-tools
/plugin install paper-orchestra@research-tools
```

Update later with:

```
/plugin marketplace update research-tools
```

The command is `/paper-orchestra`. Claude Code resolves it to the plugin's skill, whose full name `/paper-orchestra:paper-orchestra` runs the same command.

## Requirements

- Claude Code, logged in with a Claude subscription, with web search available. You need no Anthropic API key and no other AI provider.
- Python 3.10 or later, as the `python3` on your PATH: the tool runs its scripts with `python3`. The scripts use only the standard library. On macOS the system `python3` is 3.9, so install a newer one, for example with Homebrew (`brew install python`) or uv, and check that `python3 --version` shows 3.10 or later.
- matplotlib in your project's Python environment, or [uv](https://docs.astral.sh/uv/). Only plot figures need it; the tool never installs anything.

## Optional keys

Set these in your shell before starting Claude Code. You create the keys yourself.

- `OPENALEX_API_KEY`: free, and recommended. Requests without a key share a small daily budget, so a big literature search may run out. Papers it could not look up are reported as `lookup-failed`. To look them up again later without searching again, run `/paper-orchestra lit-review` and choose "retry lookups only".
- `SEMANTIC_SCHOLAR_API_KEY`: used only if it is set.

The tool never sends your email or other personal details to these services.

## Usage

Start Claude Code in your project folder and run:

```
/paper-orchestra
```

With no argument it runs the next stage that is not done. It stops twice for you:

1. **After Gather.** It has drafted `materials/idea.md` and `materials/experiment_log.md` from your project. Check and correct them, then say go.
2. **After Outline.** Read `paper/outline.md`, ask for changes, then say go. The size estimate (search tasks, figures, critic, reviewer and revision runs) is shown here, before the expensive stages start. Switch profile now if it is too big.

Then literature and figures run in parallel, followed by Write, Review and Check.

To run one stage, or to inspect progress:

```
/paper-orchestra gather
/paper-orchestra outline
/paper-orchestra lit-review
/paper-orchestra figures
/paper-orchestra write
/paper-orchestra review
/paper-orchestra check
/paper-orchestra status
```

Options:

- `--profile full|light`: the usage profile (see below).
- `--hand-edits keep|revise`: how the review treats paragraphs you edited, for this review only.
- `write --only "<Section>" ["<Section>" ...]`: rewrite only the named sections, for example `write --only "Experiments"` after new results.

Gather asks once for the style (`ml-conference`, `journal`, or your own `paper/style.md`), the cutoff month, blind review, language and author names. Say "defaults" to accept them. Blind review defaults to the style's setting: on for `ml-conference`, off for `journal`.

With the `journal` style, Check says NOT READY until you add the two statements the style requires, "Data and code availability" and "Declaration of competing interests", each as a `##` section before References. No agent writes them, because only you know what they must say.

Re-running a stage that others depend on marks the later stages stale and names the paper sections affected. You choose what to re-run.

## What it writes

Everything goes in `paper/` inside your project, and opens directly in Obsidian.

```
paper/
├── settings.md          style, cutoff, blind review, language, profile, hand edits
├── materials/           idea.md, experiment_log.md, figures/ (your images + captions.md),
│                        references/ (your optional exports)
├── outline.json         the plan; outline.md is the readable view
├── references/          library.json, references.bib, search_log.json, cache.json
├── figures/             <id>.png, <id>.mmd (Mermaid), src/<id>.py, info.json
├── drafts/              every version of the paper
├── reviews/             reviewer reports and revision logs
├── paper.md             the current best draft, with a References section
├── review.md            scores per round, what changed, kept or undone,
│                        experiments reviewers asked for, Check results
└── .state.json          progress, used for resume
```

## Profiles and usage limits

A full run is heavy: dozens of search tasks, a critic loop per figure, and many reviewer runs. Choose a profile in `settings.md` or with `--profile`.

| | `full` (default) | `light` |
|---|---|---|
| Literature budget | Introduction 10-20, Related Work 30-50 papers | Introduction 5-10, Related Work 15-25 papers |
| Figure critic rounds | up to 3 | 1 |
| Reviewers | 3 plus a meta-reviewer | 1, no meta-reviewer |
| Revision rounds | up to 3 | 1 |

The literature budget is set when the outline is planned. Switching to `light` after the outline changes the critic, reviewer and revision counts but not the literature budget; the tool offers to re-plan the outline under the new profile.

Measured usage on the sample run (the TSAM example from the original project, `full` profile, Claude Code 2.1.327; Opus at effort `xhigh` for the session and most agents, Sonnet for the literature scouts and figure critics):

- running time: 32 minutes over three invocations, not counting the two pauses;
- 39 agent runs: 6 literature scouts, 10 figure builds and 10 critic rounds for 4 figures, 6 reviewer and 2 meta-reviewer runs, 1 revision, and one each of the planner, the two writers and the checker;
- about 15 million tokens, mostly cache reads: 12.4 million cache reads, 1.5 million cache writes, 1.0 million other input (mostly web search results) and 0.42 million output;
- Claude Code's estimate at API list prices: about $17. A subscription does not bill this; it shows the scale.

That review stopped after one round, because the revision scored lower and was undone. Each further round adds about 12 minutes and 3 million tokens: 1.4 million for the reviser and the four review agents, and 1.6 million for the session that coordinates them. With all 3 rounds, the `full` profile on this sample comes to about 56 minutes and 21 million tokens.

**If you hit a usage limit**, the run stops with finished work kept. Wait for the limit to reset, then run `/paper-orchestra` again. It continues from the last finished piece (a batch of searches, a figure, a review, a revision) and never redoes finished work.

## Your edits

`paper.md` is yours to edit. The tool finds your edits paragraph by paragraph, by comparing it with the last version it wrote. Text in a `paper.md` that existed before the tool first wrote to it counts as yours, and so does all of `paper.md` if `paper/.state.json` (where the tool records its versions) is lost.

- **Reruns** replace only the sections that stage owns: Introduction and Related Work (lit-review); Title, Abstract, Method, Experiments, Conclusion, Limitations and Appendix (write); References (script). If a section to be replaced has your edits, it asks for each one: replace it, keep yours, or save the new text beside it in `drafts/<Section>-new.md` to merge by hand.
- **Review** has two modes, set by `hand_edits` in `settings.md` or `--hand-edits`:
  - `keep` (default): your edited paragraphs stay exactly as written, and a script restores any the reviser changed. Reviewer comments on them go to `review.md` as suggestions for you.
  - `revise`: the reviser may rewrite them too, and every change is listed in `review.md` (before and after).
- Accepting a review revision never silently drops your edits. If you edited `paper.md` during a review, it shows the affected paragraphs and asks first. Your version is always saved in `drafts/`.
- Re-running Gather, Outline or Figures never changes `paper.md`.
- **References** is rebuilt from `references/library.json` at every write and review, so a hand edit to a reference line is replaced. Correct the entry in `references/library.json` instead; the correction survives later `refs verify` runs, unless you start the library fresh when re-running Literature. Must-cite papers are the exception: their entries are rebuilt from your `must_cite.bib` and the online lookup at every `refs verify`, and the lookup's title, authors, year and venue win, so correct them again after each Literature run. Other text you write under `## References` is kept after the list, and Check asks you to give it its own heading.

## Importing your references

Put exports from your reference manager (BibTeX or CSL JSON) in `paper/materials/references/`:

- `library.bib` or `library.json`: papers that supply abstracts.
- `must_cite.bib` or `must_cite.json`: papers that are always cited. They keep your own citation keys.

Papers without an abstract are kept as title-only: the paper may say only what their title and venue support.

## Privacy

Search queries reveal the topic keywords of your work to the search services (OpenAlex, Semantic Scholar, Crossref and web search). Nothing else leaves your machine except to Claude itself. API responses are treated as data, never as instructions.

## Limitations

- The reviewers are the same model family as the writer. Their scores are a relative signal for keeping or undoing a revision, not a prediction of acceptance.
- Numbers like `1.2M` are not checked against your logs.
- Diagrams are Mermaid, not publication artwork.
- The literature budget is set at outline time.
- The paper is a draft. Read it, check every claim and citation, and edit it before you share it.

## Credits

Based on PaperOrchestra by Google Research. Please cite the paper:

```bibtex
@article{song2026paperorchestra,
  title={PaperOrchestra: A Multi-Agent Framework for Automated AI Research Paper Writing},
  author={Song, Yiwen and Song, Yale and Pfister, Tomas and Yoon, Jinsung},
  journal={arXiv preprint arXiv:2604.05018},
  year={2026}
}
```

This is not an officially supported Google product.

## License

Apache-2.0; see `LICENSE`. Portions are adapted from PaperOrchestra (Copyright 2026 Google LLC, Apache-2.0); see `NOTICE` for the modifications.
