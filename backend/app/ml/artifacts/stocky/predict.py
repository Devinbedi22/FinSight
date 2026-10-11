
import torch
import torch.nn as nn
import torch.nn.functional as F
from transformers import BertModel, BertTokenizerFast

class StockyPredictor:
    def __init__(self, model_path=".", device=None):
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.tokenizer = BertTokenizerFast.from_pretrained(f"{model_path}/tokenizer")

        self.title_encoder = BertModel.from_pretrained(
            f"{model_path}/contrastive/title_encoder"
        ).to(self.device).eval()

        self.stock_encoder = BertModel.from_pretrained(
            f"{model_path}/contrastive/stock_encoder"
        ).to(self.device).eval()

        self.reranker = BertModel.from_pretrained(
            f"{model_path}/reranker"
        ).to(self.device).eval()

        self.head = nn.Linear(768, 1)
        self.head.load_state_dict(
            torch.load(f"{model_path}/reranker/classifier.pt", map_location=self.device)
        )
        self.head.to(self.device).eval()

    @torch.no_grad()
    def predict(self, title, stocks, top_k=5):
        t = self.tokenizer([title], return_tensors="pt", truncation=True).to(self.device)
        t_emb = F.normalize(self.title_encoder(**t).last_hidden_state[:, 0], dim=1)

        s = self.tokenizer(stocks, padding=True, truncation=True, return_tensors="pt").to(self.device)
        s_emb = F.normalize(self.stock_encoder(**s).last_hidden_state[:, 0], dim=1)

        sims = torch.matmul(t_emb, s_emb.T)[0]
        idx = torch.topk(sims, k=min(top_k, len(stocks))).indices.cpu()

        pairs = self.tokenizer(
            [title] * len(idx),
            [stocks[i] for i in idx],
            padding=True,
            truncation=True,
            return_tensors="pt"
        ).to(self.device)

        scores = torch.sigmoid(
            self.head(self.reranker(**pairs).last_hidden_state[:, 0])
        ).squeeze(-1)

        return [(stocks[i], scores[j].item()) for j, i in enumerate(idx)]
