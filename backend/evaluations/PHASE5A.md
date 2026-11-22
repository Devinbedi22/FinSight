# Phase 5A forecasting foundation

This folder contains a standalone price-only research pipeline. It does not change the live prediction route or reuse its output as a target. Historical news and SEC fundamentals are excluded until true point-in-time availability can be established.

## Forecast contract

- Anchor: after the completed trading session on date `t` and its adjusted daily OHLCV bar is available.
- Information cutoff: no later than the anchor date's completed bar. Each row records `forecast_anchor_date`, `information_cutoff`, `feature_as_of_date`, and `feature_observation_date`.
- Realistic execution convention: enter at the next observed trading session's adjusted open; exit at the adjusted close of the 5th or 20th future session. This avoids assuming an order could fill at an already completed close.
- Stock return: `exit adjusted close / next-session adjusted open - 1`.
- Benchmark return: same calculation for the S&P 500 proxy over the same dates. Excess return is stock return minus benchmark return.
- Direction: positive when the relevant stock/excess return is above zero; negative when below zero; exact zero has no direction label.

## Dataset schema

Each row includes ticker/sector, anchor and information cutoff dates, feature observation/source metadata, a fixed feature map with missing values retained as JSON `null`, and per-horizon target values plus entry/exit dates and methods. Features call the Phase 4 market-context calculator with only bars through the anchor. The builder accepts historical OHLCV from a caller; it does not fetch market data or claim a historical constituent universe.

Features include price/SMA and price/EMA gaps, SMA/EMA relationships, RSI, normalized MACD fields, Bollinger position, ATR/price, 20-day volatility, volume ratio, 20/252-session momentum, S&P 500 relative return/correlation/relative volatility, sector proxy relative return/relative volatility, and one-hot observed market-regime labels.

## Splits and preprocessing

Walk-forward folds expand chronologically. The last training labels that end on/after the validation start are purged. Validation labels ending on/after the test start are purged. The validation block selects regularization; the final model is refit using only mature training plus validation samples before the test boundary. Test rows are never used for feature imputation, scaling, model fitting, or hyperparameter choice. The scaler and median imputer are fit on the applicable training rows; all-missing training features are dropped. No random split is used.

## Baselines and metrics

The runner reports zero-return, training-period mean, Ridge regression, and L2 logistic direction baselines. Metrics include MAE, RMSE, improvement in MAE over zero and training-mean baselines, directional accuracy, balanced accuracy, and Brier score for logistic probabilities. Logistic outputs are not calibrated probabilities in this phase. Prediction metrics do not establish profitable trading performance.

## Data caveats

Yahoo Finance historical bars may be revised after corporate actions or provider corrections, so an adjusted history downloaded today is not a true historical data vintage. Current S&P 500 membership creates survivorship/look-ahead risk if callers use it to select past companies. The pipeline reports these caveats and does not automatically fetch current constituents. No news sentiment or SEC facts are added because historical availability has not been established.

## Reproduce the synthetic mechanics check

From `backend`:

```powershell
.\.venv\Scripts\python.exe .\evaluations\run_phase5a_synthetic.py
```

The runner uses fixed seeds and synthetic prices. It writes `forecast_phase5a_synthetic_dataset.json` and `forecast_phase5a_synthetic.json`, both labeled `synthetic_only`. The experiment records its fixture seeds, model settings, Git head, source-file digest, feature definitions, split periods, and out-of-sample predictions. The metrics validate code paths, not real-market predictive performance. Overlapping test outcomes are dependent; no confidence intervals are reported. The live historical evaluation is blocked in this environment because outbound Yahoo Finance requests are denied and no local historical market dataset is available.
