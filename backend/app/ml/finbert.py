"""Financial headline sentiment using the pretrained ProsusAI FinBERT model."""

from functools import lru_cache

import torch
from transformers import pipeline

from app.core.config import get_settings


class ModelUnavailableError(RuntimeError):
    """Raised when FinBERT weights cannot be loaded or initialized."""


class InferenceError(RuntimeError):
    """Raised when an initialized model cannot classify the supplied text."""


@lru_cache(maxsize=1)
def _classifier():
    device = 0 if torch.cuda.is_available() else -1
    try:
        return pipeline(
            "text-classification",
            model=get_settings().finbert_model_id,
            device=device,
        )
    except Exception as exc:
        raise ModelUnavailableError("Configured FinBERT model could not be loaded.") from exc


def _format_scores(scores: list[dict]) -> dict:
    normalized = {item["label"].lower(): float(item["score"]) for item in scores}
    label = max(normalized, key=normalized.get)
    return {
        "label": label,
        "score": round(normalized[label], 4),
        "scores": {key: round(value, 4) for key, value in normalized.items()},
        "model": get_settings().finbert_model_id,
        "model_version": getattr(getattr(_classifier(), "model", None), "config", None)
        and getattr(_classifier().model.config, "_commit_hash", None),
    }


def classify_sentiments(texts: list[str]) -> list[dict]:
    """Classify multiple texts in one model call, preserving input order."""
    if not texts:
        return []
    classifier = _classifier()
    try:
        predictions = classifier(texts, truncation=True, top_k=None, batch_size=16)
    except Exception as exc:
        raise InferenceError("FinBERT inference failed for the submitted article text.") from exc
    # Pipeline output is a list of per-text class-score lists for top_k=None.
    if predictions and isinstance(predictions[0], dict):
        predictions = [predictions]
    return [_format_scores(scores) for scores in predictions]


def classify_sentiment(text: str) -> dict:
    """Classify a single text as positive, neutral, or negative."""
    return classify_sentiments([text])[0]
