# FinSight — financial-news inference POC

This repository contains a runnable news pipeline and an S&P 500 research frontend. It uses pretrained, non-generative models:

- `stocky-ai/stock-predictor-scratch` retrieves candidate symbols from Nasdaq Trader's current active, non-test, non-ETF listings.
- `techandy42/FinancialBERT` Model v2 applies the FinBERT encoder and released regression head to the top five recent stored headlines retrieved for one company, producing a next-month expected return.

The forecast page plots observed daily adjusted closes and a single 30-day model forecast point. It is experimental, not a calibrated path, causal estimate, or investment recommendation.

## What runs

- The Companies view covers S&P 500 constituents and retrieves actual adjusted daily prices.
- Google News RSS ingestion runs automatically every 15 minutes while the backend is running; articles are deduplicated by URL and persisted.
- The News view is a single newest-first infinite feed. Older stories load as the user scrolls; no manual ingestion button or separate Events page is needed.
- Each S&P 500 company page retrieves the best-ranked recent stored headlines, runs FinancialBERT Model v2 regression on the combined headline text, and plots the expected 30-day point beside actual price history.

## Run locally (Bash)

Requires Python 3.11+, Node.js 20.9+, and internet access. PostgreSQL/Docker is optional for the POC; SQLite works locally. From the repository root:

```bash
python -m pip install -e 'backend[dev]'
mkdir -p backend/app/ml/artifacts/financialbert
curl -L 'https://drive.google.com/uc?export=download&id=1g-HDbEMdaMrWHFKxjE7UmLu_Tf8kwhqB' \
  -o backend/app/ml/artifacts/financialbert/model_regressor_weight_v2.pth
```

Run the backend in one terminal (from the repository root):

```bash
cd backend
DATABASE_URL=sqlite:///./finsight.db alembic upgrade head
DATABASE_URL=sqlite:///./finsight.db NEWS_INGEST_ENABLED=false python -m uvicorn app.main:app --reload
```

Run the frontend in a second terminal:

```bash
cd frontend
npm ci
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1 npm run dev
```

Open <http://localhost:3000>; backend docs are at <http://localhost:8000/docs>. The first Stocky use downloads Hugging Face weights; Stocky is approximately 1.36 GB. The FinancialBERT regression checkpoint must be present at the configured path. For PostgreSQL, set the appropriate `DATABASE_URL` and start the Compose database separately. Background polling can be disabled with `NEWS_INGEST_ENABLED=false`.

## API

- `GET /health`
- `GET /api/v1/universe/us-listed` (add `?refresh=true` to refetch)
- `GET /api/v1/universe/sp500` (legacy comparison endpoint)
- `POST /api/v1/analyze` — body: `{"headline":"...", "summary":"..."}`
- `GET /api/v1/news?limit=30&offset=0&ticker=NVDA`
- `GET /api/v1/news/{id}` — persisted article with ticker-level impact classes
- `GET /api/v1/companies/{ticker}/prediction` — observed daily closes, retrieved recent headlines, and FinancialBERT expected return/forecast price
- `POST /api/v1/news/ingest` — body: `{"limit":25}`

## Research limitations

This is a model integration POC, not evidence of a trading edge. FinancialBERT's upstream notebook uses a random split and selects epochs using test loss, so its evaluation is not a strict out-of-time validation. This app approximates the upstream retrieval flow using Stocky-ranked stored news rather than Bing plus Cohere. The predicted return is a single experimental point forecast. News comes from one Google News RSS query. Prices are delayed adjusted daily closes via yfinance, not real-time data.
