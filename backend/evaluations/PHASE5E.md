# Phase 5E forward-tracking operations

Phase 5E is research-only. It does not train or tune models, call the production
forecast endpoint, or change frontend behavior. It uses the existing Phase 5B
Yahoo downloader and Phase 5D append-only SQLite registry.

## Manual update after US market close

Run from the backend directory after the regular US close. The command waits until
**4:15 p.m. America/New_York** before treating the current date's daily bars as
complete. That 75-minute buffer also delays early-close days conservatively.
Before the buffer, it can ingest and evaluate earlier complete sessions, but it
will not use current-date bars for outcomes or forecasts. A forecast is created
only when every configured stock, SPY, and its sector proxy share the current
market date; running on weekends, holidays, or with stale data does not create a
backdated forecast.

```powershell
Set-Location 'C:\Users\Devin Bedi\.vscode\FinSight-fresh\backend'
\.venv\Scripts\python.exe .\evaluations\run_phase5e.py update
\.venv\Scripts\python.exe .\evaluations\run_phase5e.py status
```

The update order is: download a fresh snapshot to temporary staging; validate
the manifest, hashes, required tickers, quality report, freshness, and session
alignment; make a verified registry backup; register/archive the snapshot and
compare bar hashes; evaluate mature existing forecasts; then create forecasts
only for a new completed current-date anchor. The detailed downloader progress
is captured; the command prints a concise JSON summary.

The downloaded snapshot is archived at
`backend/data/forecast_tracking/snapshots/` and its full manifest hash is kept
in SQLite. A failed download or invalid snapshot exits before registry changes.
If an interrupted process leaves a verified snapshot archive before its SQLite
commit, the next update discovers and registers the orphan. If interrupted
during forecast insertion, semantic uniqueness makes a same-anchor retry fill
missing records without altering prior forecasts. Outcome uniqueness prevents
repeating an assessment for the same forecast and evaluation snapshot.

Exit codes: `0` success; `1` unexpected operation failure; `2` snapshot rejected;
`3` downloader failure; `4` registry audit reports an integrity problem.

## Status and audit

```powershell
\.venv\Scripts\python.exe .\evaluations\run_phase5e.py status
\.venv\Scripts\python.exe .\evaluations\run_phase5e.py audit
```

Status reports total/pending/matured forecasts, currently incomplete outcomes,
latest anchor and registered snapshot, detected bar revisions, and descriptive
performance for completed outcomes. Performance is grouped by model, horizon,
and target. Groups under 30 outcomes or five distinct forecast anchors are
explicitly labeled too small for meaningful conclusions. Overlapping 5/20
session returns remain dependent even when counts exceed those thresholds; the
status metrics are not significance tests or profitability estimates.

Audit checks SQLite append-only triggers and uniqueness, strict training label
cutoffs, forecast-to-snapshot hash links, every archived snapshot's manifest and
CSV hashes, and the pinned Phase 5C artifact SHA-256. The audit reads the Phase
5C artifact but never rewrites it.

## Backups and recovery

Create a standalone consistent backup at any time:

```powershell
\.venv\Scripts\python.exe .\evaluations\run_phase5e.py backup
```

Backups are stored in the ignored `backend/data/forecast_tracking/backups/`
directory. They use Python's SQLite backup API, run `PRAGMA integrity_check`,
and verify registry table counts before being published under a unique filename.
Existing backups are never overwritten or automatically deleted.

To restore safely, stop registry-using processes and copy the chosen backup to a
new registry filename; do not overwrite the active database:

```powershell
Copy-Item -LiteralPath '.\data\forecast_tracking\backups\forecast_registry_backup_<timestamp>.sqlite3' `
  -Destination '.\data\forecast_tracking\forecast_registry_restore_check.sqlite3'
\.venv\Scripts\python.exe .\evaluations\run_phase5e.py audit `
  --registry '.\data\forecast_tracking\forecast_registry_restore_check.sqlite3'
```

After verifying the restored copy, use `--registry` with that path for subsequent
commands. Keep the snapshot archive directory alongside it because registry
rows reference archived snapshots by path. Preserve the original backup and the
previous active registry until the restored copy is confirmed.

## Session and data caveats

SPY is used as the observed benchmark session sequence, not as an authoritative
exchange calendar. The report compares stock, benchmark, and sector dates;
missing stock bars on observed SPY dates and dates found in other symbols but
missing from SPY are reported. Calendar gaps over four days are flagged as
unconfirmed; closures are not inferred from SPY absence. No independent market
calendar is installed, so simultaneous omissions across all symbols cannot be
identified here. A common anchor must exist across the full configured universe.

Snapshots may contain a current-date partial bar before the close buffer; such
bars are recorded for provenance but excluded from outcomes and features. Yahoo
adjusted history may be retrospectively revised; revision detection compares
only snapshots actually archived. A warning or validation failure in a fresh
manifest blocks registry updates. Provider rate limits or the managed
environment's network restrictions can prevent the download; a failed update
does not advance the registry, and no retry loop is used.

No Windows Task Scheduler job is created by this phase. If later desired, the
manual command can be scheduled by the user for a weekday evening, with a
separate notification policy for nonzero exit codes and provider failures.
