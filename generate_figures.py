#!/usr/bin/env python3
"""Generate publication-quality figures from returns.csv using matplotlib only.

Saves PNGs into an `images/` folder (created if missing) with dpi=300.
"""
import os
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np


def set_plot_style():
    # Publication-quality matplotlib settings
    plt.rcParams.update({
        "figure.dpi": 300,
        "font.family": "sans-serif",
        "font.sans-serif": ["DejaVu Sans", "Arial", "Liberation Sans", "Helvetica"],
        "font.size": 12,
        "axes.titlesize": 16,
        "axes.labelsize": 13,
        "xtick.labelsize": 11,
        "ytick.labelsize": 11,
        "legend.fontsize": 11,
        "axes.grid": False,
        "axes.edgecolor": "#333333",
    })


def ensure_images_dir(base_path: Path) -> Path:
    images_dir = base_path / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    return images_dir


def load_returns(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    # normalize column names
    df = df.rename(columns={
        "CAGR using strategy": "strategy",
        "CAGR without strategy": "buy_hold",
        "Company": "company",
        "Number of years": "years",
    })
    # ensure numeric
    df["strategy"] = pd.to_numeric(df["strategy"], errors="coerce")
    df["buy_hold"] = pd.to_numeric(df["buy_hold"], errors="coerce")
    df = df.dropna(subset=["company"])
    return df


def save_fig(fig, path: Path, dpi=300):
    fig.savefig(str(path), dpi=dpi, bbox_inches="tight")
    plt.close(fig)


def grouped_cagr_chart(df: pd.DataFrame, outpath: Path):
    set_plot_style()
    companies = df["company"].astype(str)
    x = np.arange(len(companies))
    width = 0.36

    fig, ax = plt.subplots(figsize=(14, 7))
    bars1 = ax.bar(x - width / 2, df["strategy"], width, label="CAGR (strategy)", color="#2a9d8f", edgecolor="#16694a")
    bars2 = ax.bar(x + width / 2, df["buy_hold"], width, label="CAGR (buy & hold)", color="#264653", edgecolor="#0f2730")

    ax.set_xticks(x)
    ax.set_xticklabels(companies, rotation=45, ha="right")
    ax.set_ylabel("CAGR (%)")
    ax.set_title("CAGR: Strategy vs Buy & Hold by Company")
    ax.grid(axis="y", linestyle="--", alpha=0.12)
    ax.legend(frameon=False, loc="upper left")

    # annotate bars with percent and white bbox for readability
    for bar in list(bars1) + list(bars2):
        h = bar.get_height()
        ax.annotate(f"{h:.2f}%", xy=(bar.get_x() + bar.get_width() / 2, h),
                    xytext=(0, 6), textcoords="offset points", ha="center", va="bottom",
                    fontsize=10, color="#111111", bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.7))

    plt.tight_layout()
    save_fig(fig, outpath)


def improvement_horizontal_bar(df: pd.DataFrame, outpath: Path):
    set_plot_style()
    df2 = df.copy()
    df2["improvement"] = df2["strategy"] - df2["buy_hold"]
    df2 = df2.sort_values("improvement")

    colors = ["#2a9d8f" if v >= 0 else "#e76f51" for v in df2["improvement"]]

    fig, ax = plt.subplots(figsize=(12, 8))
    y = np.arange(len(df2))
    bars = ax.barh(y, df2["improvement"], color=colors, edgecolor="#222222", height=0.7)
    ax.set_yticks(y)
    ax.set_yticklabels(df2["company"])
    ax.set_xlabel("Improvement in CAGR (percentage points)")
    ax.set_title("Strategy Improvement over Buy & Hold by Company")
    ax.grid(axis="x", linestyle="--", alpha=0.12)

    for bar in bars:
        val = bar.get_width()
        ax.annotate(f"{val:.2f}%", xy=(val, bar.get_y() + bar.get_height() / 2),
                    xytext=(6 if val >= 0 else -6, 0), textcoords="offset points",
                    ha=("left" if val >= 0 else "right"), va="center", fontsize=10,
                    bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.75))

    plt.tight_layout()
    save_fig(fig, outpath)


def average_cagr_chart(df: pd.DataFrame, outpath: Path):
    set_plot_style()
    avg_strategy = df["strategy"].mean()
    avg_buy_hold = df["buy_hold"].mean()

    fig, ax = plt.subplots(figsize=(7, 6))
    bars = ax.bar([0, 1], [avg_strategy, avg_buy_hold], color=["#2a9d8f", "#264653"], width=0.6, edgecolor="#222222")
    ax.set_xticks([0, 1])
    ax.set_xticklabels(["Avg CAGR (strategy)", "Avg CAGR (buy & hold)"])
    ax.set_ylabel("CAGR (%)")
    ax.set_title("Average CAGR: Strategy vs Buy & Hold")
    ax.grid(axis="y", linestyle="--", alpha=0.12)

    for bar in bars:
        h = bar.get_height()
        ax.annotate(f"{h:.2f}%", xy=(bar.get_x() + bar.get_width() / 2, h), xytext=(0, 8),
                    textcoords="offset points", ha="center", va="bottom", fontsize=11,
                    bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.8))

    plt.tight_layout()
    save_fig(fig, outpath)


def additional_visuals(df: pd.DataFrame, images_dir: Path):
    # Histogram of improvements
    imp = df["strategy"] - df["buy_hold"]
    set_plot_style()
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.hist(imp, bins=10, color="#2a9d8f", edgecolor="#1b4332", alpha=0.95)
    ax.set_xlabel("Improvement in CAGR (percentage points)")
    ax.set_ylabel("Number of companies")
    ax.set_title("Distribution of Strategy Improvement")
    ax.grid(axis="y", linestyle="--", alpha=0.12)
    save_fig(fig, images_dir / "improvement_histogram.png")

    # Ranked improvement bar chart (descending)
    df_rank = df.copy()
    df_rank["improvement"] = df_rank["strategy"] - df_rank["buy_hold"]
    df_rank = df_rank.sort_values("improvement", ascending=False)
    colors = ["#2a9d8f" if v >= 0 else "#e76f51" for v in df_rank["improvement"]]
    fig, ax = plt.subplots(figsize=(11, 6))
    bars = ax.bar(df_rank["company"], df_rank["improvement"], color=colors, edgecolor="#222222")
    ax.set_ylabel("Improvement in CAGR (percentage points)")
    ax.set_title("Ranked Strategy Improvement (highest to lowest)")
    ax.grid(axis="y", linestyle="--", alpha=0.12)
    plt.xticks(rotation=45, ha="right")
    for bar in bars:
        val = bar.get_height()
        ax.annotate(f"{val:.2f}%", xy=(bar.get_x() + bar.get_width() / 2, val), xytext=(0, 6),
                    textcoords="offset points", ha="center", va="bottom", fontsize=9,
                    bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.8))
    plt.tight_layout()
    save_fig(fig, images_dir / "improvement_rank.png")


def write_pipeline_md(images_dir: Path):
    content = """
```mermaid
flowchart LR
  A[Raw Analyst Ratings + Financial News] --> B[Data Preprocessing]
  B --> C[Feature Engineering]
  C --> D[Sentiment Analysis]
  D --> E[Trading Strategy]
  E --> F[Backtesting]
  F --> G[returns.csv]
```
"""
    (images_dir / "pipeline.md").write_text(content)


def main():
    base = Path(__file__).resolve().parent
    images_dir = ensure_images_dir(base)
    csv_path = base / "returns.csv"
    if not csv_path.exists():
        print(f"Error: {csv_path} not found. Run from the project root where returns.csv lives.")
        return

    df = load_returns(csv_path)

    grouped_cagr_chart(df, images_dir / "cagr_comparison.png")
    improvement_horizontal_bar(df, images_dir / "strategy_improvement.png")
    average_cagr_chart(df, images_dir / "average_cagr.png")
    additional_visuals(df, images_dir)
    write_pipeline_md(images_dir)

    print(f"Saved figures to {images_dir}")


if __name__ == "__main__":
    main()
