"use client";

/**
 * Infographics for an answer or an Explore topic: key figures, a citation map (reports by year,
 * arrows from each report to the later ones that build on it), and the evidence matrix. Each
 * visual stands alone and says when it's empty.
 */

import { useState } from "react";

import type { CitationFlow, Empty, FlowLink, KeyFigure, LensResult, Relation, Source, Timeline, Visuals } from "@/lib/agent";
import { CARD_H, CARD_W, citationMap } from "@/lib/citationMap";
import { type ClaimsMatrix, claimsMatrix } from "@/lib/matrix";
import { MatrixTable } from "./MatrixTable";
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

/** The citation map as a family tree: a generation per year, elbow connectors from each report
 * down to the later reports that build on it, and undated reports listed under the tree. */
function CitationMapView({ timeline, flow, onOpenPage }: MapProps) {
  const map = citationMap(timeline, flow);
  const linked = new Set(map.links.flatMap((e) => [e.from, e.to]));
  const [picked, setPicked] = useState<string | null>(map.edges[0]?.to ?? map.links[0]?.to ?? timeline.newest);
  const titles = new Map([...map.nodes, ...map.undated].map((n) => [n.docId, n.title]));
  const title = (id: string) => titles.get(id) ?? id;
  const node = map.nodes.find((n) => n.docId === picked);
  const loose = map.undated.find((n) => n.docId === picked);
  const cites = map.links.filter((e) => e.to === picked);
  const citedBy = map.links.filter((e) => e.from === picked);
  const relations = [...new Set(map.edges.map((e) => e.relation))];

  return (
    <div className="aw-map">
      {map.nodes.length > 0 && (
        <div className="aw-map-scroll">
          <svg viewBox={`0 0 ${map.width} ${map.height}`} style={{ maxWidth: map.width * 1.25 }} role="img" aria-label="Citation tree of the reports">
            <defs>
              {(Object.keys(RELATION_COLORS) as Relation[]).map((relation) => (
                <marker key={relation} id={`arrow-${relation}`} viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                  <path d="M0,1 L9,5 L0,9 z" fill={RELATION_COLORS[relation]} />
                </marker>
              ))}
            </defs>
            {map.rows.map((row, i) => (
              <g key={row.label}>
                {i % 2 === 0 && <rect className="aw-map-band" x="0" y={row.y - 12} width={map.width} height={CARD_H + 24} rx="6" />}
                <rect className="aw-map-year-chip" x="4" y={row.y + CARD_H / 2 - 11} width="52" height="22" rx="11" />
                <text x="30" y={row.y + CARD_H / 2 + 4} textAnchor="middle" className="aw-map-year">{row.label}</text>
              </g>
            ))}
            {map.edges.map((edge) => {
              const key = `${edge.from}>${edge.to}`;
              const on = picked === edge.from || picked === edge.to;
              return (
                <path
                  key={key}
                  className="aw-map-edge"
                  d={map.paths[key]}
                  stroke={RELATION_COLORS[edge.relation]}
                  strokeWidth={on ? 2.5 : 1.6}
                  strokeDasharray={edge.relation === "contrasts" ? "5 4" : undefined}
                  opacity={picked && !on ? 0.3 : 1}
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
                <rect className="aw-map-card" width={CARD_W} height={CARD_H} rx="10" />
                <rect className="aw-map-strip" width="5" height={CARD_H} rx="2.5" />
                {n.lines.map((line, i) => (
                  <text key={i} x="16" y={22 + i * 16} className="aw-map-title">{line}</text>
                ))}
                <text x="16" y={CARD_H - 10} className="aw-map-sub">
                  {n.year}{n.citedInAnswer ? " · cited in the answer" : ""}
                </text>
                {n.citedBy > 0 && (
                  <g transform={`translate(${CARD_W - 10},0)`}>
                    <title>{`Cited by ${n.citedBy} report${n.citedBy === 1 ? "" : "s"} in AskWRI`}</title>
                    <circle r="10" className="aw-map-badge" />
                    <text textAnchor="middle" y="4" className="aw-map-badge-n">{n.citedBy}</text>
                  </g>
                )}
              </g>
            ))}
          </svg>
        </div>
      )}
      {map.undated.length > 0 && (
        <div className="aw-map-undated">
          <span className="aw-meta">No publication year, so not in the tree:</span>
          {map.undated.map((n) => (
            <button
              key={n.docId}
              className={`aw-map-chip${n.citedInAnswer ? " cited" : ""}${n.docId === picked ? " on" : ""}`}
              onClick={() => setPicked(n.docId)}
              title={n.title}
            >
              {n.title}
            </button>
          ))}
        </div>
      )}
      <p className="aw-meta aw-legend">
        <span className="aw-key cited" /> cited in the answer <span className="aw-key" /> linked by citation
        {relations.map((relation) => (
          <span key={relation} className="aw-legend-rel">
            <span className="aw-legend-line" style={{ background: RELATION_COLORS[relation] }} /> {RELATION_LABELS[relation]}
          </span>
        ))}
        {" "}· numbers: cited by N reports
      </p>
      {(node || loose) && (
        <div className="aw-flow-detail">
          <b>{(node ?? loose)!.title}</b>
          <span className="aw-meta">{node?.year ?? "No publication year"}{(node ?? loose)!.citedInAnswer ? " · cited in the answer" : ""}</span>
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
    <MatrixTable
      label="Evidence matrix"
      columns={matrix.columns.map((column) => ({ label: column.label, title: column.text }))}
      rows={matrix.rows.map((row, r) => ({
        ...row,
        cells: matrix.cells[r].map((backs) =>
          backs ? { content: "✓", tick: true } : { content: "–", tick: true, empty: true },
        ),
      }))}
    />
  );
}

type VisualsViewProps = {
  visuals: Visuals;
  answer?: { paragraphs: string[]; sources: Source[]; themes?: string[] };
  lens?: LensResult;
  matrix?: boolean;
  activeMarker: number | null;
  onMarker: (marker: number) => void;
  onOpenPage: (link: FlowLink) => void;
};

export function VisualsView({ visuals, answer, lens, matrix, activeMarker, onMarker, onOpenPage }: VisualsViewProps) {
  const figures = visuals.keyFigures;
  const claims = !lens && answer ? claimsMatrix(answer.paragraphs, answer.sources, answer.themes) : null;
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
        <Section title="Evidence matrix" caption="Which publication backs which point of the answer. Hover a heading for the full point; for a matrix by aspect, use a Lens or a Topic dossier.">
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
