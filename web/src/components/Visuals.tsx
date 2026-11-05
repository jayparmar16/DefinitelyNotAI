"use client";

/**
 * Infographics for an answer or an Explore topic: key figures, a citation map (reports by year,
 * arrows from each report to the later ones that build on it), and the evidence matrix. Each
 * visual stands alone and says when it's empty.
 */

import { useState } from "react";

import type { CitationFlow, Empty, FlowLink, KeyFigure, LensResult, Relation, Source, Timeline, Visuals } from "@/lib/agent";
import { CARD_H, CARD_W, WIDTH, citationMap } from "@/lib/citationMap";
import { type ClaimsMatrix, claimsMatrix } from "@/lib/matrix";
import { LensTable } from "./LensTable";

const RELATION_LABELS: Record<Relation, string> = {
  updates: "updates",
  uses_data_or_method: "uses data or method",
  extends: "extends",
  contrasts: "contrasts",
  supports: "supports",
  background: "mentions",
};

function isEmpty<T extends object>(visual: T | Empty | undefined): visual is Empty | undefined {
  return !visual || "empty" in visual;
}

function Section({ title, caption, children }: { title: string; caption?: string; children: React.ReactNode }) {
  return (
    <section className="aw-visual">
      <h4>{title}</h4>
      {caption && <p className="aw-meta">{caption}</p>}
      {children}
    </section>
  );
}

function KeyFigures({ cards, onMarker }: { cards: KeyFigure[]; onMarker: (marker: number) => void }) {
  return (
    <div className="aw-figures">
      {cards.map((card) => (
        <button key={card.docId} className="aw-figure" onClick={() => onMarker(card.marker)} title={card.title}>
          <span className="v">
            {card.value}
            {card.unit && <small> {card.unit}</small>}
          </span>
          <span className="w">{card.what}</span>
          <span className="aw-meta">
            {[card.place, card.year].filter(Boolean).join(" · ")} [{card.marker}]
          </span>
        </button>
      ))}
    </div>
  );
}

const RELATION_COLORS: Record<Relation, string> = {
  updates: "var(--rel-updates)",
  uses_data_or_method: "var(--rel-uses)",
  extends: "var(--rel-extends)",
  contrasts: "var(--rel-contrasts)",
  supports: "var(--rel-supports)",
  background: "var(--rel-mentions)",
};

type MapProps = {
  timeline: Timeline;
  flow?: CitationFlow;
  onOpenPage: (link: FlowLink) => void;
};

/** One citation map: rows of years, report cards, arrows from a report to those that cite it. */
function CitationMapView({ timeline, flow, onOpenPage }: MapProps) {
  const map = citationMap(timeline, flow);
  const linked = new Set(map.edges.flatMap((e) => [e.from, e.to]));
  const [picked, setPicked] = useState<string | null>(map.edges[0]?.to ?? timeline.newest);
  const node = map.nodes.find((n) => n.docId === picked);
  const at = (id: string) => map.nodes.find((n) => n.docId === id)!;
  const cites = map.edges.filter((e) => e.to === picked);
  const citedBy = map.edges.filter((e) => e.from === picked);
  const title = (id: string) => at(id).title;

  return (
    <div className="aw-map">
      <div className="aw-map-scroll">
        <svg viewBox={`0 0 ${WIDTH} ${map.height}`} role="img" aria-label="Citation map of the reports">
          <defs>
            {(Object.keys(RELATION_COLORS) as Relation[]).map((relation) => (
              <marker key={relation} id={`arrow-${relation}`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                <path d="M0,0 L10,5 L0,10 z" fill={RELATION_COLORS[relation]} />
              </marker>
            ))}
          </defs>
          {map.rows.map((row) => (
            <text key={row.label} x="0" y={row.y + CARD_H / 2 + 4} className="aw-map-year">{row.label}</text>
          ))}
          {map.edges.map((edge) => {
            const a = at(edge.from), b = at(edge.to);
            const x1 = a.x + CARD_W / 2, y1 = a.y + CARD_H, x2 = b.x + CARD_W / 2, y2 = b.y;
            const bend = Math.max(24, (y2 - y1) / 2);
            const on = picked === edge.from || picked === edge.to;
            return (
              <path
                key={`${edge.from}>${edge.to}`}
                d={`M${x1},${y1} C${x1},${y1 + bend} ${x2},${y2 - bend} ${x2},${y2 - 2}`}
                fill="none"
                stroke={RELATION_COLORS[edge.relation]}
                strokeWidth={on ? 2.5 : 1.5}
                strokeDasharray={edge.relation === "contrasts" ? "5 4" : undefined}
                opacity={picked && !on ? 0.25 : 1}
                markerEnd={`url(#arrow-${edge.relation})`}
              />
            );
          })}
          {map.nodes.map((n) => (
            <g
              key={n.docId}
              className={`aw-map-node${n.citedInAnswer ? " cited" : ""}${n.docId === picked ? " on" : ""}${linked.has(n.docId) ? "" : " alone"}`}
              transform={`translate(${n.x},${n.y})`}
              onClick={() => setPicked(n.docId)}
              onKeyDown={(event) => event.key === "Enter" && setPicked(n.docId)}
              tabIndex={0}
              role="button"
              aria-label={`${n.title}${n.year ? `, ${n.year}` : ""}`}
            >
              <title>{n.title}</title>
              <rect width={CARD_W} height={CARD_H} rx="8" />
              {n.lines.map((line, i) => (
                <text key={i} x="10" y={20 + i * 16}>{line}</text>
              ))}
              {n.citedBy > 0 && (
                <g transform={`translate(${CARD_W - 12},-6)`}>
                  <circle r="9" className="aw-map-badge" />
                  <text textAnchor="middle" y="4" className="aw-map-badge-n">{n.citedBy}</text>
                </g>
              )}
            </g>
          ))}
        </svg>
      </div>
      <p className="aw-meta aw-legend">
        <span className="aw-key cited" /> cited in the answer <span className="aw-key" /> linked by citation · numbers: cited by N reports
      </p>
      {node && (
        <div className="aw-flow-detail">
          <b>{node.title}</b>
          <span className="aw-meta">{node.year ?? "Undated"}{node.citedInAnswer ? " · cited in the answer" : ""}</span>
          {cites.length + citedBy.length === 0 && (
            <span className="aw-meta">No citation links to other reports in AskWRI&apos;s collection.</span>
          )}
          {[...cites.map((e) => ({ e, other: e.from, verb: "builds on" })), ...citedBy.map((e) => ({ e, other: e.to, verb: "is built on by" }))].map(({ e, other, verb }) => (
            <div key={`${e.from}>${e.to}`} className="aw-map-link">
              <div>
                <span className={`aw-rel ${e.relation}`}>{RELATION_LABELS[e.relation]}</span> {verb} <b>{title(other)}</b>
              </div>
              {e.sentence && <blockquote>&ldquo;{e.sentence}&rdquo;</blockquote>}
              {e.pdfKey && e.page && (
                <button
                  className="aw-btn sm"
                  onClick={() => onOpenPage({ docId: e.to, title: title(e.to), year: null, relation: e.relation, aspect: e.aspect, sentence: e.sentence, page: e.page, pdfKey: e.pdfKey, confidence: null })}
                >
                  Open page {e.page} of the citing report
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ClaimsMatrixTable({ matrix }: { matrix: ClaimsMatrix }) {
  return (
    <div className="aw-lens aw-claims">
      <div className="aw-lens-scroll">
        <table>
          <thead>
            <tr>
              <th scope="col">Report</th>
              {matrix.columns.map((column, i) => (
                <th key={i} scope="col" title={column.text}>{column.label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {matrix.rows.map((row, r) => (
              <tr key={row.docId}>
                <th scope="row">
                  {row.title}
                  <span className="aw-meta">{row.year ?? "n.d."}</span>
                </th>
                {matrix.cells[r].map((backs, c) => (
                  <td key={c} className={backs ? "aw-tick" : "empty"} aria-label={backs ? "cited for this point" : "not cited"}>
                    {backs ? "✓" : "–"}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

type VisualsViewProps = {
  visuals: Visuals;
  answer?: { paragraphs: string[]; sources: Source[] };
  lens?: LensResult;
  matrix?: boolean;
  activeMarker: number | null;
  onMarker: (marker: number) => void;
  onOpenPage: (link: FlowLink) => void;
};

export function VisualsView({ visuals, answer, lens, matrix, activeMarker, onMarker, onOpenPage }: VisualsViewProps) {
  const figures = visuals.keyFigures;
  const claims = !lens && answer ? claimsMatrix(answer.paragraphs, answer.sources) : null;
  return (
    <div className="aw-visuals">
      {!isEmpty(figures) && figures.cards.length > 0 && (
        <Section title="Key figures" caption={figures.caption}>
          <KeyFigures cards={figures.cards} onMarker={onMarker} />
        </Section>
      )}
      {isEmpty(visuals.timeline) ? (
        <Section title="Citation map" caption={visuals.timeline?.reason} >{null}</Section>
      ) : (
        <Section
          title="Citation map"
          caption={`${visuals.timeline.caption}. ${visuals.citationFlow?.caption ?? ""}. Click a report to see what it builds on and what builds on it.`}
        >
          <CitationMapView timeline={visuals.timeline} flow={visuals.citationFlow} onOpenPage={onOpenPage} />
        </Section>
      )}
      {lens ? (
        <section className="aw-visual">
          <LensTable lens={lens} activeMarker={activeMarker} onMarker={onMarker} matrix={matrix} />
        </section>
      ) : claims ? (
        <Section title="Evidence matrix" caption="Which report backs which point of the answer (hover a column for the full point). For a matrix by topic, use a Lens or a Topic dossier.">
          <ClaimsMatrixTable matrix={claims} />
        </Section>
      ) : answer ? (
        <Section title="Evidence matrix" caption="The answer rests on one report, so there is nothing to compare. A Lens or a Topic dossier reads more papers." >
          {null}
        </Section>
      ) : null}
    </div>
  );
}
