/**
 * The admin page's data client and tile logic. Numbers come from the API's /admin routes
 * (latest evaluation run plus the live query log); nothing here invents a value. Without an API
 * URL the page shows placeholder fixtures, clearly marked as a layout preview.
 */

export type Scorecard = {
  run_id: string;
  run_date: string;
  configuration: string | null;
  questions: number;
  figures_cited_rate: number | null;
  recall_at_5: number | null;
  precision_at_5: number | null;
  unanswerable_declined: string | null; // "3 of 3"
  decline_accuracy: number | null;
  must_include_rate: number | null;
  verified_rate: number | null;
  audience_accuracy: number | null;
  median_seconds_quick: number | null;
  median_seconds_deep: number | null;
  judged: boolean;
};

export type Live = {
  questions: number;
  cost_per_answer_usd: number | null;
  projected_per_1000_usd: number | null;
  tokens_per_answer_median: number | null;
  spend_30d_usd: number | null;
  sandbox_cap_usd: number;
  spend_per_day: { day: string; cost_usd: number; tokens: number; questions: number }[];
  by_kind: { kind: string; questions: number; avg_cost_usd: number | null; share: number | null }[];
  tokens_by_step: { step: string; in: number; out: number }[];
  most_expensive: { id: string; question: string; kind: string; tokens: number | null; cost_usd: number | null }[];
  claims_removed_per_answer: number | null;
  declined_share: number | null;
  thumbs_down: number | null;
  median_seconds: { quick: number | null; deep: number | null };
};

export type Overview = { scorecard: Scorecard | null; live: Live; source: "user" | "eval" };

export type ReviewItem = {
  id: string;
  ts: string;
  source: string;
  session: string | null;
  question: string;
  mode: string;
  kind: string;
  seconds: number;
  status: "answered" | "declined" | "error";
  audience: string | null;
  claims_total: number | null;
  claims_verified: number | null;
  removed_claims: string[];
  paragraphs: string[];
  sources: { marker: number; title: string; page: number; url: string | null; passage: string }[];
  usage: { tokensIn: number; tokensOut: number; estimatedCostUsd: number } | null;
};

export type Traffic = "user" | "eval";
export type Window = "24h" | "7d" | "30d";
export type Status = "On target" | "Below target" | "No data yet";

/** A tile's status from its value and target; no value means no data, never zero. */
export function status(value: number | null | undefined, target: number, better: "higher" | "lower"): Status {
  if (value === null || value === undefined) return "No data yet";
  return (better === "higher" ? value >= target : value < target) ? "On target" : "Below target";
}

/** "3 of 3" declined: on target only when every unanswerable question was declined. */
export function allDeclined(text: string | null | undefined): Status {
  const match = text?.match(/^(\d+) of (\d+)$/);
  if (!match || match[2] === "0") return "No data yet";
  return match[1] === match[2] ? "On target" : "Below target";
}

export const percent = (value: number | null | undefined) => (value === null || value === undefined ? "–" : `${Math.round(value * 100)}%`);
export const usd = (value: number | null | undefined, digits = 4) => (value === null || value === undefined ? "–" : `$${value.toFixed(digits)}`);
export const seconds = (value: number | null | undefined) => (value === null || value === undefined ? "–" : `${value.toFixed(1)} s`);

const apiUrl = process.env.NEXT_PUBLIC_ASKWRI_API_URL;
const apiKey = process.env.NEXT_PUBLIC_ASKWRI_API_KEY ?? "";
export const adminMock = !apiUrl;

async function get<T>(path: string): Promise<T> {
  const response = await fetch(`${apiUrl!.replace(/\/$/, "")}${path}`, { headers: { "X-AskWRI-Key": apiKey } });
  if (!response.ok) throw new Error(`The admin API answered ${response.status}`);
  return (await response.json()) as T;
}

export async function fetchOverview(traffic: Traffic, window: Window): Promise<Overview> {
  if (adminMock) return (await import("../mock/adminFixtures.ts")).OVERVIEW;
  return get<Overview>(`/admin/overview?source=${traffic}&window=${window}`);
}

export async function fetchReview(id: string): Promise<ReviewItem> {
  if (adminMock) return (await import("../mock/adminFixtures.ts")).REVIEW;
  return get<ReviewItem>(`/admin/review?id=${encodeURIComponent(id)}`);
}

/** A link to the question's trace in CloudWatch (Transaction Search, filtered by session). */
export function traceUrl(session: string | null): string | null {
  const template = process.env.NEXT_PUBLIC_TRACE_URL_TEMPLATE;
  return template && session ? template.replace("{session}", encodeURIComponent(session)) : null;
}
