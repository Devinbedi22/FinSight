import Link from "next/link";
import type { ReactNode } from "react";
import type { Decision, Sentiment } from "@/lib/demo-data";

export function Icon({ name, size = 18 }: { name: string; size?: number }) {
  const common = {
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.7,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true as const,
  };
  const paths: Record<string, ReactNode> = {
    grid: <><rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" /><rect x="3" y="14" width="7" height="7" rx="1" /><rect x="14" y="14" width="7" height="7" rx="1" /></>,
    news: <><path d="M4 5.5A1.5 1.5 0 0 1 5.5 4H20v15H5.5A1.5 1.5 0 0 1 4 17.5z" /><path d="M4 17.5V7m5 1h7m-7 4h7m-7 4h4" /></>,
    building: <><rect x="4" y="3" width="16" height="18" rx="1" /><path d="M8 7h2m4 0h2M8 11h2m4 0h2M8 15h2m4 0h2M10 21v-3h4v3" /></>,
    spark: <><path d="m12 3 1.7 5.3L19 10l-5.3 1.7L12 17l-1.7-5.3L5 10l5.3-1.7z" /><path d="m19 16 .8 2.2L22 19l-2.2.8L19 22l-.8-2.2L16 19l2.2-.8z" /></>,
    pulse: <><path d="M3 12h4l3-8 4 16 3-8h4" /></>,
    bookmark: <><path d="M6 4.5A1.5 1.5 0 0 1 7.5 3h9A1.5 1.5 0 0 1 18 4.5V21l-6-4-6 4z" /></>,
    settings: <><circle cx="12" cy="12" r="3" /><path d="m19.4 15 .1.1 1.2 1-.9 1.6-1.5-.4a7.8 7.8 0 0 1-1.5.9l-.3 1.6h-1.9l-.3-1.6a7.8 7.8 0 0 1-1.7 0l-.3 1.6h-1.9l-.3-1.6a7.8 7.8 0 0 1-1.5-.9l-1.5.4-.9-1.6 1.2-1a7.5 7.5 0 0 1-.3-1.8l-1.4-.7.5-1.8 1.6.1a7.5 7.5 0 0 1 1-1.4L7 7.9l1.4-1.3 1.3.9a7.5 7.5 0 0 1 1.7-.5l.5-1.5h1.9l.5 1.5a7.5 7.5 0 0 1 1.7.5l1.3-.9 1.4 1.3-.8 1.4a7.5 7.5 0 0 1 1 1.4l1.6-.1.5 1.8-1.4.7a7.5 7.5 0 0 1-.2 1.9z" /></>,
    search: <><circle cx="10.8" cy="10.8" r="6.3" /><path d="m16 16 4.5 4.5" /></>,
    bell: <><path d="M18 9a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9m-8 12h4" /></>,
    chevron: <path d="m9 18 6-6-6-6" />,
    plus: <><path d="M12 5v14M5 12h14" /></>,
    sliders: <><path d="M4 7h9m4 0h3M4 17h3m4 0h9" /><circle cx="15" cy="7" r="2" /><circle cx="9" cy="17" r="2" /></>,
    more: <><circle cx="5" cy="12" r="1" /><circle cx="12" cy="12" r="1" /><circle cx="19" cy="12" r="1" /></>,
    arrow: <><path d="M7 17 17 7M7 7h10v10" /></>,
    close: <><path d="m6 6 12 12M18 6 6 18" /></>,
    calendar: <><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M16 3v4M8 3v4M3 10h18" /></>,
    clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
    filter: <><path d="M4 5h16l-6 7v5l-4 2v-7z" /></>,
    menu: <><path d="M4 6h16M4 12h16M4 18h16" /></>,
    check: <path d="m5 12 4 4L19 6" />,
  };
  return <svg {...common}>{paths[name] ?? paths.spark}</svg>;
}

export function Panel({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return <section className={`rounded-xl border border-[#252d36] bg-[#10151b] ${className}`}>{children}</section>;
}

export function PanelHeading({
  title,
  detail,
  action,
}: {
  title: string;
  detail?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-[#252d36] px-5 py-4">
      <div>
        <h2 className="text-sm font-semibold text-[#e8edf2]">{title}</h2>
        {detail && <p className="mt-1 text-xs text-[#89939f]">{detail}</p>}
      </div>
      {action}
    </div>
  );
}

export function PageHeader({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="mb-7 flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
      <div>
        {eyebrow && <p className="mb-2 text-[11px] font-medium uppercase tracking-[0.15em] text-[#89939f]">{eyebrow}</p>}
        <h1 className="text-2xl font-semibold tracking-tight text-white sm:text-[28px]">{title}</h1>
        {description && <p className="mt-2 max-w-2xl text-sm leading-6 text-[#89939f]">{description}</p>}
      </div>
      {action}
    </div>
  );
}

export function StatusBadge({
  children,
  tone = "muted",
}: {
  children: ReactNode;
  tone?: "muted" | "green" | "red" | "amber" | "blue";
}) {
  const tones = {
    muted: "border-[#37414c] bg-[#1a2027] text-[#bac3cc]",
    green: "border-emerald-900/70 bg-emerald-950/50 text-emerald-300",
    red: "border-rose-900/70 bg-rose-950/50 text-rose-300",
    amber: "border-amber-900/70 bg-amber-950/40 text-amber-300",
    blue: "border-blue-900/70 bg-blue-950/40 text-blue-300",
  };
  return <span className={`inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-[10px] font-semibold uppercase tracking-wide ${tones[tone]}`}>{children}</span>;
}

export function SentimentBadge({ sentiment }: { sentiment: Sentiment }) {
  const tone = sentiment === "Positive" ? "green" : sentiment === "Negative" ? "red" : "muted";
  return <StatusBadge tone={tone}>{sentiment}</StatusBadge>;
}

export function DecisionBadge({ decision }: { decision: Decision }) {
  const tone = decision === "TRADE" ? "green" : decision === "WATCH" ? "amber" : "muted";
  return <StatusBadge tone={tone}>{decision}</StatusBadge>;
}

export function StatCard({
  label,
  value,
  note,
  icon,
}: {
  label: string;
  value: string;
  note: string;
  icon?: string;
}) {
  return (
    <div className="rounded-xl border border-[#252d36] bg-[#10151b] p-4">
      <div className="flex items-center justify-between">
        <p className="text-xs font-medium text-[#89939f]">{label}</p>
        {icon && <span className="text-[#6d7885]"><Icon name={icon} size={16} /></span>}
      </div>
      <p className="mt-4 text-[22px] font-semibold tracking-tight text-[#e8edf2]">{value}</p>
      <p className="mt-1.5 text-[11px] text-[#74808c]">{note}</p>
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex min-h-52 flex-col items-center justify-center px-6 py-10 text-center">
      <span className="mb-4 flex h-10 w-10 items-center justify-center rounded-lg border border-[#303a45] bg-[#171d24] text-[#9aa6b3]">
        <Icon name="pulse" size={19} />
      </span>
      <h3 className="text-sm font-semibold text-[#e2e7ec]">{title}</h3>
      <p className="mt-2 max-w-sm text-xs leading-5 text-[#89939f]">{description}</p>
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export function LoadingState({ label = "Loading analysis" }: { label?: string }) {
  return <div className="flex items-center gap-3 px-5 py-7 text-xs text-[#89939f]" role="status"><span className="h-4 w-4 animate-pulse rounded-full bg-[#364357]" />{label}</div>;
}

export function SearchInput({
  placeholder = "Search",
  className = "",
  value,
  onChange,
}: {
  placeholder?: string;
  className?: string;
  value?: string;
  onChange?: (value: string) => void;
}) {
  return (
    <label className={`flex min-w-0 items-center gap-2.5 rounded-lg border border-[#29323c] bg-[#0c1116] px-3 py-2.5 text-[#7e8995] focus-within:border-[#6079b5] ${className}`}>
      <Icon name="search" size={16} />
      <input value={value} onChange={(event) => onChange?.(event.target.value)} className="min-w-0 flex-1 bg-transparent text-xs text-[#e8edf2] placeholder:text-[#68737f] focus:outline-none" placeholder={placeholder} />
    </label>
  );
}

export function FilterBar({ children }: { children: ReactNode }) {
  return <div className="flex flex-wrap items-center gap-2.5">{children}</div>;
}

export function FilterSelect({
  label,
  options,
}: {
  label: string;
  options: string[];
}) {
  return (
    <label className="relative">
      <span className="sr-only">{label}</span>
      <select defaultValue={label} className="appearance-none rounded-lg border border-[#29323c] bg-[#10151b] py-2.5 pl-3 pr-8 text-xs text-[#b8c1ca]">
        <option value={label}>{label}</option>
        {options.map((option) => <option key={option}>{option}</option>)}
      </select>
      <span className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-[#75808c]"><Icon name="chevron" size={12} /></span>
    </label>
  );
}

export function Button({
  children,
  variant = "secondary",
  className = "",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost";
}) {
  const styles = {
    primary: "border border-[#a8bbff] bg-[#9cb2ff] text-[#101827] hover:bg-[#b1c2ff]",
    secondary: "border border-[#303a45] bg-[#171d24] text-[#d3dbe3] hover:bg-[#202832]",
    ghost: "border border-transparent bg-transparent text-[#9aa5b0] hover:bg-[#1a2027] hover:text-white",
  };
  return <button className={`inline-flex items-center justify-center gap-2 rounded-lg px-3.5 py-2.5 text-xs font-semibold transition-colors ${styles[variant]} ${className}`} {...props}>{children}</button>;
}

export function DataTable({
  headers,
  children,
}: {
  headers: string[];
  children: ReactNode;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[720px] border-collapse text-left">
        <thead><tr className="border-b border-[#252d36] bg-[#121820]">{headers.map((header) => <th key={header} className="px-5 py-3 text-[10px] font-semibold uppercase tracking-wider text-[#75808c]">{header}</th>)}</tr></thead>
        <tbody className="divide-y divide-[#202830]">{children}</tbody>
      </table>
    </div>
  );
}

export function CompanyLink({ ticker, children }: { ticker: string; children: ReactNode }) {
  return <Link href={`/companies/${ticker}`} className="font-medium text-[#e0e6ec] transition-colors hover:text-[#a9bcff]">{children}</Link>;
}

export function MutedText({ children }: { children: ReactNode }) {
  return <span className="text-xs text-[#89939f]">{children}</span>;
}
