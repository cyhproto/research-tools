# Figure style guide

Every figure follows this guide. It applies to plots (matplotlib) and to diagrams (Mermaid).

## Palette (Okabe-Ito, colour-blind safe)
`#E69F00`, `#56B4E9`, `#009E73`, `#F0E442`, `#0072B2`, `#D55E00`, `#CC79A7`, `#000000`

## Colours
- Our method is always `#D55E00`, in every figure.
- Baselines take the remaining colours in the order above, skipping `#D55E00`: `#E69F00`, `#56B4E9`, `#009E73`, `#F0E442`, `#0072B2`, `#CC79A7`, `#000000`.
- A baseline keeps the same colour in every figure of the paper.

## Text and output
- Fonts are at least 8 pt at final size.
- Save PNG at 300 dpi.
- No title or caption text inside the image. The caption lives in the paper text.

## Plot elements
- Legends never cover data.
- Use a light grid.
- No 3D charts and no pie charts, unless the figure plan asks for them.
- Draw error bars when the log has a standard deviation or several seeds.
- Axis labels carry units.
- Method names are identical to the names used in the paper.

## Mermaid diagrams
- Use `flowchart LR` by default.
- At most 15 nodes.
- Node labels have at most 4 words.
