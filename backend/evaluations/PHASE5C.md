# Phase 5C model improvement and holdout protocol

Phase 5C uses the already validated Phase 5B Yahoo Finance snapshot and its persisted real-provider feature datasets. It does not call market-data providers, regenerate prices, modify the database, or touch the live forecast endpoint. Install its optional CPU research estimators from `backend` with:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[research]"
```

Run once against the existing snapshot:

```powershell
.\.venv\Scripts\python.exe .\evaluations\run_phase5c.py --input-dir .\data\market_cache\phase5b\snapshot_20261121T093632Z
```

Results are written to that snapshot's `phase5c_output/phase5c_evaluation.json`, separate from the Phase 5B artifacts. The runner verifies the original snapshot manifest and CSV hashes and checks that every Phase 5B feature artifact names the same manifest hash. It refuses to overwrite an existing result, preventing accidental repeated use of the final holdout.

## Chronology and holdout

The shared pooled models use features from all five fixed tickers, without ticker identity as a model feature. Validation and holdout boundaries are fixed by calendar date, so per-ticker rows are never randomly split:

- Validation windows: calendar years 2020, 2021, 2022, and 2023; plus 2024-01-02 through 2024-09-25.
- Final holdout anchors: 2024-10-24 through the last eligible anchor in the snapshot.
- Every training label must end strictly before its validation or holdout start. Validation labels are also required to mature before 2024-10-24.
- The final holdout is excluded from candidate selection, feature missingness/drift/correlation analysis, permutation importance, and feature ablations. Selected configurations are fit on all mature pre-holdout labels and evaluated on the holdout once.
- Median imputation and scaling are learned from each fold's training rows only.

The five fixed validation blocks have minimum pooled training and validation row checks. They are meaningfully sized calendar windows rather than a loop over a remainder that creates a tiny final fold. Final holdout is at least 1,000 ticker-observations or evaluation stops.

## Models and baselines

Continuous-return candidates are zero return, per-ticker historical mean, Ridge (alpha 0.1/1/10), Random Forest, and HistGradientBoosting. Direction candidates are training-period constant prevalence, majority class, momentum sign, L2 LogisticRegression, RandomForestClassifier, and HistGradientBoostingClassifier. Class probabilities from classifiers are uncalibrated; Brier and log loss are reported descriptively.

Random Forest and HistGradientBoosting use compact deterministic CPU parameter grids (60–80 trees and 60–100 boosting iterations), a fixed random seed, and one Random Forest worker. Regression candidates are selected by pooled validation MAE; classifiers by validation Brier score. No hyperparameter is selected using holdout observations. Progress is printed per candidate. The holdout block bootstrap uses 500 paired replicates within ticker with horizon-length blocks.

The momentum direction baseline uses trailing `momentum_20d` for stock return and `relative_return_20d_vs_sp500` for excess return. A missing momentum observation is represented as neutral probability 0.5, not fabricated as a directional signal.

## Feature analysis

On pre-holdout rows only, the output reports missingness, early-versus-validation feature means and standardized shifts, and high absolute Pearson correlations. The selected best validation regression model gets permutation importance on a capped sample from the final validation window. Ridge validation ablations remove trend, momentum, volatility, and sector-relative groups one at a time. These diagnostics are associational; correlated features can mask or exchange importance, and no causal interpretation is intended.

## Statistical reporting and limitations

Validation and final-holdout results are separately named in the JSON. Both pooled and per-ticker metrics, selected parameters, candidate validation scores, validation-window performance, holdout regime summaries, and identical-row baseline comparisons are retained. Final-holdout MAE differences use paired circular moving-block resampling within ticker, with block length equal to the target horizon. Intervals are descriptive, not significance tests. Forecast rows overlap by design, so ordinary independent-observation intervals are inappropriate.

Yahoo adjusted bars may be revised and do not provide historic as-reported vintages. The fixed current ticker list is not historical S&P 500 membership; SPY, XLK, and XLY are ETF proxies. News and SEC fundamentals remain excluded. Adjusted-open-to-adjusted-close targets are return measurements, not a costed or executable trading strategy. No prediction metric establishes profitability.
