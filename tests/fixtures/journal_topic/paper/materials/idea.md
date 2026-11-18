## Problem Statement

New lithium-ion cell designs and fast-charging protocols are validated by cycling cells until their capacity falls to 80% of nominal, which takes months. A model that predicts a cell's cycle life from its first 100 cycles, before capacity fade is visible, would shorten this loop. Early-prediction models on public fast-charging data give point predictions only, and their errors grow on cells charged with protocols that were not in the training data, so a test engineer cannot tell which predictions to trust.

## Core Hypothesis

Features of the discharge voltage curve from the first 100 cycles, combined with monotonic constraints that encode known degradation trends, let a gradient-boosted tree model predict cycle life more accurately than linear early-prediction models; and split-conformal prediction intervals around its predictions reach their nominal coverage on cells charged with protocols seen in training.

## Proposed Methodology

- **Features per cell**, from cycles 2 to 100:
  - the variance, minimum and skewness of $\Delta Q_{100-10}(V) = Q_{100}(V) - Q_{10}(V)$, the difference between the discharge capacity-voltage curves of cycle 100 and cycle 10, sampled at 1,000 voltages between 2.0 V and 3.5 V;
  - the slope and intercept of a linear fit to discharge capacity from cycle 2 to cycle 100;
  - the internal resistance at cycle 2, and its change from cycle 2 to cycle 100;
  - the average charge time over the first 5 cycles.
- **Target:** $y = \log_{10} N$, where $N$ is the first cycle at which the discharge capacity falls below 80% of the nominal capacity.
- **Model:** gradient-boosted regression trees with monotonic constraints. The predicted log cycle life may not increase with the variance of $\Delta Q_{100-10}(V)$, with the magnitude of the capacity-fade slope, or with the resistance increase.
- **Prediction intervals:** split conformal prediction. A calibration set of cells is held out from the training cells. For calibration cell $i$ the residual is $r_i = |y_i - \hat{y}_i|$ in log space, and $q$ is the $\lceil (n+1)(1-\alpha) \rceil$-th smallest of the $n$ residuals. The interval for a new cell is $[10^{\hat{y}-q}, 10^{\hat{y}+q}]$ cycles, with $\alpha = 0.1$.

## Expected Contribution

- An early cycle-life predictor that uses only the first 100 cycles and keeps known degradation trends through monotonic constraints.
- Prediction intervals for early cycle-life prediction, with their coverage measured on cells charged with seen and with unseen protocols.
- A comparison with re-implemented linear, recurrent and Gaussian-process baselines on a public dataset of 124 fast-charged cells.
