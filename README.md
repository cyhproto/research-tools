# research-tools

Claude Code plugins for research work, shared as a plugin marketplace.

| Plugin | What it does |
| --- | --- |
| [paper-orchestra](plugins/paper-orchestra/README.md) | Drafts a verified Markdown research paper from a project's code, results and notes: outline, literature, figures, writing, simulated review, checks. |

## Install

In Claude Code:

```
/plugin marketplace add cyhproto/research-tools
/plugin install paper-orchestra@research-tools
```

It runs on a Claude subscription; no Claude API key is needed. The [plugin README](plugins/paper-orchestra/README.md) covers requirements, usage and cost.

## License

Apache License 2.0; see [LICENSE](LICENSE). paper-orchestra adapts prompts and logic from Google Research's [PaperOrchestra](https://github.com/google-research/paper-orchestra) (Apache-2.0); see its [NOTICE](plugins/paper-orchestra/NOTICE).
