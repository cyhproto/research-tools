# PaperOrchestra for Claude Code — Design

**Date:** 2026-11-18 · **Status:** draft, waiting for the user's approval

How to read the tags in this document:

- **(user)** decided by the user in conversation.
- **(original)** ported from Google's PaperOrchestra with its logic unchanged.
- **(my call)** decided by Claude during design; the user may overturn it (full list in §11).
- **(builder)** left to whoever builds it (full list in §12).

---

## 1. What this is and why

Google Research published **PaperOrchestra** (`github.com/google-research/paper-orchestra`, commit `d9bae997e793a015ed38bb1605be9eb58c00284f`, 2026-11-15; paper arXiv 2604.05018). It is a multi-agent pipeline that turns a research idea and an experiment log into a submission-ready LaTeX paper, with literature search, generated figures, and a simulated peer-review loop. It runs on Gemini (partly OpenAI) APIs; its literature search is hard-wired to Gemini's Google Search tool.

The user wants the same sequence and logic as a **Claude Code tool** (user):

- runs entirely inside Claude Code: no Gemini or OpenAI keys;
- reusable for every future research project, not tied to one project;
- writes **Markdown**, because the user writes in Markdown; no LaTeX;
- shareable with colleagues;
- runs on a **Claude subscription** login (Pro/Max), with no Anthropic API key and no pay-per-token billing (§9);
- the deliverable is **the tool**, not a particular paper, so it must not assume a venue.

Why: the user likes the original's orchestration ideas and wants them as the standard backbone for writing up future research.

## 2. Goals, non-goals, anti-goals

**Goals**

1. In any project folder, `/paper-orchestra` produces a Markdown paper draft in `paper/`, built only from that project's materials.
2. Reproduce the original's logic faithfully (§5), adapted to Claude Code and Markdown.
3. Every stage writes its own files, so any stage can be re-run alone and an interrupted run can resume.
4. Venue rules live in swappable style-guide files (§7).
5. Installed and updated through a Claude Code plugin marketplace hosted on GitHub (§8).

**Non-goals**

- LaTeX templates, PDF compilation, PDF layout checks.
- Batch mode over many papers, the Streamlit web demo, and the benchmark scorers in `autoraters/` (citation F1, side-by-side ratings). Those need Google's unreleased dataset.
- Illustrated diagrams from an image-generation model.
- Running new experiments.
- Converting to Word/PDF. The citation format keeps this possible later with pandoc; not built now.

**Anti-goals.** The tool has failed, even if it runs, when:

- the paper cites a paper that does not exist, or anything outside the verified library;
- the paper states a number that cannot be traced to the project's materials;
- the paper claims to beat a method that was not evaluated in the experiment log;
- a rerun silently overwrites text the user edited by hand (my call).

## 3. Who uses it and how

- **Primary user:** a researcher who writes in Markdown (also uses Obsidian), with many research projects under `~/Research/CodeWorks/`. Claude Code CLI on Linux (WSL2).
- **Secondary users:** colleagues who install the plugin from the GitHub repo. Their OS and Python setup may differ.

Typical session (proposed in conversation; user said "Good"):

```
$ cd ~/Research/CodeWorks/<project>
$ claude
> /paper-orchestra
```

1. **Gather**, then **pause**: the user checks and corrects the drafted materials.
2. **Outline**, then **pause**: the user approves or changes the plan.
3. **Literature** and **Figures** run in parallel.
4. **Write** the remaining sections.
5. **Review and revise**, up to 3 rounds.
6. **Check**, then a final report.

Each stage can also be run alone, for example re-running the literature search after new papers appear, or running Check on a draft the user edited. The output folder opens directly in Obsidian; Mermaid and math render there.

## 4. Per-project files (my call: names may change, the shape should not)

```
<project>/paper/
├── settings.md            style guide name, cutoff month (YYYY-MM), blind review yes/no,
│                          language (default English), profile full | light (§9),
│                          max review rounds (default comes from the profile),
│                          hand edits keep | revise (§5, Stage 4)
├── materials/
│   ├── idea.md
│   ├── experiment_log.md
│   ├── figures/            images the user supplies + captions.md
│   └── references/         optional exports from the user's reference manager (BibTeX or CSL JSON):
│                           library.bib = abstract source, must_cite.bib = always cited
├── outline.json            the three plans; source of truth for later stages
├── outline.md              readable view of the outline, shown at the pause
├── references/
│   ├── library.json        verified papers: key, title, authors, venue, year, abstract,
│   │                       identifiers (OpenAlex/S2/DOI), reason found, section found for
│   ├── references.bib
│   ├── search_log.json     every task, every candidate, why dropped ones were dropped
│   └── cache.json          lookup cache so reruns don't re-query
├── figures/
│   ├── <figure_id>.png     plots, 300 dpi
│   ├── <figure_id>.mmd     Mermaid diagrams
│   ├── src/<figure_id>.py  plot scripts, re-runnable
│   └── info.json           id, file, caption, description, critic history
├── drafts/v0.md, v1.md, …  every version kept
├── reviews/review_v0.json, …, worklog.json
├── paper.md                current best draft, with References section
├── review.md               human summary: scores per round, what changed, kept or undone,
│                           experiments reviewers asked for, Check results
└── .state.json             stage status + hashes of inputs/outputs
                            (for resume, stale-stage and hand-edit detection)
```

### Reruns, section ownership and hand edits (my call)

- `paper.md` is the single working file; the tool splits it by its `##` headings. Each section has one owner:
  - literature-writer: Introduction, Related Work;
  - section-writer: Title, Abstract, Method, Experiments, Conclusion, Limitations, Appendix;
  - script: References.
- **Hand edits** are found at paragraph level, by comparing `paper.md` with the last version the tool wrote (kept in `drafts/`).
- **Rerunning a stage replaces only the sections it owns**, as a new version in `drafts/`. Every other section is kept, including review revisions and hand edits. `write` can be limited to named sections (e.g. only Experiments after new results).
- **Before replacing**, the tool lists the sections it will replace. If any contain hand edits, it asks per section: replace, keep yours, or save the new text beside it (`drafts/<section>-new.md`) to merge by hand.
- **Rerunning `gather`, `outline` or `figures`** changes nothing in `paper.md`. It marks later stages stale and names the sections that depend on what changed (e.g. Experiments uses the new numbers), so the user can re-run `write` for just those.
- **What the reviser may do with hand-edited paragraphs:** see §5, Stage 4.

## 5. The pipeline

### Stage 0: Gather (new; not in the original)

The original makes the researcher hand-write `idea.md` and `experimental_log.md`. Here Claude drafts them from the project.

- **Reads:** README and notes, code (model, losses, training loop), configs (hyperparameters), result files (CSV/JSON/logs), notebooks, existing figures.
- **Writes `materials/idea.md`** with the original's sections: Problem Statement · Core Hypothesis · Proposed Methodology (components; equations where the code defines them) · Expected Contribution.
- **Writes `materials/experiment_log.md`** with: 1. Experimental Setup (datasets, splits, baselines, metrics, implementation details) · 2. Raw Numeric Data (tables) · 3. Qualitative Observations (comparison with baselines, ablations, sensitivity, visual analysis).
- **Every number in the log carries a machine-readable source tag** (my call). The exact syntax is fixed once in the plugin's docs and never changed afterwards, because every project's materials depend on it. Four kinds:
  - a table cell: file + row + column (CSV/TSV);
  - a JSON value: file + key path;
  - a text-log line: file + line number (+ optional pattern);
  - a computed value (mean over seeds, standard deviation, difference): the formula and its tagged inputs.
- **Gather checks its own numbers** (my call). A script re-reads every tagged source and recomputes every formula; mismatches are fixed before the pause. Values the script cannot read (notebook outputs, images, PDFs) are marked **check by hand**, and the pause lists those first.
- **After the pause, the approved log is the ground truth** (my call). Check (Stage 5) compares the paper with `experiment_log.md`; it does not re-read raw files. When raw results change, re-run `gather`.
- If the project has no results yet, Gather says what is missing and stops. The tool never writes an Experiments section without data.
- Asks for the style guide, cutoff month, blind review, and any reference-manager exports to import (§5, Stage 2a), or applies defaults (`ml-conference`, current month, blind review on, no import). Writes `settings.md`.
- If materials already exist (hand-written), validates their structure and asks before replacing anything.
- **Pause.** Nothing downstream runs until the user says go.

### Stage 1: Outline (original: `methods/prompts/outline_agent.py`)

One agent turns materials + style guide into **three plans**, using the original's JSON schema (`plotting_plan`, `intro_related_work_plan`, `section_plan`). The style guide's section skeleton replaces the original's `template.tex`.

1. **Figure plan.** Per figure:
   - `figure_id`: meaningful, never containing the word "Figure";
   - title;
   - `plot_type`: `plot` or `diagram`;
   - `data_source`: idea / experiment log / both. Optionally it also lists project data files named in the log (my call; the original only reads the two Markdown files);
   - objective: names the chart type for plots;
   - aspect ratio: plots only.
2. **Literature plan.**
   - **Introduction** (macro context, **10–20 papers**):
     - a hook hypothesis;
     - a problem-gap hypothesis, strictly scoped to the experiments actually run (no over-claiming);
     - 3–5 search directions: real-world impact of the gap, surveys, 3–5 foundational papers.
   - **Related Work** (technical comparison, **30–50 papers**): **2–4 method clusters**. Each cluster has:
     - a name;
     - a SOTA investigation mission: no searches past the cutoff, and no new "competitors" that aren't in the log;
     - a limitation hypothesis;
     - narrow limitation search queries;
     - the bridge: how our method fixes the limitation.
   - Introduction and Related Work searches must not overlap in scope.
3. **Section plan.**
   - Sections and subsections follow the style guide's skeleton. No subsection X.1 without an X.2.
   - Content bullets point at specific source material ("formalize Eq. 3 from idea.md", not "describe the model").
   - **Citation hints for every dataset, metric, baseline, optimizer, architecture and framework** mentioned in the materials. Hint format: `Author (Exact Title)` only when certain; otherwise `research paper introducing 'X'`. Authors are never guessed.
   - Math subsections are proposed only for what the materials support.
   - Every paper in `materials/references/must_cite.bib` is assigned to the section where it belongs (user).

**Pause.** Show `outline.md`; apply the user's changes to `outline.json` before continuing.

### Stage 2a: Literature (original: `methods/agents/literature_review_agent.py`, `utils/scholar_utils.py`, `methods/prompts/literature_review_agent.py`)

1. **Collect search tasks** exactly as the original's `_collect_search_tasks`:
   - one per Introduction search direction;
   - one per Related-Work limitation query (fallback: cluster title + cluster name);
   - one **targeted** task per citation hint.
2. **Discover** with Claude's web search, which replaces Gemini + Google Search grounding.
   - Exploration task: 10–15 relevant, influential papers (peer-reviewed venues, highly cited work, or the exact state of the art), each with title, year, and reason.
   - Targeted task: exactly 1 paper, namely the original paper that introduced the dataset/model/metric.
   - Anything published after the cutoff is excluded.
   - If web search is unavailable, this stage stops with a clear message; other stages still work.
3. **Verify** each candidate with a script (my call: a script, not an agent).
   - **Lookup services** (my call), as tested from this machine on 2026-11-18:
     - **OpenAlex** first. It works without a key and returns abstracts where it has them. Its free budget is counted in money: key-less requests share $0.10/day with everyone on the same network address; a `search=` lookup costs $0.001 and a `filter=` lookup $0.0001 (measured 2026-11-18). A full run needs roughly 200–600 lookups, so the script uses `filter=` title lookups and caches results (my call). The README recommends a free OpenAlex key (`OPENALEX_API_KEY`, its own $1/day), which users create themselves.
     - **Semantic Scholar** only when `SEMANTIC_SCHOLAR_API_KEY` is set. Without a key it returned HTTP 429 (rate limited) on both tries.
     - **Crossref** for title/DOI confirmation. It works without a key but usually has no abstract.
     - The arXiv API was also rate-limited (HTTP 429), so it is not a primary source.
   - **Match rule** (original, except the abstract rule below):
     - take the best of the top results by fuzzy title similarity, +10 if the year matches, accept if > 70;
     - the paper must be published before the cutoff;
     - dedupe by normalized title;
     - about 1 request per second, cached.
   - **Abstracts** (user: "limited use + import"). The original drops every paper without an abstract. In the reviewer's check that would lose about 85–90% of recent Elsevier journal papers, because the free databases lack their abstracts. Instead:
     - abstract sources, in order: the user's export `materials/references/library.bib` (matched by DOI, then by the title rule), OpenAlex, Semantic Scholar (with a key). Truncated at 1,500 characters.
     - A paper verified to exist but with no abstract from any source is kept as a **title-only** entry. It may be cited only for what its title and venue say (e.g. "X studied Y"), never for specific results, numbers, or method details. Check enforces this (Stage 5).
   - **Must-cite papers** (user, via the import). Entries in `materials/references/must_cite.bib`, including the user's own earlier work, always enter the library.
     - Each is verified like any candidate. One that cannot be found online (e.g. in press) is kept and marked as vouched for by the user (my call).
     - The Outline places each one in a section (Stage 1), and Check confirms each is cited (Stage 5).
   - Candidates that fail verification are dropped and logged with the reason. They are never cited.
   - The run reports four counts: papers with abstracts, title-only papers, must-cite papers, dropped candidates.
4. **Build the library.**
   - Citation key: first author's last name + year + first two meaningful title words (e.g. `Vaswani2017AttentionAll`), with `a`/`b` suffixes for clashes (original `_generate_key`).
   - `references.bib`: `@article` if the paper has a journal, else `@inproceedings` (original).
   - Each subsection in `outline.json` gets its `citation_candidates` (original `_inject_citations_into_outline`).
5. **Write Introduction + Related Work** (separate agent; original prompt adapted to Markdown).
   - It may cite **only** the library.
   - It must cite ≥ 90% of the papers found by the Introduction/Related-Work tasks. The original requires 90% of *all* collected papers; this is scoped so must-cite dataset/metric papers can sit in Method/Experiments instead (my call).
   - It describes each cited paper from that paper's abstract; title-only entries only by their title and venue.
   - **No claim of beating a paper unless that paper is evaluated in the experiment log.** Papers after the cutoff are concurrent work, never baselines.

### Stage 2b: Figures (original: `methods/agents/plotting_agent.py`, `utils/paper_banana_utils.py`). One job per figure, in parallel with 2a.

**Plots** (original steps):

1. **Planner:** a detailed description listing every data point, the variable → axis/colour mapping, and exact styling.
2. **Stylist:** refines the description using our figure style guide `styles/figures.md`. The original reads a NeurIPS style guide and a few-shot example bank from Google's separate PaperBanana project. Neither is in the repo, and the original runs without them. We write our own guide and use no example bank (my call).
3. **Code:** a matplotlib script saved as `figures/src/<id>.py` and run to produce `<id>.png`.
4. **Critic:** a separate agent with fresh context (my call). It looks at the PNG against the raw data and checks:
   - data fidelity: all values correct, nothing missing or invented;
   - text typos, overlaps, redundant legends;
   - no caption or title text inside the image;
   - if rendering failed: simplify the description.

   It returns suggestions + a revised description, or "No changes needed". **Up to 3 rounds** (original).
5. **Caption:** plain text, no "Figure N:" prefix.

**Diagrams** (method overview, pipeline):

- Claude cannot generate images, so diagrams are **Mermaid** (my call): text that Obsidian and GitHub draw.
- The critic checks the Mermaid source against the method description.
- Rendering for the critic is optional; `mmdc` is not installed on the user's machine (builder).

**User-supplied images** in `materials/figures/` are used as-is with their captions.

**Python for plots:**

- On the user's machine, system `python3` has no matplotlib, `~/Research/bin/python` has matplotlib 3.10 + numpy 2.1, and `uv` is installed.
- The tool must find a working Python with matplotlib: project venv first, then `uv run --with matplotlib --with numpy`, then ask the user to install it.
- It must never install packages into the user's project environments (my call).

### Stage 3: Write the remaining sections (original: `methods/agents/section_writing_agent.py`, `methods/prompts/section_writing_agent.py`)

**What it writes:**

- Title (if missing), Abstract, Method, Experiments, Conclusion, **Limitations**, and an optional Appendix, following `outline.json`.
- Introduction and Related Work stay as written, apart from consistency edits.

**Inputs:** outline with citation candidates; the library with abstracts (title-only entries flagged); materials; the figure list **and the PNG files themselves**; the style guide.

**Rules kept from the original:**

- tables use the experiment log's exact values;
- no invented math;
- detailed ablation and qualitative analysis: what works, what doesn't, and why;
- use **all** figures and reference each one in the text;
- describe figures faithfully, never contradicting the image;
- all figures and tables appear before the Conclusion unless they are in the Appendix;
- dense, objective tone.

**Markdown conventions (my call):**

- Citations: `[@key]`, several as `[@a; @b]` (pandoc syntax: readable as plain text and convertible later).
- Figures: `![…](figures/<id>.png)` with a caption line `*Figure N: …*` below. Mermaid goes in a fenced `mermaid` block with the same caption line.
- Tables: pipe tables with `*Table N: …*` above; best results in bold.
- Math: `$…$` inline, `$$…$$` display.
- Figures and tables are numbered in order of appearance, and cross-referenced by number.

A **References** section is appended by script from the cited library entries, styled per the style guide (numbered or author–year).

### Stage 4: Review and revise (original: `methods/agents/content_refinement_agent.py`, `methods/prompts/content_refinement_agent.py`, `autoraters/agent_review.py`)

**Reviewer panel (original):**

- **3 independent reviewers**, each with fresh context and run in parallel.
  - Persona: AgentReview's "best case" reviewer (knowledgeable, responsible, benign).
  - Overall score rubric: the 1/3/5/6/8/10 anchors in `agent_review.py`.
  - A style guide may change the persona wording (e.g. journal reviewer) and add criteria, but **not the score fields**, because the keep-or-undo rule depends on them (my call).
- **Review fields:** Summary, Strengths, Weaknesses, Questions, Limitations, Ethical Concerns; Originality / Quality / Clarity / Significance / Soundness / Presentation / Contribution (1–4); Overall (1–10); Confidence (1–5); Decision (Accept/Reject).
- **1 meta-reviewer** merges the three into one review in the same format. Each score is the mean of the three reviewers, rounded (original).
- Claude Code cannot set sampling temperature. If the three reviews come out near-identical, the builder may give each reviewer a different emphasis while keeping the same fields (builder).

**Reviser** (original prompt, with two deliberate changes):

- Turns each weakness and question into edits inside the paper; no separate response letter.
- Preserves the listed strengths.
- Checks every number against the experiment log; cites only the library.
- Writes a worklog entry: weaknesses addressed, answers integrated, actions taken.
- **Change 1 (my call):** the original prompt says "Never explicitly state a limitation." We keep an honest Limitations section instead.
- **Change 2 (my call):** requests for new experiments or data stay out of the paper (as in the original), but are listed in `review.md` under "Experiments reviewers asked for", as a to-do for the researcher.
- **Hand-edited paragraphs** (user: "make it an option"). A `hand edits` setting in `settings.md`, which can be overridden for a single run (builder picks the syntax):
  - `keep` (default; my call): paragraphs the user edited stay exactly as written. Reviewer comments about them go to `review.md` as suggestions for the user. After each revision a script confirms those paragraphs are unchanged and restores any that changed.
  - `revise`: the reviser may rewrite them too. Every change to a hand-edited paragraph is listed in `review.md` (before → after), and the user's version stays in `drafts/`.

**Keep-or-undo rule (original):** a fresh panel reviews each revised draft, then:

- Overall score up: keep the revision and continue.
- Overall score down: undo (return to the previous draft) and stop.
- Overall score equal: compare the sub-scores (all except Overall and Confidence). If the total gain ≥ the total drop, keep and continue; otherwise undo and stop.
- At most **3** revision rounds (setting). All versions and reviews are kept.

The README must say: the reviewers are the same model family as the writer, so scores are a relative signal for keep-or-undo, not a real acceptance prediction.

### Stage 5: Check (new; replaces the original's compile step and PDF format loop)

A script runs first, then a checker agent handles what a script cannot judge.

1. **Citations:**
   - every `[@key]` exists in the library;
   - every library entry has a verified identifier, or is a must-cite paper vouched for by the user;
   - every must-cite paper is cited at least once;
   - every sentence that cites a **title-only** entry claims no more than its title and venue support. The checker agent rules on each one; otherwise **FAIL**;
   - share of the library cited (warning below 90%);
   - unused entries listed.
2. **Numbers:**
   - extract numbers from `paper.md`, excluding section/figure/table/equation numbers, citation keys, and years inside references;
   - normalize them (`87.3` = `87.30` = `87.3%`);
   - match them against the numbers in the materials and the listed data files.

   The checker agent then rules on each unmatched number. It is allowed only if derived from matched numbers (e.g. a difference), and the report shows the arithmetic. Otherwise it is **FAIL**.
3. **Figures and tables:**
   - every image and Mermaid file exists;
   - every figure and table is referenced in the text;
   - every figure in `info.json` is used.
4. **Venue rules:**
   - required sections are present;
   - length is within the style guide's target;
   - if blind review: no author names, emails, affiliations, or acknowledgements.

**Output:** a PASS/FAIL list with line numbers in `review.md`, plus a one-line status in chat (`READY` or `NOT READY: n problems`). Check never edits the paper. It can also run on its own, e.g. after the user edits `paper.md` by hand.

## 6. Rules every agent follows (original `utils/prompt_utils.py`, adapted; my call)

The original forbids all prior knowledge because it rebuilds already-published benchmark papers and must not leak them. For real, unpublished research the adapted rules are:

- Facts about **this** work come only from the materials.
- Facts about **other** work come only from library entries, with a citation: from the abstract when there is one; from the title and venue only, for title-only entries.
- General background knowledge may shape wording, but never supports an uncited claim.
- No invented numbers, equations, variables, authors, affiliations, or acknowledgements.
- Anonymize when the style guide says blind review; cite the user's own earlier work in the third person.

## 7. Venue style guides (my call)

- **Shipped with the plugin:**
  - `styles/ml-conference.md`, adapted from the original's ICLR/CVPR `guidelines.md` minus the LaTeX specifics;
  - `styles/journal.md`: a generic journal guide (not anonymous, longer, data/code availability statement);
  - `styles/figures.md`: the figure style guide.
- **Added by users:** one Markdown file per venue, either in a user-level folder (e.g. `~/.claude/paper-orchestra/styles/`) or as `paper/style.md` inside a project. The builder picks the lookup order.
- **Contents of a style guide:** section skeleton, length target in words, tone, citation display style, figure/table caption rules, blind review on/off, required statements, reviewer persona notes and extra criteria, language.
- **Read by:** Outline, both writers, the reviewers, and Check.

## 8. Packaging and sharing (user: shareable; names: my call)

```
~/Research/research-tools/          → GitHub repo "research-tools" (private is fine)
├── .claude-plugin/marketplace.json   marketplace "research-tools"; plugin source "./plugins/paper-orchestra"
├── plugins/paper-orchestra/
│   ├── .claude-plugin/plugin.json
│   ├── skills/paper-orchestra/SKILL.md    orchestrator: stages, pauses, resume, stage arguments
│   ├── agents/                            outline-planner, literature-scout, literature-writer,
│   │                                      figure-maker, figure-critic, section-writer,
│   │                                      reviewer, meta-reviewer, reviser, checker
│   ├── scripts/                           verify papers, build library/bib/references, check, state
│   ├── styles/                            ml-conference.md, journal.md, figures.md
│   └── README.md, LICENSE, NOTICE
├── tests/
└── docs/superpowers/specs/             this document
```

- **Layout facts verified on this machine** (from installed plugins):
  - a plugin has `.claude-plugin/plugin.json` (name, version, description, author);
  - agents are Markdown files with frontmatter `name`, `description`, `model`;
  - a marketplace's `.claude-plugin/marketplace.json` lists plugins with `"source": "./plugins/<name>"`.
- **Colleague install:**
  1. `/plugin marketplace add <owner>/research-tools`
  2. `/plugin install paper-orchestra@research-tools`

  Update with `/plugin marketplace update research-tools`. For local testing, add the marketplace by its local path.
- **Command name:** as short as the plugin system allows. The intent is `/paper-orchestra`, with stage arguments: `gather`, `outline`, `lit-review`, `figures`, `write`, `review`, `check`. Plugin skills may be namespaced; the builder verifies what users actually have to type (builder).
- **Licensing (my call):** the original is Apache-2.0.
  - Ported prompts keep its copyright notice, and `NOTICE` states they were modified.
  - The plugin itself is Apache-2.0.
  - The README credits the PaperOrchestra paper.

## 9. Constraints

### Runs on a Claude subscription (user)

The tool must work for anyone logged in to Claude Code with a Claude subscription (the user's plan and colleagues' plans), with no Anthropic API key and no per-token billing.

- **All model work happens inside Claude Code agents.** No script calls an LLM API, uses an Anthropic SDK, or reads an API key. Scripts only do mechanical work: lookups, files, checks.
- **Verified on the user's machine (2026-11-18):** Claude Code is logged in with a subscription account on the top rate-limit tier (Max 20x class), and the web search tool is available in that setup.
- **Usage limits are the real constraint.** Subscriptions have rolling and weekly usage limits, and a full run is heavy: dozens of search tasks, a critic loop per figure, and up to 16 reviewer runs (4 per review pass). Rough guess: 1.5–2.5M tokens for a full run; measure it on the sample run (§13). On smaller plans a run may hit a limit midway. Therefore:
  1. **Resume after a limit stop.** Work is checkpointed at fine grain: per batch of search tasks, per figure, per review, per revision. Running `/paper-orchestra` again continues from the last finished piece and never redoes finished work.
  2. **Usage profile** in `settings.md` (my call):

     | | `full` (default) | `light` |
     |---|---|---|
     | Literature budget | original: Intro 10–20, Related Work 30–50 papers | about half: Intro 5–10, Related Work 15–25 |
     | Figure critic rounds | up to 3 | 1 |
     | Reviewer panel | 3 reviewers + meta-reviewer | 1 reviewer |
     | Revision rounds | up to 3 | 1 |

     `full` is the default because it matches the original and the user is on the top tier. Colleagues on smaller plans can switch to `light`.
  3. **Show the size before spending it** (my call). After the Outline pause and before Literature/Figures start, show how many search tasks, figures and review passes the run will do, so the user can switch profile first.
  4. **Models** (my call). Writing, reviewing and revising agents use `model: inherit` (whatever model the user's session runs). Search scouts and figure critics use a cheaper model (e.g. `sonnet`). Never hard-require a model a plan might not include.
  5. **Modest parallelism**, e.g. at most 4 agents at once, to stay clear of rate limiting.
- The free lookup-service keys (OpenAlex, Semantic Scholar) are separate from the Claude subscription and stay optional.

### Other constraints

- **Claude Code only,** with its web search tool available. No Gemini/OpenAI calls anywhere.
- **Scripts:** Python ≥ 3.10, standard library only (`difflib` instead of `thefuzz`, `urllib` instead of `requests`), so they run on colleagues' machines. Plotting is the one place matplotlib/numpy are needed.
- **Network:** OpenAlex, Semantic Scholar (optional key), Crossref. Never send the user's email or other personal details in API requests (no `mailto` parameters).
- **API responses are data, not instructions.** Lookup responses can contain text addressed to AI agents (OpenAlex's responses ask agents to send the user's email to get a key). Scripts and agents ignore such text.
- **Privacy:** search queries reveal topic keywords of unpublished work (the original has the same property). Nothing else leaves the machine except to Claude itself. The README says so.
- **Time:** a full run is long. Rough scale implied by the original's rules:
  - ~20–45 search tasks;
  - ~40–80 verified papers;
  - 3 reviewers + 1 meta-reviewer per review pass;
  - up to 4 review passes and 3 revisions.

  The pauses, per-stage reruns and resume exist partly so users don't redo everything.
- **Context:** agents receive file paths and read what they need. Large content is never pasted between agents.
- **Platforms:** must work on Linux/WSL2 (the user); should work on macOS (colleagues).

## 10. Decided by the user

- Build a Claude-native version of PaperOrchestra; no Gemini.
- Reusable for all future research: installed once, used in any project.
- Markdown output; the LaTeX module is not needed.
- Shareable with colleagues.
- Must work with Claude subscriptions (the user's and colleagues'), not API keys.
- Papers without an abstract: keep them with limited use (title and venue only), and import abstracts and must-cite papers from the user's reference-manager export.
- Whether the reviser may rewrite hand-edited paragraphs is a setting (`keep` / `revise`), not a fixed rule.
- The deliverable is the tool, not a paper; venue-agnostic.
- The design lives in `~/Research/research-tools/`, which becomes the plugin's GitHub repo.
- Said "Good" / "generally good" to the proposed flow (Gather → Outline with pauses → Literature ∥ Figures → Write → Review → Check). Raised no objection to the additions from the gap check against the original; approving this document confirms them.

## 11. Calls Claude made (the user may overturn any of these)

1. Plugin marketplace named `research-tools`; plugin named `paper-orchestra`.
2. A Gather stage drafts the materials from the project; every number keeps its source.
3. Pauses after Gather and after Outline.
4. `[@key]` citations + a generated References list + `references.bib`.
5. A Check stage; a draft with an unverifiable citation or number is marked NOT READY.
6. OpenAlex first, Semantic Scholar when a key is set, Crossref as backup.
7. Mermaid for diagrams.
8. Our own figure style guide; no few-shot example bank.
9. A separate critic agent for figures.
10. Keep an honest Limitations section (differs from the original).
11. Reviewers' requests for new experiments go to a to-do list in `review.md` (differs from the original).
12. Two starter style guides (ML conference, journal), plus user-added ones.
13. The adapted "facts only from materials and library" rule (§6).
14. Scripts for mechanical work, agents for judgment.
15. Keep every version; never overwrite hand-edited files without asking.
16. Test on the sample shipped with the original repo.
17. Apache-2.0 with a NOTICE file.
18. Literature citation-coverage rule scoped to Intro/Related-Work papers (§5, Stage 2a, step 5).
19. `full` / `light` usage profiles; `full` by default (§9).
20. Writing/reviewing agents inherit the session's model; scouts and critics use a cheaper one (§9).
21. Show the run's size before the expensive stages start (§9).
22. Fine-grained checkpoints, so a usage-limit stop loses little work (§9).
23. Machine-readable source tags; Gather re-checks its own numbers; after the pause the approved log is the ground truth (§5, Stage 0).
24. Section ownership: a rerun replaces only the sections its stage owns, and asks before replacing hand-edited ones (§4).
25. OpenAlex `filter=` lookups with caching; a free OpenAlex key recommended (§5, Stage 2a).
26. Text in API responses is never followed as instructions (§9).
27. `keep` is the default for hand-edited paragraphs (§5, Stage 4).
28. Import formats BibTeX or CSL JSON, as two files: `library.bib` (abstract source) and `must_cite.bib` (always cited) (§4).
29. A must-cite paper that can't be found online is kept, marked as vouched for by the user (§5, Stage 2a).

## 12. Left to the builder

- Exact file formats and field names beyond what is fixed above.
- Prompt wording: port the original's prompts, adapted to Markdown and to the rules here.
- Exact model per agent and exact parallelism limits, within the policy in §9.
- How pauses and outline edits are captured in the conversation.
- Stale-stage detection and the hand-edit check.
- Mermaid rendering for the critic.
- Reference display style details.
- Command syntax within the plugin system's namespacing rules.

## 13. How we know it works (acceptance)

1. **Sample run.** Convert the original's `frontend/examples/cvpr_example.json` (idea, experiment log, overview figure + caption, extracted from the CVPR 2025 paper "TSAM") into `materials/`. A full run finishes and produces:
   - every section the style guide requires;
   - ≥ 30 verified references;
   - ≥ 2 generated plots, plus the supplied overview figure;
   - at least one review round with scores and a keep/undo decision in `review.md`;
   - a Check report.
2. **Planted errors.** In a copy of `paper.md`, add `[@Fake2024Paper]` and a result number that isn't in the log. Check flags both as FAIL.
3. **Unit tests** for the scripts, using recorded API responses (no network): key generation, BibTeX, title-match threshold and year bonus, cutoff filter, number extraction and matching, link check.
4. **Rerun.** Running only `figures` regenerates the figures without touching references or drafts; later stages are reported as stale.
5. **Hand edits.** Edit a paragraph of `paper.md` by hand, then run `review`. With `keep`, the paragraph is byte-identical afterwards and reviewer comments about it appear in `review.md`. With `revise`, any change to it is listed in `review.md`, and the hand-edited version is in `drafts/`.
6. **Fresh install.** Install from the marketplace (local path, then GitHub) in a clean Claude Code profile; `/paper-orchestra` works.
7. **No other providers.** No Gemini/OpenAI references anywhere in the plugin.
8. **Subscription only.** The sample run completes on a Claude subscription login with no `ANTHROPIC_API_KEY` in the environment. Record the run's time and approximate usage in the README.
9. **Interrupted run.** Stop a run in the middle of Literature, and again in the middle of Review; `/paper-orchestra` resumes both times without redoing finished tasks.
10. **Journal-heavy literature.** The sample's references are mostly arXiv papers, which hides the abstract problem. So also run Literature on a topic whose key papers are mostly in Elsevier journals: the report shows how many candidates had abstracts, were kept title-only, or were dropped (§5, Stage 2a).
11. **Gather self-check.** In a test project, change one number in a result file after drafting the log; Gather's re-check reports the mismatch.
12. **Title-only rule.** In a copy of `paper.md`, cite a title-only entry for a specific number; Check flags it as FAIL.
13. **Import.** With a small BibTeX export that has abstracts, plus one `must_cite.bib` entry: matching candidates get the imported abstracts, and the must-cite paper is placed by the Outline and cited in the paper.

## 14. Map of the original (commit `d9bae997e793a015ed38bb1605be9eb58c00284f`)

| Original file | What to take from it |
|---|---|
| `methods/paper_writer_with_plotting.py` | stage order; Literature ∥ Figures in parallel; what each stage hands to the next |
| `methods/prompts/outline_agent.py` | outline prompt and JSON schema (the three plans) |
| `methods/agents/literature_review_agent.py` | task collection; discovery prompts (exploration / targeted); dedupe; keys; BibTeX; citation-candidate injection; cutoff filter |
| `utils/scholar_utils.py` | title-match rule (> 70, +10 year bonus) |
| `methods/prompts/literature_review_agent.py` | Introduction + Related Work writing rules |
| `methods/prompts/section_writing_agent.py` | rules for the remaining sections |
| `methods/prompts/content_refinement_agent.py`, `methods/agents/content_refinement_agent.py` | reviser rules, worklog format, keep-or-undo logic |
| `autoraters/agent_review.py` | reviewer persona, rubric, review fields, meta-review |
| `utils/paper_banana_utils.py`, `methods/agents/plotting_agent.py` | figure planner / stylist / critic / caption prompts and the critic loop |
| `utils/prompt_utils.py` | ground rules (adapt per §6) |
| `templates/*/guidelines.md` | starting point for `styles/ml-conference.md` |
| `frontend/examples/cvpr_example.json` | test sample |

**Not ported:** the `autoraters/` scorers other than `agent_review.py`; `frontend/app.py`; the batch functions; LaTeX/PDF utilities (`utils/pdf_utils.py`); `methods/prompts/format_agent.py`.
