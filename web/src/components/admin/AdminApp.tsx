"use client";

/**
 * The admin page: what WRI asked us to show (the latest evaluation run plus live speed), what
 * questions cost, and whether quality holds. Every number comes from the /admin API; a missing
 * value shows "No data yet", never a zero. Demo only: there is no access control yet.
 */

import { useEffect, useState } from "react";

import {
  adminMock,
  allDeclined,
  fetchOverview,
  fetchReview,
  percent,
  seconds,
  status,
  usd,
  type Overview,
  type ReviewItem,
  type Status,
  type Traffic,
  type Window,
} from "@/lib/admin";

import { SignOut } from "../SignOut";
import { ReviewPanel } from "./ReviewPanel";

type TileProps = { label: string; value: string; target?: string; status?: Status; source: "Evaluation" | "Live" | "Estimated"; note?: string };

function Tile({ label, value, target, status: state, source, note }: TileProps) {
  return (
    <div className="ad-tile">
      <div className="ad-tile-top">
        <span className="ad-tile-label">{label}</span>
        <span className="ad-source">{source}</span>
      </div>
      <div className={`ad-tile-value${value === "No data yet" ? " small" : ""}`}>{value}</div>
      <div className="ad-tile-foot">
        {state && <span className={`ad-status ${state === "On target" ? "ok" : state === "Below target" ? "bad" : "none"}`}>{state}</span>}
        {target && <span className="aw-meta">Target {target}</span>}
      </div>
      {note && <div className="aw-meta">{note}</div>}
    </div>
  );
}

// The AgentCore Evaluations judges shown, with our targets (null: monitored, no target).
const JUDGES = [
  { id: "Faithfulness", label: "Faithfulness", target: 0.8, note: "Claims grounded in the retrieved passages" },
  { id: "Correctness", label: "Correctness", target: 0.85, note: "Agrees with the test set's expected facts" },
  { id: "ResponseRelevance", label: "Response relevance", target: 0.9, note: "Answers the question asked" },
  { id: "Helpfulness", label: "Helpfulness", target: null, note: "Usefulness to the reader (monitored)" },
];

function Bars({ rows, label }: { rows: { name: string; value: number; shown: string }[]; label: string }) {
  const [table, setTable] = useState(false);
  const top = Math.max(...rows.map((r) => r.value), 0);
  if (!rows.length) return <p className="ad-empty">No data yet</p>;
  return (
    <div>
      <button type="button" className="aw-btn sm ghost link" onClick={() => setTable(!table)}>
        {table ? "View as chart" : "View as table"}
      </button>
      {table ? (
        <table className="ad-table">
          <thead><tr><th>{label}</th><th>Value</th></tr></thead>
          <tbody>{rows.map((r) => <tr key={r.name}><td>{r.name}</td><td>{r.shown}</td></tr>)}</tbody>
        </table>
      ) : (
        <div className="ad-bars" role="img" aria-label={label}>
          {rows.map((r) => (
            <div className="ad-bar-row" key={r.name}>
              <span className="ad-bar-name">{r.name}</span>
              <span className="ad-bar-track"><span className="ad-bar" style={{ width: `${top ? (r.value / top) * 100 : 0}%` }} /></span>
              <span className="ad-bar-value">{r.shown}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function readQuery() {
  const params = new URLSearchParams(window.location.search);
  return {
    traffic: (params.get("source") === "eval" ? "eval" : "user") as Traffic,
    window: (["24h", "30d"].includes(params.get("window") ?? "") ? params.get("window") : "7d") as Window,
    review: params.get("review"),
  };
}

function writeQuery(traffic: Traffic, range: Window, review: string | null) {
  const params = new URLSearchParams({ source: traffic, window: range });
  if (review) params.set("review", review);
  window.history.replaceState(null, "", `?${params}`);
}

export function AdminApp() {
  const [traffic, setTraffic] = useState<Traffic>("user");
  const [range, setRange] = useState<Window>("7d");
  const [review, setReview] = useState<string | null>(null);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [item, setItem] = useState<ReviewItem | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [money, setMoney] = useState<"cost" | "tokens">("cost");

  useEffect(() => {
    const q = readQuery();
    setTraffic(q.traffic);
    setRange(q.window);
    setReview(q.review);
  }, []);

  useEffect(() => {
    writeQuery(traffic, range, review);
    setOverview(null);
    setError(null);
    fetchOverview(traffic, range).then(setOverview, (e: Error) => setError(e.message));
  }, [traffic, range]);

  useEffect(() => {
    writeQuery(traffic, range, review);
    setItem(null);
    if (review) fetchReview(review).then(setItem, (e: Error) => setError(e.message));
  }, [review]);

  const card = overview?.scorecard ?? null;
  const live = overview?.live;

  return (
    <div className="ad-app">
      <header className="aw-header">
        <a className="aw-logo" href="/" style={{ color: "inherit", textDecoration: "none" }}>
          <span className="aw-logo-mark">WRI</span>AskWRI <small>admin</small>
        </a>
        <span className="spacer" />
        <SignOut />
      </header>

      <main className="ad-main">
        {adminMock && <p className="ad-banner warn">Layout preview: no API URL is set, so these are placeholder numbers, not results.</p>}
        {error && <p className="ad-banner bad">Couldn&apos;t load the admin numbers: {error}.</p>}

        <div className="ad-filters">
          <label>Traffic{" "}
            <select value={traffic} onChange={(e) => setTraffic(e.target.value as Traffic)}>
              <option value="user">Users</option>
              <option value="eval">Evaluation runs</option>
            </select>
          </label>
          <label>Window{" "}
            <select value={range} onChange={(e) => setRange(e.target.value as Window)}>
              <option value="24h">Last 24 hours</option>
              <option value="7d">Last 7 days</option>
              <option value="30d">Last 30 days</option>
            </select>
          </label>
        </div>

        <section className="ad-section">
          <h2>Quality scorecard</h2>
          <p className="aw-meta">Measured against WRI&apos;s success criteria on the evaluation test set; latency from live traffic.</p>
          {card ? (
            <p className="ad-run">
              Evaluation run <b>{card.run_id}</b> · {new Date(card.run_date).toLocaleString()} · {card.configuration ?? "default configuration"} · {card.questions}-question test set
              {card.judged ? " · graded by AgentCore Evaluations" : ""}
            </p>
          ) : (
            overview && <p className="ad-empty">No evaluation run yet. Run <code>uv run python -m eval.run_eval run</code>.</p>
          )}
          <div className="ad-grid">
            <Tile label="Citation coverage" value={percent(card?.figures_cited_rate)} target="100%" status={status(card?.figures_cited_rate, 1, "higher")} source="Evaluation" note="Answers with every figure cited" />
            <Tile label="Retrieval recall@5" value={percent(card?.recall_at_5)} target="≥ 75%" status={status(card?.recall_at_5, 0.75, "higher")} source="Evaluation" note="Expected source in the top 5 results" />
            <Tile label="Retrieval precision@5" value={percent(card?.precision_at_5)} source="Evaluation" note="Relevant results among the top 5 (monitored)" />
            <Tile label="Abstention accuracy" value={card?.unanswerable_declined ?? "–"} target="100%" status={allDeclined(card?.unanswerable_declined)} source="Evaluation" note="Out-of-scope questions correctly declined" />
            <Tile label="Median latency · Quick answer" value={seconds(live?.median_seconds.quick)} target="< 60 s" status={status(live?.median_seconds.quick, 60, "lower")} source="Live" note="Time to a cited answer" />
            <Tile label="Median latency · Deep research" value={seconds(live?.median_seconds.deep)} target="< 60 s" status={status(live?.median_seconds.deep, 60, "lower")} source="Live" note="Time to a cited report" />
          </div>
          <h3 className="ad-subhead">Model-graded quality · AgentCore Evaluations</h3>
          <div className="ad-grid">
            {JUDGES.map((judge) => {
              const score = card?.judges?.[judge.id] ?? null;
              return (
                <Tile
                  key={judge.id}
                  label={judge.label}
                  value={score === null ? "–" : score.toFixed(2)}
                  target={judge.target === null ? undefined : `≥ ${judge.target.toFixed(2)}`}
                  status={judge.target === null ? undefined : status(score, judge.target, "higher")}
                  source="Evaluation"
                  note={judge.note}
                />
              );
            })}
          </div>
        </section>

        <section className="ad-section">
          <h2>Cost and usage</h2>
          <p className="aw-meta">Estimated from token usage at Amazon Bedrock list prices.</p>
          <div className="ad-grid">
            <Tile label="Cost per answer" value={usd(live?.cost_per_answer_usd)} source="Estimated" note={live ? `${live.questions} questions in this window` : undefined} />
            <Tile label="Projected cost per 1,000 answers" value={usd(live?.projected_per_1000_usd, 2)} source="Estimated" />
            <Tile label="Median tokens per answer" value={live?.tokens_per_answer_median?.toLocaleString() ?? "–"} source="Live" />
            <Tile label="Spend · last 30 days" value={usd(live?.spend_30d_usd, 2)} source="Estimated" note={live ? `Budget $${live.sandbox_cap_usd}` : undefined} />
          </div>
          <div className="ad-cols">
            <div className="ad-box">
              <div className="ad-box-head">
                <h3>Daily spend</h3>
                <span className="ad-switch">
                  <button type="button" className={money === "cost" ? "on" : ""} onClick={() => setMoney("cost")}>Cost</button>
                  <button type="button" className={money === "tokens" ? "on" : ""} onClick={() => setMoney("tokens")}>Tokens</button>
                </span>
              </div>
              <Bars label="Day" rows={(live?.spend_per_day ?? []).map((d) => ({ name: d.day.slice(5), value: money === "cost" ? d.cost_usd : d.tokens, shown: money === "cost" ? usd(d.cost_usd, 2) : d.tokens.toLocaleString() }))} />
            </div>
            <div className="ad-box">
              <h3>Cost by request type</h3>
              <Bars label="Kind" rows={(live?.by_kind ?? []).map((k) => ({ name: `${k.kind} (${k.questions})`, value: k.share ?? 0, shown: `${percent(k.share)} · ${usd(k.avg_cost_usd)} each` }))} />
            </div>
            <div className="ad-box">
              <h3>Token usage by pipeline step · 7 days</h3>
              <Bars label="Step" rows={(live?.tokens_by_step ?? []).map((s) => ({ name: s.step, value: s.in + s.out, shown: `${s.in.toLocaleString()} in · ${s.out.toLocaleString()} out` }))} />
            </div>
            <div className="ad-box">
              <h3>Highest-cost requests</h3>
              {live?.most_expensive.length ? (
                <ol className="ad-list">
                  {live.most_expensive.map((q) => (
                    <li key={q.id}>
                      <button type="button" className="ad-link" onClick={() => setReview(q.id)}>{q.question}</button>
                      <span className="aw-meta">{q.kind} · {q.tokens?.toLocaleString() ?? "–"} tokens · {usd(q.cost_usd)}</span>
                    </li>
                  ))}
                </ol>
              ) : (
                <p className="ad-empty">No data yet</p>
              )}
            </div>
          </div>
        </section>

        <section className="ad-section">
          <h2>Live quality signals</h2>
          <div className="ad-grid">
            <Tile label="Unsupported claims removed per answer" value={live?.claims_removed_per_answer?.toString() ?? "–"} source="Live" note="Caught by verification before display" />
            <Tile label="Decline rate" value={percent(live?.declined_share)} source="Live" note="Questions answered with 'no WRI evidence'" />
            <Tile label="Negative feedback" value={live?.thumbs_down?.toString() ?? "No data yet"} source="Live" note="User feedback capture not yet enabled" />
          </div>
        </section>
      </main>

      {review && <ReviewPanel item={item} onClose={() => setReview(null)} />}
    </div>
  );
}
