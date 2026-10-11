"""Stocky headline-to-ticker retrieval for the current S&P 500 universe."""

from importlib.util import module_from_spec, spec_from_file_location
from functools import lru_cache
from pathlib import Path

import torch
import torch.nn.functional as F
from huggingface_hub import snapshot_download

from app.core.config import get_settings

ARTIFACT_ROOT = Path(__file__).parent / "artifacts" / "stocky"


@lru_cache(maxsize=1)
def get_predictor():
    """Load the upstream StockyPredictor implementation and checkpoint once."""
    if not (ARTIFACT_ROOT / "predict.py").exists():
        snapshot_download(
            repo_id=get_settings().stocky_model_id,
            local_dir=str(ARTIFACT_ROOT),
        )
    spec = spec_from_file_location("stocky_upstream_predict", ARTIFACT_ROOT / "predict.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load Stocky predictor implementation")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    return module.StockyPredictor(model_path=str(ARTIFACT_ROOT), device=device)


@lru_cache(maxsize=1)
@torch.inference_mode()
def _stock_embeddings(symbols: tuple[str, ...]):
    predictor = get_predictor()
    stock_batch = predictor.tokenizer(
        list(symbols), padding=True, truncation=True, return_tensors="pt"
    ).to(predictor.device)
    embeddings = F.normalize(
        predictor.stock_encoder(**stock_batch).last_hidden_state[:, 0], dim=1
    )
    return embeddings


@torch.inference_mode()
def retrieve_tickers(
    headline: str, symbols: list[str], top_k: int = 10, candidates_k: int | None = None
) -> list[dict]:
    if not symbols:
        return []
    predictor = get_predictor()
    title_batch = predictor.tokenizer(
        [headline], return_tensors="pt", truncation=True
    ).to(predictor.device)
    title_embedding = F.normalize(
        predictor.title_encoder(**title_batch).last_hidden_state[:, 0], dim=1
    )
    all_symbols = tuple(symbols)
    similarities = torch.matmul(title_embedding, _stock_embeddings(all_symbols).T)[0]
    # Match the released predictor: top_k is both the contrastive shortlist
    # size and returned count. The upstream implementation preserves retrieval
    # order while attaching each candidate's reranker score.
    candidate_count = min(top_k if candidates_k is None else candidates_k, len(all_symbols))
    indices = torch.topk(similarities, k=candidate_count).indices
    candidates = [all_symbols[index] for index in indices.tolist()]
    pair_batch = predictor.tokenizer(
        [headline] * len(candidates), candidates,
        padding=True, truncation=True, return_tensors="pt"
    ).to(predictor.device)
    scores = torch.sigmoid(
        predictor.head(
            predictor.reranker(**pair_batch).last_hidden_state[:, 0]
        )
    ).squeeze(-1)
    ranked = list(zip(candidates, scores.tolist()))[:top_k]
    return [
        {"ticker": ticker, "relevance_score": round(float(score), 4)}
        for ticker, score in ranked
    ]
