# toyproject

A small image-classification experiment. We train a compact convolutional network with label smoothing on a two-class dataset, and ask whether such a small model is stable across random seeds: do two runs that differ only in the seed reach similar validation and test accuracy?

Files:
- `logs/train.log`: validation loss and learning rate at selected epochs of one training run.
- `results/metrics.csv`: validation and test accuracy for each seed.
- `results/summary.json`: test F1, overall and per class.
- `notebooks/analysis.ipynb`: a placeholder for the analysis notebook (no cells yet).
