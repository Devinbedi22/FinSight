"""Inference adapter for techandy42/FinancialBERT Model v2.

The upstream checkpoint is a one-output regression head over the frozen
ProsusAI FinBERT [CLS] embedding. Company forecasts expose the regression
output as a next-month expected return; the legacy article helper can still
bucket it into a direction class for compatibility.
"""

from functools import lru_cache
from pathlib import Path

import torch
from torch import nn
from transformers import AutoModel, AutoTokenizer

from app.core.config import get_settings


@lru_cache(maxsize=1)
def _load_model():
    settings = get_settings()
    checkpoint = Path(settings.financialbert_weights_path)
    if not checkpoint.is_absolute():
        checkpoint = Path(__file__).resolve().parents[2] / checkpoint
    if not checkpoint.is_file():
        return None
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    tokenizer = AutoTokenizer.from_pretrained(settings.finbert_model_id)
    encoder = AutoModel.from_pretrained(settings.finbert_model_id)
    regressor = nn.Linear(encoder.config.hidden_size, 1)
    regressor.load_state_dict(torch.load(checkpoint, map_location="cpu", weights_only=True))
    encoder.to(device).eval()
    regressor.to(device).eval()
    return tokenizer, encoder, regressor, device, checkpoint


def predict_expected_return(context_text: str) -> dict:
    """Return Model v2's next-month regression output (not a sentiment label)."""
    loaded = _load_model()
    if loaded is None:
        return {
            "status": "financialbert_checkpoint_missing",
            "expected_return": None,
            "model": "FinancialBERT Model v2",
        }
    tokenizer, encoder, regressor, device, checkpoint = loaded
    inputs = tokenizer(context_text, return_tensors="pt", truncation=True, max_length=512).to(device)
    with torch.inference_mode():
        embedding = encoder(**inputs).last_hidden_state[:, 0, :]
        expected_return_internal = float(regressor(embedding).item())
    return {
        "status": "financialbert_model_v2",
        "expected_return": expected_return_internal,
        "model": "techandy42/FinancialBERT Model v2",
        "model_artifact": checkpoint.name,
    }


def classify_impact(context_text: str) -> dict:
    """Legacy per-headline label API; graph predictions use the raw regression output."""
    result = predict_expected_return(context_text)
    if result["expected_return"] is None:
        return {**result, "impact": None}
    expected_return_internal = result["expected_return"]
    band = get_settings().impact_neutral_band
    impact = "positive" if expected_return_internal > band else "negative" if expected_return_internal < -band else "neutral"
    return {
        **result,
        "status": "financialbert_model_v2",
        "impact": impact,
        "neutral_band": band,
    }
