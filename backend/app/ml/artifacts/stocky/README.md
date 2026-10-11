
language:
- en
- tr
tags:
- finance
- stocks
- news-analysis
- stock-prediction
- information-retrieval
license: apache-2.0
datasets:
- financial-news
metrics:
- recall
pipeline_tag: zero-shot-classification
---

# 📈 Stocky Stock Predictor

**Predict stock symbols from news headlines using a two-stage deep learning pipeline.**

## 🎯 Model Overview

This model predicts which stock symbols are mentioned or relevant to a given news headline. It uses a sophisticated two-stage retrieval system:

1. **Stage 1 - Contrastive Retrieval**: Fast dual-encoder retrieves top-50 candidates
2. **Stage 2 - Cross-Encoder Reranking**: Precise scoring to get final top-10 predictions

## 📊 Performance

**Test Set Metrics (10,620 samples):**
- Recall@5: **51.17%**
- Recall@10: **54.40%**
- Recall@20: **58.76%**

**Real-World Performance:**
- Direct company mentions (e.g., "Nvidia announces..."): **~80% accuracy**
- Generic sector news (e.g., "Tech stocks rally"): **~50% accuracy**

## 🚀 Quick Start

```python
from predict import StockyPredictor

# Initialize predictor
predictor = StockyPredictor()

# Your list of stock symbols (load all 6,973 stocks in production)
stocks = ["NVDA", "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "META", ...]

# Predict
title = "Nvidia announces new AI chip breakthrough"
predictions = predictor.predict(title, stocks, top_k=10)

# Results: [('NVDA', 0.95), ('AMD', 0.78), ...]
for stock, score in predictions:
    print(f"{stock}: {score:.4f}")
```

## 💡 Use Cases

- **News Analysis**: Automatically tag news articles with relevant stocks
- **Trading Signals**: Identify stocks mentioned in breaking news
- **Portfolio Monitoring**: Track news about your holdings
- **Market Research**: Analyze media coverage of stocks

## 🏗️ Model Architecture

### Components:

1. **Tokenizer** (35K vocab)
   - Custom WordPiece trained on financial text
   - Top 500 stocks as special tokens
   - 98.4% coverage of frequent stocks

2. **MLM Pretrained Encoder** (113M params)
   - BERT-base architecture
   - Pretrained from scratch on FinCorpus + news
   - Perplexity: 5.08

3. **Contrastive Model** (226M params)
   - Dual-encoder (title encoder + stock encoder)
   - Trained with InfoNCE loss
   - Retrieves top-50 candidates in milliseconds

4. **Cross-Encoder Reranker** (113M params)
   - BERT + classification head
   - Binary relevance scoring
   - Validation loss: 0.1619

### Training Details:

- **Dataset**: 106,207 news articles, 6,973 unique stocks
- **Training time**: ~4-5 days on V100 GPU
- **Stages**: MLM (3 epochs) → Contrastive (5 epochs) → Reranking (3 epochs)

## 📝 Examples

### Example 1: Tech Company
```python
title = "Apple unveils new iPhone with advanced camera"
predictions = predictor.predict(title, all_stocks)
# Top result: AAPL (0.94)
```

### Example 2: Cryptocurrency
```python
title = "Bitcoin price surges past $50,000"
predictions = predictor.predict(title, all_stocks)
# Top result: BTC-USD (0.92)
```

### Example 3: Multiple Companies
```python
title = "Tech giants report strong earnings amid AI boom"
predictions = predictor.predict(title, all_stocks)
# Top results: NVDA (0.89), MSFT (0.85), GOOGL (0.78)
```

## ⚠️ Limitations

- Works best when company names are mentioned directly
- Generic market news (e.g., "tech sector rallies") may have lower accuracy
- ETF symbols (SPY, QQQ) have limited training data
- Primarily trained on English news (some Turkish support)

## 🔧 Advanced Usage

### Custom Stock List
```python
# Load your own stock universe
import pandas as pd
stocks_df = pd.read_csv("my_stocks.csv")
stocks = stocks_df["symbol"].tolist()

predictions = predictor.predict(title, stocks, top_k=20)
```

### Batch Prediction
```python
news_headlines = [
    "Nvidia announces new GPU",
    "Tesla deliveries beat estimates",
    "Amazon expands AWS services"
]

all_predictions = []
for headline in news_headlines:
    preds = predictor.predict(headline, all_stocks)
    all_predictions.append({
        "headline": headline,
        "predictions": preds
    })
```

### Custom Candidate Size
```python
# Retrieve more candidates for better recall
predictions = predictor.predict(
    title,
    all_stocks,
    top_k=10,
    candidates_k=100  # Default: 50
)
```

## 📚 Model Card

| Component | Size | Description |
|-----------|------|-------------|
| Tokenizer | 35K vocab | Financial domain tokenizer |
| Title Encoder | 113M | Encodes news headlines |
| Stock Encoder | 113M | Encodes stock symbols |
| Reranker | 113M | Scores title-stock pairs |
| **Total** | **~340M params** | Complete pipeline |

## 🎓 Citation

```bibtex
@misc{stocky2025,
  title={Stocky: Stock Prediction from News Headlines},
  author={Stocky AI Team},
  year={2025},
  publisher={Hugging Face},
  howpublished={\\url{https://huggingface.co/stocky-ai/stocky-stock-predictor}}
}
```

## 📄 License

Apache 2.0

## 🤝 Contact

- Organization: [stocky-ai](https://huggingface.co/stocky-ai)
- Issues: Report bugs or request features on GitHub

---

**Built with ❤️ using PyTorch and Transformers**
