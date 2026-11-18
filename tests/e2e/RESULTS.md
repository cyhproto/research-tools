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

## Acceptance scenarios (Task 22; spec §13 items 2–5 and 9–13)

Run on 2026-11-18 with Claude Code 2.1.327 and the headless setup above: subscription login, `--plugin-dir`, the calling session's `CLAUDE*` variables unset. Each scenario ran in its own `.e2e/<name>/` copy. Following Ruling P19, the fresh runs used the `light` profile: 1 reviewer, no meta-review, 1 critic round and 1 revision round. Usage is `modelUsage`, counted once per session (see Usage below).

- **Planted errors (items 2 and 12): pass.**
  - **Setup:** in a copy of the sample, two paragraphs were added at the end of Experiments: `We also reach 91.7 [@Fake2024Paper].` and `Audio-visual segmentation [@Zhou2022AudiovisualSegmentation] reaches 23.20 Seen J on Ref-AVS.`
  - **Scripts:** `check run` then `check finalize --rulings /dev/null` print `NOT READY: 35 problems`, with three new FAILs:
    - `citations-019`: citation key Fake2024Paper is not in the library;
    - `numbers-015`: number 91.7 not found in the materials;
    - `citations-020`: sentence cites title-only entry Zhou2022AudiovisualSegmentation. The 23.20 is in the log, so only the title-only rule catches this sentence.
  - **Checker:** with `/paper-orchestra check`, all three stay FAIL with stated reasons ("The title does not support any Ref-AVS result"), giving `NOT READY: 15 problems`.
  - **Literal append:** a sentence appended at the very end of `paper.md` lands inside `## References`. Check skips that section by design and `paper references` regenerates it, so nothing is flagged.
  - **Usage:** scripts 0; checker run 0.51 M.
- **Rerun figures only (item 4): pass.**
  - **Run:** `/paper-orchestra figures` on a copy of the sample, with the full profile as it was, took 369 s. It moved the old figures to `old/figures-<stamp>/` and rebuilt all 4 figures (9 builds, 9 critic rounds).
  - **Evidence:** the sha256 of every file in `references/` and `drafts/`, and of `paper.md`, `review.md` and `outline.json`, is unchanged. `state show` gives `stale: ["write", "review", "check"]`, and the run suggested `write --only "Method" "Experiments"`.
  - **Usage:** 4.94 M.
- **Hand edits (item 5): pass.**
  - **Setup:** one Experiments paragraph of the sample was rewritten by hand, with a transposed digit (Unseen J 55.48 instead of 54.58); profile light.
  - **Keep** (`/paper-orchestra review`, 566 s):
    - the round was kept (5 → 5, `ACCEPTED_NEUTRAL_IMPROVEMENT`);
    - the paragraph is byte-identical in the new `paper.md` and in `drafts/candidate_v1.md`;
    - both reviewers flagged the typo, and `review.md` → "Suggestions for your edited paragraphs" has `po:keep 1: … Change '55.48%' to '54.58%'`;
    - usage 1.63 M.
  - **Revise** (`--hand-edits revise`, 777 s):
    - `drafts/v4-user.md` holds the hand-edited version;
    - the option was recorded as `opt:review:hand-edits=revise`, and `settings.md` still says `keep`;
    - "Changes to your edited paragraphs" lists `Round v1 (undone, not applied): paragraph rewritten`, with Before (55.48) and After (54.58);
    - the round was undone (5 → 4), so `paper.md` keeps the user's paragraph;
    - usage 1.76 M.
- **Interrupted run (item 9): pass.**
  - **Setup:** a fresh copy of the fixture with `--profile light`, through Gather and Outline: 44 search tasks and 3 plots; the supplied overview was not redrawn.
  - **Kill 1:** the whole process group was killed 91 s after the go, 2 s after the first `references/candidates/*.json` file appeared; 2 such files existed. All 3 figures had been built; 2 of their checkpoints were recorded.
  - **Resume 1** (a fresh `/paper-orchestra`): it searched only the 42 pending tasks, in 6 new batches. It recorded the third figure's checkpoint from its meta file instead of rebuilding it, and went on through Write into Review.
  - **Kill 2:** 789 s into that resume, 1 s after `reviews/v0/r1.md` was written and before its checkpoint was recorded.
  - **Resume 2** (744 s): it recorded `review:v0:r1` from the file, then ran the reviser, the v1 reviewer and Check.
  - **Evidence:**
    - the 2 candidate files and `r1.md` have the same sha256 at the end as at the kills;
    - no agent ran again for finished work;
    - `assert_sample.py .e2e/interrupt/paper` prints `OK: all checks passed; references=33 figures=4 plots=3 review_rounds_with_outcome=1`.
  - **Usage:** 8.5 M. The first killed run printed no JSON, so its 0.97 M comes from its transcripts, plus about 0.25 M for its 16 web searches.
- **Journal-heavy literature and import (items 10 and 13): pass.**
  - **Fixture:** `tests/fixtures/journal_topic`, on battery cycle-life prediction, with the `journal` style and the light profile.
  - **Candidates:** 13 search tasks gave 30 candidates with 21 unique titles.
  - **Counts** (`refs counts`): with_abstract 14, title_only 8, must_cite 1, dropped 0. So 14 + 8 + 0 = 22, which is the 21 unique candidates plus the must-cite entry, which no candidate matched.
  - **Journal abstracts:** of the 6 Elsevier-journal entries, 5 are title-only, and the sixth carries the imported abstract.
  - **Import:** both `library.bib` entries matched candidates and have `abstract_source: "import"`. Severson et al. (2019) has no abstract in OpenAlex, Semantic Scholar or Crossref, so the import is its only source.
  - **Must-cite:** `hu2020battery` is in the library, cited in the Introduction and in Method 3.1, where the outline assigns it.
  - **Check:** after figures (an empty plan) and write, Check printed `NOT READY: 7 problems` with no must-cite FAIL. The 7 are 3 title-only over-claims, 2 numbers quoted from cited abstracts, and the journal style's 2 required statements.
  - **Usage:** 2.35 M.
- **Gather self-check (item 11): pass.**
  - **Drafting:** on the toy project, with its new `README.md`, `/paper-orchestra gather --profile light (use the defaults …)` drafted both materials files in 66 s and paused. `log verify` exits 0 with 21 ok.
  - **Changed result:** after `seed_1,0.8731` became `seed_1,0.8000` in `results/metrics.csv`, `log verify` exits 1 with 4 mismatches. All 4 come from that cell: the value's two tags and the two `calc` tags that use it. `materials validate` also exits 1.
  - **Re-check:** running `/paper-orchestra gather` again (25 s) reported the mismatch, traced the calc lines to the cell, and asked the user to fix the log or the CSV.
  - **Usage:** 0.54 M.
- **Unit-level items (item 3): pass.** `uv run --no-project --with pytest pytest -q` from the repo root gives 269 passed. That is 265 before this task, plus 3 tests for calc ids and 1 fixture test.

### Title-only rules (Ruling P20)

L4, W9 and X4 now list allowed and forbidden sentence patterns for entries without an abstract (`f095d1c`). Title-only FAILs after the change:

| Paper | Title-only sentences | FAIL |
| --- | --- | --- |
| The Task 21 sample, older prompts (re-checked in the planted-errors run, planted sentence excluded) | 18 | 12 |
| Interrupted run, after its review round | 22 | 3 |
| Journal topic | 12 | 3 |

- **The remaining FAILs:**
  - framing claims around the must-cite review ("an established research field", "a central problem of");
  - the name "Mask2Former" attached to a title that doesn't contain it;
  - a task definition attributed to a title-only paper;
  - one clause on how a closed loop works.
- **Caveat:** these are different papers, not a controlled comparison.

### Bugs found and fixed

1. **`f095d1c` `fix: stricter title-only citation rules (found in E2E)`.** This is Ruling P20, prompted by Task 21's 11 FAILs.
2. **`39783ab` `fix: calc tags may use ids defined later in the log (found in E2E)`.**
   - **Problem:** `log verify` resolved ids in one pass. A `calc` tag above the final `## Source values` section, the layout that the template and drafter rule M2 prescribe, was reported as "unknown id". In the gather run the drafter worked around it by tagging every value twice.
   - **Fix:** src tags are resolved first, and a calc uses an id's closest definition above it, or else the first one below it. There are 3 regression tests.
3. **`d1c1849` `fix: README usage figures counted the first two invocations twice (found in E2E)`.**
   - **Problem:** with `claude -p --continue`, the JSON `modelUsage` and `total_cost_usd` are cumulative for the session. The S4 transcripts show it: run1 used 0.21 M and run2 0.36 M, yet run2 reports 0.58 M.
   - **Correction:** the sample run above used 15.29 M tokens and $16.66, not 16.41 M and $18.13. Its Usage table's run2 and run3 columns are cumulative, so the total is run3's figure. The README now says about 15 million tokens and about $17.
4. **`eeb8522` `fix: checker can list the materials folder it must read (found in E2E)`.**
   - **Problem:** the checker had only Read and Write, so it could not list `materials/`. In the journal Check it got EISDIR, then guessed 7 file names and found only `idea.md` and `experiment_log.md`.
   - **Fix:** it now has Glob and reads the same text files the script uses. In the interrupted run's Check it ran `Glob **/*` and also read `figures/captions.md`.

### Other observations (no change made)

- **Resume without a checkpoint:** both interruptions hit an output that was written but not yet checkpointed (a figure's meta file, `reviews/v0/r1.md`). Both times the orchestrator recorded the checkpoint from the file instead of redoing the work. Only Literature states this rule in SKILL.md (a task is pending only without a checkpoint *and* without a file); for figures and reviews it rests on the model's judgment.
- **Text below `## References`:** Check ignores it, and `paper references` replaces it. A paragraph appended at the very end of `paper.md`, without its own `##` heading, is lost silently when the next stage regenerates References. The tests encode this as the design.
- **Journal required statements:** no agent writes "Data and code availability" or "Declaration of competing interests" (W1 limits the writer to the style's `sections`, and G4 forbids inventing them). The writer says so, and Check FAILs until the user adds them.
- **Numbers quoted from cited abstracts:** for example "9.1%" from Severson et al. These FAIL in Check, because K1 accepts only the materials, although G2 lets writers use abstract facts. This is a spec tension for the user to decide.
- **Asking before a stale stage:** `/paper-orchestra check` on a stale Check asked before running (§10). `/paper-orchestra review` on a stale review ran without asking.
- **Key-less lookups:** the key-less OpenAlex budget for this network address ran out during the interrupted run (`429 … Insufficient budget`), and Semantic Scholar also returned 429. 8 candidates were dropped as `lookup-failed`; they are retried on the next `refs verify`. The README already recommends a free OpenAlex key.
- **Gather on "go":** it re-validates only when the materials changed. A result file changed during the pause is re-checked only when Gather runs again, which then reports it.
- **Fixture slip:** the journal fixture's log first said "nine features" where `idea.md` lists eight. The section writer flagged it in `write_notes.md`, and the committed fixture now says eight.

### Usage

- **Total:** 16 invocations in 12 sessions used 20.2 M tokens: 19.0 M measured, and about 1.2 M for the killed run without JSON. The list-price estimate is about $28. All runs together took 71 minutes, partly in parallel.
- **Per scenario:**

  | Scenario | Tokens |
  | --- | --- |
  | Planted errors | 0.51 M |
  | Rerun figures | 4.94 M |
  | Hand edits | 3.39 M |
  | Interrupted run | 8.52 M |
  | Journal topic | 2.35 M |
  | Gather | 0.54 M |
- **Rerun on the full profile:** the figures-only rerun with 4 figures and up to 3 critic rounds (4.94 M) cost more than either light hand-edit review (1.63 M and 1.76 M).
