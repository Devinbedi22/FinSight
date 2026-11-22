# Phase 5D forward forecast tracking

Phase 5D is a local, research-only append-only registry. It does not connect to
the live forecast endpoint or modify the Phase 5C evaluation artifact. The
registry is a SQLite file under `backend/data/forecast_tracking/`; verified raw
market snapshots are copied under `snapshots/` and referenced by the SHA-256 of
their original manifest. The existing Phase 5C JSON is pinned by its content
hash and its selected configurations are recorded as a reference. Existing
holdout predictions and metrics remain where they are and are not rewritten.

## Register a snapshot and create forward predictions

Run from `backend` using its existing virtual environment:

```powershell
.\.venv\Scripts\python.exe .\evaluations\run_phase5d.py forecast `
  --input-dir .\data\market_cache\phase5b\snapshot_YYYYMMDDTHHMMSSZ `
  --phase5c-reference .\data\market_cache\phase5b\snapshot_20261121T093632Z\phase5c_output\phase5c_evaluation.json
```

The command verifies the provider snapshot, archives it without changing the
source, and records predictions for each available configured stock at the
latest common session across stocks, SPY, and the mapped sector ETF. Each run
creates forecasts for 5 and 20 sessions, stock and SPY-excess returns, and three
models: zero return, per-ticker mature-training mean, and fixed Ridge alpha 10.
The Ridge configuration was chosen using Phase 5C's pre-holdout validation and
is held fixed; it is a research baseline, not a promoted production model.

The training labels must end strictly before the forecast anchor. The registry
stores training anchor range/count/cutoff, fixed model parameters and hash,
features and hash, schema version, snapshot manifest hash, provider retrieval
time, and forecast creation time. A semantic uniqueness key prevents re-running
the same model/ticker/target/horizon/anchor forecast from creating a duplicate,
even if the later download has a different snapshot ID. Forecast rows have
SQLite update/delete guards. Their initial status remains `pending` forever;
later assessments go into a separate immutable `outcomes` table.

The exact future eligibility session is not knowable at forecast creation from a
daily-bar provider. The forecast row therefore has a null eligibility date; a
completed outcome records its observed exit session as the eligibility date.

## Register snapshots and evaluate outcomes

Snapshots can be archived separately without generating forecasts:

```powershell
.\.venv\Scripts\python.exe .\evaluations\run_phase5d.py register-snapshot `
  --input-dir .\data\market_cache\phase5b\snapshot_YYYYMMDDTHHMMSSZ
```

On a later retrieval, evaluate pending forecasts with:

```powershell
.\.venv\Scripts\python.exe .\evaluations\run_phase5d.py evaluate `
  --input-dir .\data\market_cache\phase5b\snapshot_YYYYMMDDTHHMMSSZ
```

Evaluation requires a market snapshot retrieved after the forecast's source
snapshot. It measures entry at the first SPY-observed session after the anchor
adjusted open and exit at the fifth/twentieth SPY-observed session adjusted
close, matching Phase 5A's target. Stock bars must exist on all those benchmark
sessions; missing bars are recorded as an incomplete mature assessment, never
forward-filled. If the benchmark has not yet supplied enough later sessions,
the horizon is reported as not mature and no outcome row is added. An incomplete
forecast can be reassessed against a later snapshot; each assessment remains a
separate immutable row.

For each forecast/evaluation snapshot, outcome rows store realized stock,
benchmark, excess, and forecast-target return, direction, start/end sessions,
bar hashes, and any revisions detected relative to the forecast snapshot.
Snapshots and bar hashes are immutable registry records. Changed historical
bars on dates shared by two snapshots are recorded in `snapshot_revisions`;
changed outcomes in later snapshots are appended, never substituted for older
assessments. Hash checks detect altered archive files when they are loaded.

## Limitations

Yahoo Finance adjusted bars can be revised retrospectively and do not provide
true historic vintages. Revision comparison only detects differences between
snapshots that were actually archived. SPY serves as the observed session
calendar and benchmark proxy; if SPY itself omits a session, this workflow cannot
independently establish the exchange calendar. Current ticker membership is a
fixed research universe with survivorship limitations. Adjusted open/close
returns do not model verified fills, spreads, fees, or market impact. Forward
samples will be small initially; reports are descriptive and do not claim
statistical significance or trading profitability.
