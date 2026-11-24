# FinSight — Financial Intelligence & Stock Market Research

FinSight is an AI-assisted financial research platform that integrates stock market data, financial news, sentiment analysis, company fundamentals, technical indicators, and experimental machine learning forecasts into a unified research workspace.

## Key Features

- **Market Overview:** Explore market performance and available company quotes.
- **Company Research:** Analyze historical stock prices, financial statements, and technical indicators.
- **Financial News:** Retrieve and organize financial news with company-level relevance and sentiment analysis.
- **Stock Comparison:** Compare historical performance and financial fundamentals of up to four companies.
- **Watchlist:** Maintain a personalized, browser-local list of companies.
- **Event Intelligence:** Explore heuristic financial event signals extracted from stored news headlines.
- **Research Assistant:** Ask financial research questions and receive evidence-grounded findings with source citations.
- **LLM Integration:** Optional conversational interpretation through an OpenAI-compatible provider.
- **Stock Predictions:** Explore experimental FinancialBERT-based forecasts.
- **Backtesting:** Evaluate forecasting methodologies using historical market data.

## Technology Stack

| Component | Technology |
|---|---|
| Frontend | Next.js, React, TypeScript, Tailwind CSS |
| Backend | Python, FastAPI |
| Database | SQLite, PostgreSQL |
| ORM | SQLAlchemy |
| Database Migrations | Alembic |
| Market Data | Yahoo Finance |
| Financial Fundamentals | SEC EDGAR |
| News Source | Google News RSS |
| NLP Models | FinBERT, Stocky, FinancialBERT |
| Machine Learning | PyTorch, Transformers, Scikit-learn |
| Version Control | Git, GitHub, Git LFS |

## System Architecture

FinSight follows a modular architecture comprising:

1. A Next.js frontend for interactive financial research and visualization.
2. A FastAPI backend for API requests and financial data processing.
3. External providers for market prices, financial statements, and news.
4. Machine learning models for sentiment, company relevance, and experimental forecasting.
5. A persistence layer for storing news and related research data.

## User Interface

FinSight uses a custom Smoky Amethyst design system featuring muted purple surfaces, refined typography, consistent visual components, responsive layouts, and financial data visualizations.

## Local Development

### Prerequisites

- Python 3.11 or later
- Node.js 20.9 or later
- Git and Git LFS
- Internet connectivity for external data providers
- Required machine learning model artifacts

### Clone the repository

```bash
git clone https://github.com/Devinbedi22/FinSight.git
cd FinSight
```

### Backend setup

From the repository root:

```bash
python -m pip install -e "backend[dev]"
cd backend
```

Configure the required environment variables using `.env.example` as a reference.

For a local SQLite setup:

```bash
export DATABASE_URL=sqlite:///./finsight.db
export NEWS_INGEST_ENABLED=false
alembic upgrade head
python -m uvicorn app.main:app --reload
```

On Windows PowerShell, use `$env:DATABASE_URL` and `$env:NEWS_INGEST_ENABLED` instead of the Bash export commands.

### Frontend setup

Open a separate terminal from the repository root:

```bash
cd frontend
npm ci
npm run dev
```

Configure the frontend API base URL as:

```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1
```

### Access the application

- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API documentation: http://localhost:8000/docs

## Configuration

SEC fundamentals require a valid `SEC_USER_AGENT` containing an application identifier and monitored contact email.

The optional LLM integration requires a compatible provider configuration. See [LLM Configuration](docs/research-llm.md) for details.

Keep credentials and environment files outside version control.

Some machine learning features require separately available model checkpoints. Refer to the existing model setup documentation before running inference.

## Testing

Backend:

```bash
cd backend
python -m pytest
```

Frontend:

```bash
cd frontend
npx tsc --noEmit
npm run build
```

## Current Limitations

- Market prices are delayed daily observations rather than real-time exchange data.
- External financial data requires successful network access.
- The emergency company-directory fallback provides limited historical coverage.
- Event classifications are heuristic and are not human-verified.
- Experimental forecasts have not demonstrated reliable predictive superiority over baseline models.
- LLM functionality requires a configured provider and remains optional.
- Watchlists are stored locally in the browser.

## Disclaimer

FinSight is an educational and research-oriented project. Its forecasts, sentiment classifications, and financial interpretations are not investment recommendations.

## License

This project is licensed under the MIT License.
