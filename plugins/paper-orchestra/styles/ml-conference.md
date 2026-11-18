---
name: ml-conference
sections:
  - Abstract
  - Introduction
  - Related Work
  - Method
  - Experiments
  - Conclusion
  - Limitations
optional_sections:
  - Appendix
literature_sections:
  - Introduction
  - Related Work
length_words: [5500, 7500]
blind_review: true
citation_style: author-year
required_statements: []
language: English
---
# ML conference style

Guidance for a double-blind machine learning conference paper written in Markdown.

Adapted from PaperOrchestra (Copyright 2026 Google LLC, Apache-2.0), templates/iclr2025/guidelines.md and templates/cvpr2025/guidelines.md; modified.

## Anonymity

- The submission is double-blind. Do not include author names, affiliations, acknowledgments or links that identify the authors.
- Cite your own earlier work in the third person ("Earlier work by Smith (2024) showed..."), never "in our earlier work".
- Do not refer to a public preprint of the paper, and use anonymous links for code and data.

## Length and structure

- The main text is 5,500 to 7,500 words, excluding References and the Appendix.
- Use the sections in order: Abstract, Introduction, Related Work, Method, Experiments, Conclusion, Limitations.
- The Appendix comes after References and is optional.
- Optional Ethics and Reproducibility statements go at the end of the main text, before References, and stay short (about one page each).

## Abstract

- The abstract is one paragraph, with no lists, citations or section references.
- State the problem, the approach, the main result and why it matters.

## Tone

- Write dense, objective, technical prose. State claims precisely and support each one with evidence or a citation.
- Avoid marketing language and unsupported superlatives. Define notation at first use and keep it consistent.
- Do not refer to line or page numbers.

## Citations

- Use author-year citations. Narrative: "Gomu et al. (2024) show...". Parenthetical: "(Gomu et al., 2024)".
- Every in-text citation has an entry in References, and every entry is cited.

## Figures and tables

- Figures and tables must be clear and legible and referred to in the text.
- Figure captions go below the figure. Table captions go above the table.
- Write captions in lowercase except for the first word and proper nouns.

## Reviewer notes

The reviewer is an ML conference reviewer. Judge novelty, technical soundness, strength of the experimental evidence, clarity, and whether claims match the results. Expect baselines, ablations and honest limitations.
