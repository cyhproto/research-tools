# Source tags

Every number in `materials/experiment_log.md` carries a tag that says where it came from. `po log verify` checks each tag against the file it names. Paths are relative to the project root.

## Grammar

- `[src: <path> | row=<first-column value> | col=<header>]` for `.csv` and `.tsv` files. `row=#<n>` selects the n-th data row (1-based); `row=last` selects the last row.
- `[src: <path> | path=<key.key.0.key>]` for `.json` files.
- `[src: <path> | line=<n>]` for any other text file, with an optional `| pattern=<regex with one group>`.
- Any `src` tag may add `| scale=<number>`, and may carry an id: `[src#<id>: ...]`, where the id matches `[A-Za-z0-9_-]+`.
- `[calc: <fn>(<id>, ...)]`, where `fn` is one of `mean`, `std` (sample, n-1), `pstd` (population), `min`, `max`, `sum`, `sub` (exactly 2 args), `div` (exactly 2 args). It works on the resolved, scaled source values of the ids.
- A `calc` tag may use ids defined anywhere in the log, for example in a final `## Source values` section. If an id is defined twice, a `calc` uses its closest definition above it, or the first one below it when none is above.
- `[manual: <free text>]`.
- A tag applies to the closest non-tag number before it on the same line.

Fields inside a tag are separated by space-pipe-space (` | `, with spaces). A bare `|` without spaces is not a separator, so a regex `pattern=` may contain `|`. A path containing `|` (for example `[src: a.csv|row=1|col=b]`) is reported as unreadable with "fields must be separated by ' | ' (with spaces)".

CSV and TSV files are read as UTF-8 (a BOM is ignored) and blank rows are skipped, so they do not count for `row=#<n>` or `row=last`.

## Examples

Table cell (`scale=100` turns 0.8731 into 87.31):

    Ours 87.3 [src#a1: results/metrics.csv | row=seed_1 | col=val_acc | scale=100]

Row by position, and the last row:

    Seed 2 87.9 [src#a2: results/metrics.csv | row=#2 | col=val_acc | scale=100]
    Final 70.0 [src: results/r.tsv | row=last | col=acc | scale=100]

JSON value:

    F1 0.95 [src: results/summary.json | path=test.per_class.1]

Text file line with a pattern:

    Loss 0.4123 [src: logs/train.log | line=3 | pattern=val_loss=([0-9.]+)]

Calculation over tagged ids:

    Mean 87.6 [calc: mean(a1, a2)]

Manual (taken from outside the project; reported, never verified):

    Dataset size 20000 [manual: dataset paper, Table 1]

## Matching

A written number matches its source when `abs(written - source) <= 0.5 * 10**-decimals + 1e-9`, where `decimals` is the number of digits written after the point.

## Limitations

- `.ipynb`, image and PDF files cannot be a source; export the value to a CSV, JSON or text file.
- Numbers glued to letters (`1.2M`, `3rd`, `10k`) are not recognised as numbers.
- Integers below 10 without `%` are treated as trivial and need no tag.
