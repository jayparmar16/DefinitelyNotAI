"use client";

/** The side panel for one logged question (opened by ?review=<id>): what was asked and answered. */

import { seconds, traceUrl, usd, type ReviewItem } from "@/lib/admin";

export function ReviewPanel({ item, onClose }: { item: ReviewItem | null; onClose: () => void }) {
  const trace = item ? traceUrl(item.session) : null;
  return (
    <aside className="ad-review" aria-label="Question review">
      <div className="ad-review-head">
        <h2>Question review</h2>
        <button type="button" className="aw-btn sm" onClick={onClose}>Close</button>
      </div>
      {!item ? (
        <p className="ad-empty" style={{ padding: 16 }}>Loading…</p>
      ) : (
        <div className="ad-review-body">
          <p className="aw-meta">
            {new Date(item.ts).toLocaleString()} · {item.kind} · {item.status} · {seconds(item.seconds)}
            {item.usage ? ` · ${usd(item.usage.estimatedCostUsd)}` : ""}
            {trace ? <> · <a href={trace} target="_blank" rel="noreferrer">Trace in CloudWatch</a></> : " · Trace link not configured"}
          </p>
          <h3>Question</h3>
          <p className="aw-quote">{item.question}</p>
          <h3>Answer</h3>
          {item.paragraphs.length ? item.paragraphs.map((p, i) => <p key={i}>{p}</p>) : <p className="ad-empty">No answer text</p>}
          <h3>Claims</h3>
          <p>{item.claims_total === null ? "No data yet" : `${item.claims_verified} of ${item.claims_total} verified`}</p>
          {item.removed_claims.length > 0 && (
            <ul>{item.removed_claims.map((c, i) => <li key={i}>Removed: {c}</li>)}</ul>
          )}
          <h3>Sources</h3>
          {item.sources.length ? (
            <ol className="ad-list">
              {item.sources.map((s) => (
                <li key={s.marker}>
                  [{s.marker}] {s.url ? <a href={s.url} target="_blank" rel="noreferrer">{s.title}</a> : s.title}, p. {s.page}
                  <p className="aw-quote">{s.passage}</p>
                </li>
              ))}
            </ol>
          ) : (
            <p className="ad-empty">No sources</p>
          )}
          <h3>Scores</h3>
          <div className="ad-grid">
            {["Correctness", "Faithfulness", "Helpfulness"].map((n) => (
              <div className="ad-tile" key={n}><span className="ad-tile-label">{n}</span><div className="ad-tile-value small">No data yet</div></div>
            ))}
          </div>
          <div className="ad-review-actions">
            <button type="button" className="aw-btn sm" disabled>Mark reviewed</button>
            <button type="button" className="aw-btn sm" disabled>Flag as a content gap</button>
            <span className="aw-meta">Not wired yet</span>
          </div>
        </div>
      )}
    </aside>
  );
}
