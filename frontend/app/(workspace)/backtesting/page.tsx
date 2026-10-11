import { EmptyState, PageHeader, Panel, PanelHeading, StatusBadge } from "@/components/ui";

const methodology = [
  {
    title: "News signal",
    detail: "A legacy notebook applies pretrained FinBERT labels to dated headlines and aggregates them by trading date.",
  },
  {
    title: "Trading rule",
    detail: "The notebook compares a bearish-news / moving-average exit rule with buy-and-hold. It is separate from the running API.",
  },
  {
    title: "Evaluation caveat",
    detail: "Its moving averages are shifted by one row into the future, creating look-ahead bias. The reported CAGR figures are not validated strategy performance.",
  },
  {
    title: "Reproducibility",
    detail: "The notebook expects data/news.csv and data/companies.csv, which are not present in this repository. Transaction costs and a walk-forward evaluation are not established.",
  },
];

export default function BacktestingPage() {
  return (
    <>
      <PageHeader
        eyebrow="Research status"
        title="Backtesting"
        description="A transparent view of the current research artifacts and what is required before reporting strategy performance."
        action={<StatusBadge tone="amber">Time series unavailable</StatusBadge>}
      />

      <Panel className="mb-5">
        <PanelHeading
          title="Equity curve and drawdown"
          detail="No validated, date-stamped backtest series is available to plot."
        />
        <div className="p-4 sm:p-6">
          <EmptyState
            title="No verified backtest results"
            description="The repository contains aggregate CAGR values in a legacy CSV, but no valid equity or drawdown time series. No returns, trades, Sharpe ratio, or win rate are shown here."
          />
          <p className="mx-auto max-w-2xl border-t border-[#252d36] pt-4 text-center text-[10px] leading-5 text-[#89939f]">
            The aggregate CSV is an offline research artifact, not a live API result. A look-ahead issue in the notebook must be corrected and the experiment rerun with reproducible inputs before performance charts are appropriate.
          </p>
        </div>
      </Panel>

      <Panel>
        <PanelHeading
          title="Legacy methodology and limitations"
          detail="Based on main.ipynb, returns.csv, and the checked-in research scripts"
        />
        <div className="grid gap-px bg-[#252d36] sm:grid-cols-2">
          {methodology.map((item, index) => (
            <article key={item.title} className="bg-[#10151b] p-5">
              <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[#91aaff]">
                0{index + 1} · {item.title}
              </p>
              <p className="mt-2 text-xs leading-5 text-[#aab4bf]">{item.detail}</p>
            </article>
          ))}
        </div>
      </Panel>
    </>
  );
}
