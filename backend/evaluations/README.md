# Financial news review seed

This is a small, source-linked pilot set for manual review. The local FinSight news archive contained zero articles when it was assembled, so this seed uses public headlines and is smaller than the requested 50–100 articles. It is not a random or statistically representative sample.

The CSV contains unique sourced headlines plus two clearly marked synthetic URL variants for canonical-deduplication checks. `human_*` fields are intentionally blank and `human_review_status` is `not_reviewed`; no ground-truth labels or accuracy scores are supplied.

Run the evaluation from `backend` after the `ProsusAI/finbert` weights are available locally:

```powershell
$env:HF_HUB_OFFLINE = '1'
.\.venv\Scripts\python.exe .\evaluations\run_review_seed.py
```

The script runs the real configured FinBERT model, persists each unique headline to an in-memory SQLite database through the production sentiment worker, and writes model outputs, timing, curated name/ticker matches, and title-pattern event signals to the CSV. It does not invoke Stocky or the financial-relevance model: those outputs require their model artifacts and live universe, so the `matched_tickers` column is explicitly a small-universe entity-matcher result, not full-pipeline retrieval.

The source links and publication dates are included for reproducibility. The review seed is an evaluation artifact, not part of FinSight's production news archive.
