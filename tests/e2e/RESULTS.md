# End-to-end results

## TSAM sample run (Task 21; spec §13 items 1, 7 and 8)

Run on 2026-11-18. Result: **pass**. `python3 tests/e2e/assert_sample.py .e2e/tsam/paper` exits 0:

```
OK: all checks passed; references=46 figures=5 plots=3 review_rounds_with_outcome=1
```

### Setup

- **Fixture:** `tests/fixtures/tsam/paper/`, built from the original's `frontend/examples/cvpr_example.json`:
  - `materials/idea.md` and `materials/experiment_log.md`;
  - `materials/figures/tsam_overview.png` with `captions.md`;
  - `settings.md`: `ml-conference`, cutoff `2024-11`, blind review, profile `full`, hand edits `keep`.
- **Claude Code and models:** Claude Code 2.1.327, logged in with a Claude subscription, `ANTHROPIC_API_KEY` unset. The main model was `claude-opus-5-5` (user settings: model `opus`, effort `xhigh`). `literature-scout` and `figure-critic` ran on `claude-sonnet-5-5`, and the web searches were billed to `claude-haiku-5-5`.
- **Plugin loading:** with `--plugin-dir plugins/paper-orchestra` for each session; it was not installed. The nested sessions also ran without the calling session's `CLAUDE*` variables (such as `CLAUDE_EFFORT`), so they behaved like a session started from a terminal.
- **Keys and plotting:** no `OPENALEX_API_KEY` or `SEMANTIC_SCHOLAR_API_KEY`. Plots ran through `uv run --no-project --with matplotlib --with numpy` (an ephemeral environment).
- **Command,** run in `.e2e/tsam/` (a copy of the fixture):

  ```
  claude -p "/paper-orchestra" --plugin-dir <plugin> --output-format json \
    --permission-mode acceptEdits --allowedTools "Bash Read Write Edit Glob Grep WebSearch WebFetch Agent"
  ```

  At each pause: `claude -p --continue "<answer>"` with the same flags. `Agent` is the subagent tool's name in this version. No invocation had a permission denial.

### Command name and agent names

- **Slash form** (headless, in empty folders): `/paper-orchestra status` and `/paper-orchestra:paper-orchestra status` both expand the skill directly. Claude Code records the short form as `/paper-orchestra:paper-orchestra`, and neither form needs a Skill tool call. Users type `/paper-orchestra`; README and SKILL.md say so.
- **Agent names:** subagents dispatch as `subagent_type: paper-orchestra:<name>`. The run dispatched 10 of the 11 agents this way: outline-planner, literature-scout, literature-writer, figure-maker, figure-critic, section-writer, reviewer, meta-reviewer, reviser and checker. materials-drafter was not needed, because the fixture has materials; Task 22's Gather test covers it.
- **Concurrency:** at most 4 agents ran at once.

### Timeline

| Run | Prompt | Wall time | What ran | Ended with | Answer |
|---|---|---|---|---|---|
| run1 | `/paper-orchestra` | 28 s | Gather. Settings and materials were present, so it asked no questions and dispatched no drafter. `materials validate` passed; `log verify` found 173 untagged numbers. | Gather pause | `Approved, continue.` |
| run2 | `--continue` | 202 s | Outline. The planner's first outline failed `outline validate` with 4 citation-hint format errors. The orchestrator resumed the planner with the errors, and the second attempt passed. Then render and estimate: 47 search tasks, 4 figures (3 plots, 1 diagram), at most 12 critic runs, 16 reviewer runs and 3 revisions. | Outline pause. It also asked whether to drop a planned diagram that redrew the supplied overview (bug 1). | `Approved, continue.` (kept as planned) |
| run3 | `--continue` | 1719 s | Literature and Figures in parallel, then Write, Review and Check; details below. | `NOT READY: 11 problems` | — |

Details of run3:
- **Literature** (5.5 minutes; it ran in parallel with Figures, and the two together took 7 minutes):
  - 6 scout batches;
  - `refs verify` (76 s): 94 candidates gave 46 library entries, 36 with an abstract and 10 title-only;
  - 3 candidates dropped: 2 after the cutoff, 1 not found;
  - the literature writer.
- **Figures:**
  - 10 builds and 10 critic rounds for 4 figures; each figure ended at "No changes needed." within 3 rounds;
  - `figures collect` listed 5 items, including the supplied overview.
- **Write:** the section writer took 5 minutes. The main text has 7,282 words, and every `ml-conference` section is present.
- **Review:**
  - the panel on v0 (3 reviewers and a meta-review) gave Overall 5;
  - the reviser took 9 minutes;
  - the panel on v1 gave Overall 4, so the outcome was `REJECTED_SCORE_DECREASE`: the revision was undone and the rounds stopped (spec §5, keep-or-undo).
- **Check:**
  - 32 items needed a ruling: 18 citations of title-only entries and 14 derived numbers;
  - the checker allowed 21 and failed 11. All 11 are sentences that claim more than a title-only entry supports, one of them on a medical SAM survey that was matched as a general SAM survey.
  - The script itself raised no fail or warn items. Every library entry is cited, and Figures 1–5 and Tables 1–3 are all referenced.

At the end, `state show` lists every stage as done, nothing stale, and `next_stage: null`.

### Usage

Wall time is the sum of the three invocations, without the time spent at the pauses.

| | run1 | run2 | run3 | Total |
|---|---|---|---|---|
| Wall time | 28 s | 202 s | 1719 s | **1949 s (32.5 min)** |
| `usage`: input / cache write / cache read / output | 14 / 29,047 / 268,141 / 1,927 | 8 / 1,750 / 146,572 / 1,373 | 18 / 8,041 / 1,225,848 / 3,506 | 40 / 38,838 / 1,640,561 / 6,806 (1.69 M) |
| `modelUsage`, all models, tokens | 0.30 M | 0.82 M | 15.29 M | **16.41 M** |
| `total_cost_usd` (API list price) | 0.32 | 1.14 | 16.66 | **18.13** |

- **The `usage` field undercounts.** In `-p` JSON output it covers only the main session's last turn cycle: no subagents, and nothing before a background agent finished. `modelUsage` covers the whole invocation, so the totals above use it. Per model:
  - Opus: 580 input, 1,224,209 cache write, 12,642,415 cache read, 325,359 output;
  - Sonnet: 122 input, 347,555 cache write, 759,171 cache read, 57,500 output;
  - Haiku: 987,119 input and 61,432 output, for 70 web searches.
- **Per agent** (summed from the session transcripts): the orchestrating session used 8.4 M tokens, mostly cache reads of its own growing context. The 39 subagent runs used 5.9 M:
  - figure makers 1.20 M;
  - reviewers 0.94 M;
  - reviser 0.90 M;
  - section writer 0.88 M;
  - scouts 0.77 M;
  - critics 0.40 M;
  - checker 0.33 M;
  - literature writer 0.18 M;
  - planner 0.13 M;
  - meta-reviewers 0.12 M.
- **Each further review round** (reviser, 3 reviewers, meta-reviewer) adds about 12 minutes and 1.5 M tokens.
- **Outside the sample run:** the two slash-form probes cost 0.26 and 0.25 USD-equivalent. The planner fix check (Gather and Outline only, on a fresh copy, 148 s) cost 1.16.

### Bugs found and fixed

1. **The outline planner redrew a supplied figure.** Fixed in `b86f4f2`, `fix: outline planner must not redraw supplied figures (found in E2E)`.
   - The planner added a Mermaid diagram "matching the supplied tsam_overview.png", so the paper showed the overview twice (Figure 1 as Mermaid, Figure 2 as the supplied image). Spec §5 says supplied images are used as they are.
   - Fix: rule O2 now says supplied images are already in the paper, and the planner plans only new figures.
   - Check: a Gather and Outline run on a fresh copy planned 3 plots and no diagram, and said the supplied figure "is used as is and not redrawn". The sample run above was planned before the fix.
2. **Write-notes problems were left in `paper.md` without a word.** Fixed in `6f5e42a`, `fix: report write-notes problems left in paper.md after an undone round (found in E2E)`.
   - The section writer listed consistency problems in `drafts/write_notes.md`. One was a false claim in the Introduction and Related Work that removing the temporal branch "causes the largest drop" (Table 2 shows larger drops). The round-1 reviser fixed them, but its revision was undone, so they stayed in `paper.md`.
   - SKILL.md had promised that "the first reviser round fixes them", and the final report never mentioned them.
   - Fix: the review report now says when no revision was kept, lists the write-notes problems, and points to `drafts/candidate_v1.md`. This changes reporting only and was not re-run.

### Other observations (no change made)

- **Outline citation hints:** the planner's first outline used hints like "research paper or technical report introducing the 'Ref-AVS' task and dataset", which the validator rejects. The validate and re-dispatch loop fixed them in one retry, and the later outline-only run passed on its first try.
- **Title-only over-claims:** the 11 Check FAILs show that the literature writer still over-claims from title-only entries (10 of the 46 entries have no abstract). The Check gate catches them as designed (§13 item 12).
- **Keep-or-undo discards fixes:** an undone round also discards fixes that a later reviewer would not have objected to. The final `paper.md` is the v0 draft, and `drafts/candidate_v1.md` holds the fixes. This follows the spec (and the original); changing it is a design decision.
- **Provider names:** `grep -rniE "gemini|openai" plugins/paper-orchestra/{scripts,agents,skills}` prints nothing.
