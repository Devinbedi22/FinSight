# AI-Powered Financial News Sentiment Trading Strategy

## Project Overview

This project explores the application of Natural Language Processing (NLP) to financial news sentiment for algorithmic trading. It involves building a robust system to analyze market sentiment from headlines using Hugging Face's FinBERT model and integrating it with technical indicators to generate actionable trading signals. The strategy was backtested on historical data for leading NASDAQ companies to evaluate its performance.

## Strategy Implemented

The core trading strategy is designed to capitalize on significant negative news sentiment combined with bearish technical signals:

* **Sentiment Signal:** Utilizes **Hugging Face's FinBERT model** to classify daily financial news headlines related to a company as positive or negative.
* **Technical Signal:** Checks if the **5-day Exponential Moving Average (EMA)** of the stock's closing price is lower than its **20-day EMA**, indicating a short-term bearish trend.
* **Trading Action:** If **negative news sentiment** is detected **AND** the **5-day EMA is below the 20-day EMA**, the strategy initiates a **short position** (or exits any long position) for a **3-day holding period**.

## Data Used

* **News Data:** Comprehensive historical news headlines and associated metadata for at least **10 years** for each of the selected companies.
* **Stock Data:** Historical daily stock prices (Open, High, Low, Close, Volume) for the corresponding companies, covering the period from 2009 to 2020.
* **Company Selection:** The strategy was tested on the **10 companies with the largest market capitalization** on the NASDAQ exchange around the start of the backtesting period (e.g., mid 2009).

## Backtesting & Results

The strategy was rigorously backtested using **Python** for a historical period spanning from **2009 to 2020**.

* **Scope:** Performance was evaluated across the portfolio of 10 selected NASDAQ large-cap companies.
* **Findings:** The backtesting results showed mixed performance. For some companies, the implemented strategy **outperformed a simple buy-and-hold strategy** over the 12-year period, while for others, it **underperformed**.
* **Key Insight:** This specific combination of FinBERT sentiment and EMA crossover proved to be the **best-performing strategy among numerous other strategies explored and tested** during the project's development. This highlights the potential of combining diverse signals, even if market efficiency makes consistent outperformance challenging.

## Technologies Used

* **Python:** Primary programming language.
* **Pandas:** For robust data manipulation, cleaning, and time-series analysis.
* **Hugging Face Transformers:** Specifically for implementing and leveraging the **FinBERT** pre-trained language model for financial sentiment analysis.
* **Yfinance (or similar data source):** For retrieving historical stock data.
* **Custom Backtesting Engine:** The backtesting simulation was built directly in Python (not relying on external backtesting frameworks like Backtrader), demonstrating a deep understanding of trade execution logic, position management, and performance calculation.

## Future Enhancements

* **Advanced NLP:** Explore more sophisticated NLP techniques, such as aspect-based sentiment analysis, entity linking, or transformer models fine-tuned on custom financial datasets.
* **Risk Management:** Implement more robust risk management techniques, including dynamic position sizing, stop-loss, and take-profit orders.
* **Transaction Costs:** Model realistic transaction costs (commissions, slippage) into the backtesting engine for a more accurate performance evaluation.
* **Machine Learning for Signal Fusion:** Use supervised or unsupervised learning models to combine sentiment and technical indicators for more nuanced signal generation.
* **Portfolio Management:** Extend the strategy from a single stock focus to a diversified portfolio.
* **Alternative Data:** Incorporate other alternative data sources (e.g., social media sentiment, satellite imagery, supply chain data).

---

## Key Results

The table below summarizes the core results computed from `returns.csv`.

| Metric | Value |
|---|---:|
| Number of companies evaluated | 16 |
| Average CAGR (strategy) | 27.96% |
| Average CAGR (buy & hold) | 27.05% |
| Average improvement (strategy − buy & hold) | 0.91 percentage points |
| Best performing company (strategy CAGR) | NFLX (54.57%) |
| Largest improvement over buy-and-hold | AXP (+4.14 percentage points) |
| Companies where strategy outperformed buy & hold | 12 of 16 |
| Worst relative performance (largest negative improvement) | NVDA (−3.50 percentage points) |

## Results

Below are the key visual results from the backtest and analysis. Each figure is saved in the `images/` folder at publication quality (PNG, dpi=300).

### CAGR Comparison

![CAGR Comparison](images/cagr_comparison.png)

Figure: Comparison of CAGR achieved by the sentiment-based strategy versus a buy-and-hold baseline for each evaluated company. The grouped bar chart shows both series side-by-side to make per-company comparisons straightforward.

### Strategy Improvement

![Strategy Improvement](images/strategy_improvement.png)

Figure: Improvement (strategy CAGR − buy & hold CAGR) for each company. Positive values indicate the sentiment-based strategy outperformed the buy-and-hold baseline; negative values indicate underperformance.

### Average CAGR

![Average CAGR](images/average_cagr.png)

Figure: Average CAGR across all evaluated companies for the sentiment-based strategy versus buy-and-hold. This summarizes portfolio-level performance differences.

### Company Ranking

![Company Ranking by Improvement](images/improvement_rank.png)

Figure: Companies ranked by their improvement over the buy-and-hold baseline (highest to lowest). This highlights which tickers gained the most from the strategy and which lagged behind.

---

Notes
- All figures are generated automatically by `generate_figures.py` and saved to the `images/` folder.
- The repository avoids changing any calculation or strategy logic; visualizations and documentation are presentation-only enhancements for portfolio quality.

Reproduce the figures locally:

```bash
python generate_figures.py
```

## Phase 1 application foundation

Phase 1 adds the initial modular-monolith structure without moving or modifying
the existing notebook, scripts, CSV datasets, results, or images.

### Architecture added in Phase 1

- FastAPI application with `GET /health` and an empty `/api/v1` router.
- Environment-backed backend configuration.
- SQLAlchemy 2.x declarative base and lazy database engine/session boundary.
- Alembic environment configured for future real schema migrations. No migration
  revision or application tables are created in this phase.
- Minimal Next.js, TypeScript, and Tailwind landing shell.
- PostgreSQL-only local Docker Compose service.
- Pytest health endpoint test.

The root `requirements.txt` remains for the existing research scripts. Backend
dependencies are declared separately in `backend/pyproject.toml`; overlapping
library names are intentional because the research scripts and backend have
separate dependency scopes.

### Backend setup and run

Requires Python 3.11 or newer. From the repository root in PowerShell:

```powershell
py -3 -m venv backend\.venv
backend\.venv\Scripts\Activate.ps1
Set-Location backend
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
uvicorn app.main:app --reload
```

The API runs at <http://127.0.0.1:8000>; health is available at
<http://127.0.0.1:8000/health>, and interactive API documentation is at
<http://127.0.0.1:8000/docs>.

### PostgreSQL setup

Docker Compose is the only infrastructure service in this phase. The backend
setup above creates `backend/.env` if it does not exist. Run the following
from the repository root:

```powershell
if (-not (Test-Path backend\.env)) { Copy-Item backend\.env.example backend\.env }
docker compose --env-file backend\.env up -d db
```

The backend reads that same `backend/.env`. `DATABASE_URL` is constructed by
`backend/app/core/config.py` using SQLAlchemy's `URL.create` from
`DATABASE_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, and
`POSTGRES_PASSWORD`. The example host is `localhost` because the API runs on
the host while PostgreSQL runs in Docker. Compose uses the POSTGRES variables
to initialize its container. These values are for local development only;
replace the example password locally and never commit credentials.

Stop PostgreSQL while retaining its local data volume:

```powershell
docker compose --env-file backend\.env down
```

Alembic is configured, but there is no `head` revision yet by design. From the
`backend` directory, inspect the currently empty migration history with:

```powershell
alembic heads
alembic history
```

Do not run `alembic upgrade head` in Phase 1. The first migration should
accompany the first real application schema in Phase 2.

### Backend tests

From the repository root:

```powershell
Set-Location backend
pytest
```

The health test does not require PostgreSQL.

### Frontend setup and run

Requires Node.js 20.9 or newer. From the repository root:

```powershell
Set-Location frontend
npm install
npm run dev
```

Open <http://localhost:3000>. The frontend is a FinSight-branded landing shell,
not the dashboard.

To validate TypeScript and production compilation:

```powershell
npm run typecheck
npm run build
```

### Model files

FinBERT weights are not included in Git and are not downloaded during Phase 1.
When FinBERT integration is implemented, Hugging Face Transformers will download
the configured model (default `ProsusAI/finbert`) to the local Hugging Face cache
on first use (internet access is required) and reuse that cache on later runs.
Budget approximately 0.5 GB for model files and around 1 GB for the cache,
excluding the Python/PyTorch installation. On Windows, the default cache is
typically `%USERPROFILE%\.cache\huggingface\hub`. Offline/bundled execution will
require a separate documented method to provide the model files.

Reaction-model artifacts, metadata, and evaluation metrics will only be created
after genuine offline training using real historical data. Phase 1 creates no
model weights, artifacts, predictions, or metrics and performs no model
training.

### Not implemented in Phase 1

- Database tables or a FinSight schema
- FinBERT loading or inference
- Entity/event extraction, novelty, surprise, market features, or predictions
- Reaction-model training or inference
- Authentication, watchlists, or saved user analyses
- Business APIs, dashboard, news feed, or charts in the frontend
- Backtesting changes or conversion of the existing research notebook
- Microservices, queues, Kubernetes, Terraform, or trading/broker integration
