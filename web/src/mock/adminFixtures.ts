/** Placeholder data for the admin page's layout preview (no API URL). Not results. */

import type { Overview, ReviewItem } from "../lib/admin.ts";

export const OVERVIEW: Overview = {
  source: "user",
  scorecard: {
    run_id: "preview", run_date: "2026-11-05T00:00:00Z", configuration: "C: agent loop + verify", questions: 30,
    figures_cited_rate: 1, recall_at_5: 0.9, precision_at_5: 0.7, unanswerable_declined: "3 of 3", decline_accuracy: 1,
    must_include_rate: 0.7, verified_rate: 0.9, audience_accuracy: 0.9, median_seconds_quick: 15, median_seconds_deep: 30, judged: true,
    judges: { Faithfulness: 0.82, Correctness: 0.88, ResponseRelevance: 0.97, Helpfulness: 0.72 },
  },
  live: {
    questions: 12, cost_per_answer_usd: 0.03, projected_per_1000_usd: 30, tokens_per_answer_median: 20000, spend_30d_usd: 4.2, sandbox_cap_usd: 500,
    spend_per_day: [
      { day: "2026-11-03", cost_usd: 0.4, tokens: 260000, questions: 13 },
      { day: "2026-11-04", cost_usd: 1.1, tokens: 700000, questions: 35 },
      { day: "2026-11-05", cost_usd: 0.6, tokens: 380000, questions: 19 },
    ],
    by_kind: [
      { kind: "Quick answer", questions: 8, avg_cost_usd: 0.02, share: 0.4 },
      { kind: "Quick answer with a retry", questions: 2, avg_cost_usd: 0.03, share: 0.15 },
      { kind: "Deep research", questions: 2, avg_cost_usd: 0.09, share: 0.45 },
    ],
    tokens_by_step: [
      { step: "draft", in: 120000, out: 30000 },
      { step: "verify", in: 60000, out: 4000 },
      { step: "rewrite", in: 8000, out: 500 },
    ],
    most_expensive: [{ id: "preview.1", question: "Example question", kind: "Deep research", tokens: 60000, cost_usd: 0.12 }],
    claims_removed_per_answer: 0.3, declined_share: 0.1, thumbs_down: null, median_seconds: { quick: 15, deep: 30 },
  },
};

export const REVIEW: ReviewItem = {
  id: "preview.1", ts: "2026-11-05T00:00:00Z", source: "user", session: "preview-session", question: "Example question", mode: "deep",
  kind: "Deep research", seconds: 30, status: "answered", audience: "researcher", claims_total: 3, claims_verified: 2,
  removed_claims: ["An example claim the sources didn't support."],
  paragraphs: ["An example finding [1]."],
  sources: [{ marker: 1, title: "Example publication", page: 4, url: null, passage: "Example passage." }],
  usage: { tokensIn: 50000, tokensOut: 10000, estimatedCostUsd: 0.12 },
};
