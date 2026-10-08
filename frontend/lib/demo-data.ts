export type Sentiment = "Positive" | "Negative" | "Neutral";
export type Decision = "TRADE" | "WATCH" | "ABSTAIN";

export type DemoNewsItem = {
  id: string;
  ticker: string;
  company: string;
  headline: string;
  time: string;
  sentiment: Sentiment;
  eventType: string;
  severity: "High" | "Medium" | "Low";
  novelty: string;
  reaction: string;
};

export const demoNews: DemoNewsItem[] = [
  {
    id: "evt-001",
    ticker: "NVDA",
    company: "NVIDIA Corporation",
    headline: "NVIDIA expands next-generation data center platform availability",
    time: "Today · 09:42 ET",
    sentiment: "Positive",
    eventType: "Product & business",
    severity: "Medium",
    novelty: "Elevated",
    reaction: "Not analyzed",
  },
  {
    id: "evt-002",
    ticker: "MSFT",
    company: "Microsoft Corporation",
    headline: "Microsoft announces expanded cloud infrastructure investment",
    time: "Today · 08:16 ET",
    sentiment: "Neutral",
    eventType: "Capital expenditure",
    severity: "Medium",
    novelty: "Moderate",
    reaction: "Not analyzed",
  },
  {
    id: "evt-003",
    ticker: "TSLA",
    company: "Tesla, Inc.",
    headline: "Automaker updates delivery outlook ahead of quarterly results",
    time: "Yesterday · 16:30 ET",
    sentiment: "Negative",
    eventType: "Guidance",
    severity: "High",
    novelty: "Elevated",
    reaction: "Not analyzed",
  },
];

export const demoCompanies = [
  { ticker: "AAPL", name: "Apple Inc.", sector: "Technology", sentiment: "Neutral" as Sentiment, events: 4, regime: "Unavailable" },
  { ticker: "AMZN", name: "Amazon.com, Inc.", sector: "Consumer & cloud", sentiment: "Positive" as Sentiment, events: 3, regime: "Unavailable" },
  { ticker: "MSFT", name: "Microsoft Corporation", sector: "Technology", sentiment: "Neutral" as Sentiment, events: 6, regime: "Unavailable" },
  { ticker: "NVDA", name: "NVIDIA Corporation", sector: "Semiconductors", sentiment: "Positive" as Sentiment, events: 8, regime: "Unavailable" },
  { ticker: "TSLA", name: "Tesla, Inc.", sector: "Automotive", sentiment: "Negative" as Sentiment, events: 5, regime: "Unavailable" },
];

export const demoTrend = [
  { day: "Mon", positive: 4, neutral: 5, negative: 2 },
  { day: "Tue", positive: 6, neutral: 4, negative: 3 },
  { day: "Wed", positive: 5, neutral: 7, negative: 2 },
  { day: "Thu", positive: 8, neutral: 5, negative: 4 },
  { day: "Fri", positive: 6, neutral: 6, negative: 3 },
  { day: "Sat", positive: 7, neutral: 4, negative: 2 },
  { day: "Sun", positive: 9, neutral: 5, negative: 3 },
];

export const demoMarketLine = [
  { time: "09:30", value: 38 },
  { time: "10:00", value: 44 },
  { time: "10:30", value: 41 },
  { time: "11:00", value: 53 },
  { time: "11:30", value: 49 },
  { time: "12:00", value: 58 },
  { time: "12:30", value: 55 },
  { time: "13:00", value: 68 },
  { time: "13:30", value: 62 },
  { time: "14:00", value: 74 },
  { time: "14:30", value: 71 },
  { time: "15:00", value: 82 },
];

export const demoEquity = [
  { date: "Jan 06", strategy: 12, baseline: 10 },
  { date: "Jan 13", strategy: 17, baseline: 15 },
  { date: "Jan 20", strategy: 14, baseline: 19 },
  { date: "Jan 27", strategy: 25, baseline: 21 },
  { date: "Feb 03", strategy: 30, baseline: 26 },
  { date: "Feb 10", strategy: 28, baseline: 24 },
  { date: "Feb 17", strategy: 40, baseline: 34 },
  { date: "Feb 24", strategy: 45, baseline: 38 },
];

export const demoDrawdown = [
  { date: "Jan 06", drawdown: 0 },
  { date: "Jan 13", drawdown: -5 },
  { date: "Jan 20", drawdown: -12 },
  { date: "Jan 27", drawdown: -3 },
  { date: "Feb 03", drawdown: -1 },
  { date: "Feb 10", drawdown: -8 },
  { date: "Feb 17", drawdown: -2 },
  { date: "Feb 24", drawdown: 0 },
];

export const demoRegimes = [
  { name: "Trending", count: 0 },
  { name: "Range-bound", count: 0 },
  { name: "High volatility", count: 0 },
];
