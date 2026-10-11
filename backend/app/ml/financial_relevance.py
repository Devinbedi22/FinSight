"""Pretrained financial-headline relevance scoring (distinct from sentiment)."""

from functools import lru_cache
import logging
import os
from concurrent.futures import ThreadPoolExecutor

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from app.core.config import get_settings

logger = logging.getLogger(__name__)
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
_model_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="financial-relevance")


@lru_cache(maxsize=1)
def _load_model():
    model_id = get_settings().financial_relevance_model_id
    tokenizer = AutoTokenizer.from_pretrained(model_id)
    model = AutoModelForSequenceClassification.from_pretrained(model_id)
    model.eval()
    return tokenizer, model


def score_financial_relevance(text: str) -> dict:
    """Return the model's 0–10 market relevance estimate and configured label."""
    if not get_settings().financial_relevance_enabled:
        return {"label": "unavailable", "score": None, "threshold": get_settings().financial_relevance_threshold,
                "model": get_settings().financial_relevance_model_id, "method": "model_disabled"}
    try:
        tokenizer, model = _model_executor.submit(_load_model).result()
    except Exception as exc:
        logger.exception("Could not load pretrained financial relevance model")
        return {"label": "unavailable", "score": None,
                "threshold": get_settings().financial_relevance_threshold,
                "model": get_settings().financial_relevance_model_id,
                "method": "model_load_error", "error": str(exc)[:400]}
    try:
        def infer() -> float:
            inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=256)
            with torch.inference_mode():
                return float(model(**inputs).logits.reshape(-1)[0].item())

        score = _model_executor.submit(infer).result()
    except Exception as exc:
        logger.exception("Pretrained financial relevance inference failed")
        return {"label": "unavailable", "score": None,
                "threshold": get_settings().financial_relevance_threshold,
                "model": get_settings().financial_relevance_model_id,
                "method": "model_inference_error", "error": str(exc)[:400]}
    scale = get_settings().financial_relevance_max_score
    if scale > 0 and scale != 1.0:
        score *= 10.0 / scale
    score = min(10.0, max(0.0, score))
    threshold = get_settings().financial_relevance_threshold
    return {
        "label": "useful" if score >= threshold else "not_useful",
        "score": score,
        "threshold": threshold,
        "model": get_settings().financial_relevance_model_id,
        "method": "pretrained_financial_relevance_regression",
    }


def financial_relevance_status() -> dict:
    """Report whether the model is loaded without forcing its heavyweight download."""
    settings = get_settings()
    loaded = _load_model.cache_info().currsize > 0
    return {
        "enabled": settings.financial_relevance_enabled,
        "model": settings.financial_relevance_model_id,
        "loaded": loaded,
        "threshold": settings.financial_relevance_threshold,
        "score_range": [0, 10],
    }
