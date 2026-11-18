## Experimental Setup

- **Dataset:** the public dataset of 124 commercial lithium iron phosphate/graphite cells (nominal capacity 1.1 Ah) cycled under fast-charging conditions until they reached 80% of nominal capacity. Cycle lives range from 150 to 2,300 cycles.
- **Splits:** the dataset's published split into a training set (41 cells), a primary test set (43 cells) and a secondary test set (40 cells). The secondary test cells were cycled in a later batch, and several of them used charging protocols that are not in the training set.
- **Calibration:** 10 of the 41 training cells are held out for conformal calibration; every model is fitted on the other 31 cells.
- **Baselines** (all re-implemented by us and trained on the same 31 cells):
  - variance model: an elastic net on the log variance of $\Delta Q_{100-10}(V)$, the single-feature model defined in the dataset paper;
  - discharge model: an elastic net on the six discharge features defined in the dataset paper;
  - Gaussian process regression on the discharge capacity curve of the first 100 cycles, extrapolated to 80% capacity;
  - an LSTM on the sequence of per-cycle discharge capacities of the first 100 cycles.
- **Our model:** monotone gradient-boosted regression trees on the eight features of idea.md: 300 trees, depth 3, learning rate 0.05, chosen by 5-fold cross-validation on the 31 fitting cells.
- **Other hyperparameters:** elastic-net penalty and mixing chosen by 5-fold cross-validation; LSTM with 2 layers of 64 hidden units, trained with Adam for 200 epochs.
- **Hardware:** one laptop CPU with 8 cores, no GPU.
- **Metrics:** root-mean-square error (RMSE, in cycles) and mean absolute percentage error (MAPE) of the predicted cycle life on each test set; for the intervals, the empirical coverage and the mean interval width in cycles.

## Raw Numeric Data

**Table 1: Cycle-life prediction error**

| Model | Primary test RMSE (cycles) | Primary test MAPE (%) | Secondary test RMSE (cycles) | Secondary test MAPE (%) |
| :--- | :--- | :--- | :--- | :--- |
| Variance model (elastic net) | 145 | 15.2 | 205 | 12.3 |
| Discharge model (elastic net) | 102 | 10.9 | 188 | 10.1 |
| GPR on capacity curve | 171 | 17.8 | 240 | 14.6 |
| LSTM on capacity sequence | 158 | 16.4 | 231 | 13.9 |
| Monotone GBRT (ours) | 88 | 9.3 | 162 | 8.7 |

**Table 2: Ablation of the monotone GBRT (RMSE in cycles)**

| Variant | Primary test RMSE | Secondary test RMSE |
| :--- | :--- | :--- |
| Full model | 88 | 162 |
| Without monotonic constraints | 97 | 179 |
| Without resistance features | 93 | 170 |
| Without $\Delta Q_{100-10}(V)$ features | 151 | 226 |

**Table 3: Split-conformal intervals ($\alpha = 0.1$, nominal coverage 90%)**

| Test set | Empirical coverage (%) | Mean interval width (cycles) |
| :--- | :--- | :--- |
| Primary | 90.7 | 312 |
| Secondary | 82.5 | 405 |

**Runtime:** feature extraction takes 1.8 s for all 124 cells, training the GBRT takes 4.2 s, and a prediction takes 0.3 ms per cell.

## Qualitative Observations

- The variance of $\Delta Q_{100-10}(V)$ is the most important feature by split gain in every cross-validation fold.
- Every model has larger errors on the secondary test set. The largest errors are on cells whose charging protocols are not in the training set.
- Coverage on the secondary test set is below the nominal 90%: the exchangeability assumption of split conformal prediction does not hold under this protocol shift.
- The Gaussian-process and LSTM baselines see little capacity change in the first 100 cycles, and they over-predict the cycle life of short-lived cells.
- Without the monotonic constraints, the partial dependence of predicted life on the resistance increase is non-monotone (predicted life rises with resistance growth) in 3 of the 5 folds.
