"use client";

/**
 * Infographics for an answer or an Explore topic: key figures, a publication timeline, the
 * citation flow between reports (which reports a report builds on, and which build on it), and
 * the evidence matrix when the answer has one. Each visual stands alone and says when it's empty.
 */

import { useState } from "react";

import type { CitationFlow, Empty, FlowLink, KeyFigure, LensResult, Relation, Timeline, Visuals } from "@/lib/agent";
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

function TimelineChart({ timeline }: { timeline: Timeline }) {
  const [picked, setPicked] = useState<string | null>(null);
  const years = timeline.points.map((p) => p.year!);
  const first = Math.min(...years);
  const last = Math.max(...years);
  const span = Math.max(1, last - first);
  const x = (year: number) => 24 + ((year - first) / span) * 552;
  // Reports in the same year stack upwards so none hides another.
  const stack = new Map<number, number>();
  const placed = timeline.points.map((point) => {
    const level = stack.get(point.year!) ?? 0;
    stack.set(point.year!, level + 1);
    return { point, cx: x(point.year!), cy: 62 - level * 16 };
  });
  const ticks = [...new Set([first, Math.round((first + last) / 2), last])];
  const shown = timeline.points.find((p) => p.docId === picked) ?? timeline.points.find((p) => p.docId === timeline.newest);

  return (
    <div className="aw-timeline">
      <svg viewBox="0 0 600 96" role="img" aria-label={timeline.caption}>
        <line x1="16" x2="584" y1="72" y2="72" className="axis" />
        {ticks.map((year) => (
          <g key={year}>
            <line x1={x(year)} x2={x(year)} y1="70" y2="76" className="axis" />
            <text x={x(year)} y="90" textAnchor="middle">{year}</text>
          </g>
        ))}
        {placed.map(({ point, cx, cy }) => (
          <circle
            key={point.docId}
            cx={cx}
            cy={cy}
            r={point.docId === picked ? 8 : 6}
            className={point.citedInAnswer ? "dot cited" : "dot"}
            onClick={() => setPicked(point.docId)}
            tabIndex={0}
            role="button"
            aria-label={`${point.title}, ${point.year}`}
          >
            <title>{`${point.title} (${point.year})`}</title>
          </circle>
        ))}
      </svg>
      {shown && (
        <p className="aw-timeline-pick">
          <b>{shown.year}</b> · {shown.title}
          {shown.docId === timeline.newest && <span className="aw-chip">newest</span>}
          {shown.citedBy > 0 && <span className="aw-chip">cited by {shown.citedBy}</span>}
          {!shown.citedInAnswer && <span className="aw-chip">linked by citation</span>}
        </p>
      )}
      <p className="aw-meta aw-legend">
        <span className="dot cited" /> cited in the answer <span className="dot" /> linked by citation · click a dot
      </p>
      {timeline.undated.length > 0 && (
        <p className="aw-meta">Undated: {timeline.undated.map((p) => p.title).join(" · ")}</p>
      )}
    </div>
  );
}

function LinkCard({ link, active, onPick }: { link: FlowLink; active: boolean; onPick: () => void }) {
  return (
    <button className={active ? "aw-flow-card on" : "aw-flow-card"} onClick={onPick}>
      <span className={`aw-rel ${link.relation}`}>{RELATION_LABELS[link.relation]}</span>
      <span className="t">{link.title}</span>
      <span className="aw-meta">{link.year ?? "n.d."}</span>
    </button>
  );
}

type FlowProps = { flow: CitationFlow; onOpenPage: (link: FlowLink) => void; onMarker: (marker: number) => void };

function CitationFlowView({ flow, onOpenPage, onMarker }: FlowProps) {
  const [focusId, setFocusId] = useState(flow.defaultFocus);
  const [picked, setPicked] = useState<{ link: FlowLink; direction: "cites" | "citedBy" } | null>(null);
  const current = focusId ? flow.flows[focusId] : null;
  if (!current) return null;
  const pick = (link: FlowLink, direction: "cites" | "citedBy") => setPicked(picked?.link === link ? null : { link, direction });

  return (
    <div className="aw-flow">
      {flow.focusOptions.length > 1 && (
        <div className="aw-flow-focus" role="tablist" aria-label="Report to centre on">
          {flow.focusOptions.map((option) => (
            <button
              key={option.docId}
              role="tab"
              aria-selected={option.docId === focusId}
              className={option.docId === focusId ? "aw-chip on" : "aw-chip"}
              onClick={() => {
                setFocusId(option.docId);
                setPicked(null);
              }}
              title={option.title}
            >
              {option.title.length > 34 ? `${option.title.slice(0, 32)}…` : option.title}
            </button>
          ))}
        </div>
      )}

      <div className="aw-flow-col">
        <div className="aw-flow-row">
          <span className="lbl">Builds on</span>
          {current.cites.length ? (
            current.cites.map((link) => (
              <LinkCard key={link.docId} link={link} active={picked?.link === link} onPick={() => pick(link, "cites")} />
            ))
          ) : (
            <span className="aw-meta">No other report in AskWRI&apos;s collection</span>
          )}
          {current.moreCites > 0 && <span className="aw-chip">+{current.moreCites} more</span>}
        </div>
        <div className="aw-flow-arrow" aria-hidden>↓</div>
        <div className="aw-flow-focus-card">
          <b>{current.focus.title}</b>
          <span className="aw-meta">
            {current.focus.year ?? "n.d."}
            {current.focus.markers.length > 0 && ` · cited in the answer as ${current.focus.markers.map((m) => `[${m}]`).join("")}`}
          </span>
        </div>
        <div className="aw-flow-arrow" aria-hidden>↓</div>
        <div className="aw-flow-row">
          <span className="lbl">Built on by</span>
          {current.citedBy.length ? (
            current.citedBy.map((link) => (
              <LinkCard key={link.docId} link={link} active={picked?.link === link} onPick={() => pick(link, "citedBy")} />
            ))
          ) : (
            <span className="aw-meta">No later report in AskWRI&apos;s collection</span>
          )}
          {current.moreCitedBy > 0 && <span className="aw-chip">+{current.moreCitedBy} more</span>}
        </div>
        {current.mainPoint && (
          <>
            <div className="aw-flow-arrow" aria-hidden>↓</div>
            <button
              className="aw-flow-point"
              onClick={() => current.focus.markers[0] && onMarker(current.focus.markers[0])}
              title="Open this source"
            >
              <span className="lbl">Supports in the answer</span>
              {current.mainPoint}
            </button>
          </>
        )}
      </div>

      {picked && (
        <div className="aw-flow-detail">
          <div>
            {picked.direction === "cites" ? (
              <><b>{current.focus.title}</b> {RELATION_LABELS[picked.link.relation]} <b>{picked.link.title}</b></>
            ) : (
              <><b>{picked.link.title}</b> {RELATION_LABELS[picked.link.relation]} <b>{current.focus.title}</b></>
            )}
          </div>
          {picked.link.aspect && <div className="aw-meta">About: {picked.link.aspect}</div>}
          {picked.link.sentence && <blockquote>&ldquo;{picked.link.sentence}&rdquo;</blockquote>}
          {picked.link.pdfKey && picked.link.page && (
            <button className="aw-btn sm" onClick={() => onOpenPage(picked.link)}>
              Open page {picked.link.page} of the citing report
            </button>
          )}
        </div>
      )}
      <p className="aw-meta aw-legend">
        {(["updates", "uses_data_or_method", "extends", "contrasts", "supports", "background"] as Relation[]).map((relation) => (
          <span key={relation} className={`aw-rel ${relation}`}>{RELATION_LABELS[relation]}</span>
        ))}
      </p>
    </div>
  );
}

type VisualsViewProps = {
  visuals: Visuals;
  lens?: LensResult;
  matrix?: boolean;
  activeMarker: number | null;
  onMarker: (marker: number) => void;
  onOpenPage: (link: FlowLink) => void;
};

export function VisualsView({ visuals, lens, matrix, activeMarker, onMarker, onOpenPage }: VisualsViewProps) {
  const figures = visuals.keyFigures;
  return (
    <div className="aw-visuals">
      {!isEmpty(figures) && figures.cards.length > 0 && (
        <Section title="Key figures" caption={figures.caption}>
          <KeyFigures cards={figures.cards} onMarker={onMarker} />
        </Section>
      )}
      <Section title="Publication timeline" caption={isEmpty(visuals.timeline) ? visuals.timeline?.reason : visuals.timeline.caption}>
        {!isEmpty(visuals.timeline) && <TimelineChart timeline={visuals.timeline} />}
      </Section>
      {visuals.citationFlow && visuals.citationFlow.focusOptions.length > 0 && (
        <Section title="Citation flow" caption={visuals.citationFlow.caption}>
          <CitationFlowView flow={visuals.citationFlow} onOpenPage={onOpenPage} onMarker={onMarker} />
        </Section>
      )}
      {lens && (
        <Section title="Evidence matrix">
          <LensTable lens={lens} activeMarker={activeMarker} onMarker={onMarker} matrix={matrix} />
        </Section>
      )}
    </div>
  );
}
