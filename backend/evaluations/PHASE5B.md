# Phase 5B real-data download and evaluation workflow

## Network diagnosis in this Codex session

The local API health route and local database work. DNS resolved `finance.yahoo.com`, `query1.finance.yahoo.com`, and `raw.githubusercontent.com`; `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, and `NO_PROXY` were unset. TCP port 443 probes failed, and previous application HTTP requests failed at socket creation with Windows `WinError 10013` (access denied). There was no HTTP response, so provider rate limiting was not reached or observed. The failure occurred below application response handling; the API reported a provider error because it could not open the connection.

This managed Codex environment restricts outbound network access. A Windows Firewall profile query was denied by the environment, so this check cannot distinguish the sandbox restriction from a local firewall, antivirus, or endpoint policy that might also block the process. No firewall, antivirus, proxy, or system security setting was changed. If the downloader also fails in a normal Windows terminal, check the local security product's event history and approved proxy configuration with your administrator; do not disable protections.

## Fixed universe and provider

The manual downloader requests Yahoo Finance daily bars through `yfinance` for:

- Stocks: AAPL, MSFT, NVDA, AMZN, TSLA
- S&P 500 ETF proxy: SPY
- Sector proxies: XLK for AAPL/MSFT/NVDA; XLY for AMZN/TSLA

This is a fixed present-day stock list, not a point-in-time S&P 500 membership history. Results cannot be described as survivorship-bias-free S&P 500 backtesting. SPY includes ETF tracking effects and expenses; XLK/XLY are ETF sector proxies, not sector indices.

## Download from a normal Windows PowerShell terminal

Use the existing backend virtual environment from a terminal outside the Codex execution sandbox:

```powershell
Set-Location 'C:\Users\Devin Bedi\.vscode\FinSight-fresh\backend'
.\.venv\Scripts\python.exe .\evaluations\download_market_data.py --start 2010-01-01
```

The provider `end` date is exclusive; omit it to retrieve the latest available data. Add `--end YYYY-MM-DD` for a fixed cutoff. The command prints a snapshot directory. Snapshots are locally cached under `backend/data/market_cache/phase5b/`; a matching complete snapshot is reused. Pass `--refresh` to create a new immutable retrieval snapshot. Partial downloads are recorded per ticker and are not silently treated as complete.

To import and evaluate a printed snapshot path:

```powershell
.\.venv\Scripts\python.exe .\evaluations\run_phase5b_real.py --input-dir '.\data\market_cache\phase5b\snapshot_YYYYMMDDTHHMMSSZ'
```

Outputs stay beside the local cache in `research_output`; the local market cache is excluded from version control. The downloader does not run automatically in the Codex sandbox.

## Data and adjustments

Each ticker CSV retains raw Open/High/Low/Close, Adj Close, Volume, Dividends, and Stock Splits, plus normalized adjusted OHLCV fields. Adjusted OHLC is raw OHLC multiplied by the provider's `Adj Close / Close` factor. Adjusted volume multiplies raw volume by split ratios from later split dates; dividends do not alter share volume. The manifest records source, retrieval timestamp, requested date interval, `yfinance` version, adjustment method, series coverage, row count, SHA-256, and quality report.

Adjustments are provider-reported and may retrospectively include distributions, splits, and later data revisions. Same-date adjusted entry open and exit close share the provider's adjustment basis; ratios cancel a common scale factor, while corporate actions inside the return window are reflected in the adjusted series. Exact historical provider vintages and executable fill prices are unavailable. The forecast anchor is after the completed session bar is available; entry is the next observed session's adjusted open and exit is the adjusted close of future session 5 or 20. This convention is a measurement target, not a verified executable trade.

The importer rejects duplicate or unsorted dates, absent/invalid adjusted OHLC, inconsistent high/low bounds, negative volume, missing symbols where required for an experiment, and file hash/manifest mismatches. It preserves missing volume, does not synthesize dates or bars, reports long calendar gaps, and compares stock dates with SPY dates. Missing sessions are reported rather than forward-filled.

## Evaluation

The real runner calls the Phase 5A point-in-time builder independently for each stock, using SPY and its mapped sector ETF on common observed dates. It writes separate `real_provider_data` feature and experiment artifacts; synthetic outputs retain their distinct `synthetic_only` labels. It runs 5- and 20-session stock-return and SPY-excess-return tasks with zero, training-period mean, Ridge, and L2 logistic baselines. It records per-stock and pooled results, walk-forward folds, out-of-sample counts/dates, and descriptive regime-group metrics.

Paired MAE-reduction intervals use a circular moving-block bootstrap within each ticker/fold, with block length equal to the forecast horizon. This retains some serial dependence from overlapping targets. Intervals are descriptive and are not significance tests. Out-of-sample predictions for each model and baseline share the same dates. Logistic Brier scores and classification metrics are reported for uncalibrated outputs; they are not trustworthy calibrated probabilities. Prediction metrics do not establish profitability.

No real-market dataset or performance metrics are present in this repository because provider access was blocked in the Codex environment. Run the manual download/import command to create them locally. Do not treat the fixed current universe as historical S&P 500 membership.
