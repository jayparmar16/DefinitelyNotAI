"use client";

/**
 * The resizable, closable side panel: the Deep research report, the sources list, and one
 * tab per opened source showing the cited page with the passage highlighted.
 */

import { type PointerEvent as ReactPointerEvent, useEffect, useState } from "react";

import type { ReportFormat, Source } from "@/lib/agent";
import { citationYear, pageLink } from "@/lib/citations";
import { AnswerSections, VerifiedChip, readerName } from "./AnswerSections";
import { Icon } from "./Icon";
import { MarkedText } from "./MarkedText";
import { Passage, sourceMeta } from "./SourceCards";
import { type Turn, shownAnswer } from "./turn";

export type PanelTab = "report" | "sources" | number; // a number is an open source's marker

const FORMATS: { value: ReportFormat; name: string }[] = [
  { value: "talking-points", name: "Talking points" },
  { value: "issue-brief", name: "Issue brief" },
  { value: "summary", name: "Researcher summary" },
];
const MIN_WIDTH = 360;
const MAX_WIDTH = 760;

type SidePanelProps = {
  turn: Turn;
  tab: PanelTab;
  openDocs: number[];
  activeMarker: number | null;
  width: number;
  format: ReportFormat;
  languageName: string;
  onTab: (tab: PanelTab) => void;
  onCloseDoc: (marker: number) => void;
  onMarker: (marker: number) => void;
  onFormat: (format: ReportFormat) => void;
  onPdf: (source: Source) => void;
  onDownloadReport: () => void;
  onWidth: (width: number) => void;
  onClose: () => void;
  onFollowUp: (question: string) => void;
  /** A short-lived link to the stored PDF, or null when there is none (the mock). */
  pdfUrl: (source: Source) => Promise<string | null>;
};

function ResizeHandle({ width, onWidth }: { width: number; onWidth: (width: number) => void }) {
  const [dragging, setDragging] = useState(false);
  const start = (event: ReactPointerEvent<HTMLDivElement>) => {
    const startX = event.clientX;
    const startWidth = width;
    setDragging(true);
    const move = (moveEvent: PointerEvent) => {
      const next = startWidth + (startX - moveEvent.clientX);
      onWidth(Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, next)));
    };
    const stop = () => {
      setDragging(false);
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", stop);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", stop);
  };
  return (
    <div
      className={dragging ? "aw-resize dragging" : "aw-resize"}
      onPointerDown={start}
      role="separator"
      aria-orientation="vertical"
      aria-label="Resize panel"
    />
  );
}

function ReportView(props: SidePanelProps) {
  const { turn } = props;
  const report = turn.answer?.report;
  if (!report) {
    return (
      <div className="aw-report">
        <div className="aw-meta">Briefing · {props.languageName}</div>
        <h2>{turn.status === "running" ? "Building your report…" : "No report"}</h2>
        <p className="aw-meta">
          {turn.status === "running"
            ? `${turn.found.length} sources found so far. Key points appear once every claim is verified.`
            : "The run ended before a report was written."}
        </p>
        {turn.status === "running" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 12, marginTop: 24 }}>
            <div className="aw-bar dark" style={{ width: "60%" }} />
            <div className="aw-bar" /><div className="aw-bar" style={{ width: "90%" }} /><div className="aw-bar" style={{ width: "75%" }} />
          </div>
        )}
      </div>
    );
  }
  const answer = shownAnswer(turn)!;
  const translated = Boolean(turn.translation && !turn.translation.showOriginal);
  const shownReport = answer.report ?? report;
  const authors = [...new Set(answer.sources.flatMap((source) => source.authors))];
  return (
    <div className="aw-report">
      <div className="aw-meta">
        Briefing · for {readerName(answer.audience)} · {props.languageName}
        {(answer.machineTranslated || translated) && <> · <span className="aw-mt">Machine-translated</span></>}
      </div>
      <h2>{shownReport.title}</h2>
      <div className="aw-meta">{report.builtFrom}</div>
      {answer.scope && <div className="aw-scope">{answer.scope}</div>}
      <div style={{ marginTop: 8 }}><VerifiedChip answer={answer} /></div>
      <h4>Key points</h4>
      <ul>
        {(translated ? answer.paragraphs : shownReport.keyPoints).map((point, index) => (
          <li key={index}>
            <MarkedText text={point} activeMarker={props.activeMarker} onMarker={props.onMarker} />
          </li>
        ))}
      </ul>
      {turn.outdated.map((flag) => (
        <p key={flag.text} className="aw-meta" style={{ marginTop: 12 }}>
          <Icon name="warning" small /> {flag.text}
        </p>
      ))}
      <h4>Where the evidence is thin</h4>
      <ul>
        {shownReport.thinEvidence.map((point) => (
          <li key={point}>{point}</li>
        ))}
      </ul>
      <AnswerSections answer={answer} onFollowUp={props.onFollowUp} showLimits={false} />
      <h4>People behind this work</h4>
      <div className="aw-searched">
        {authors.map((author) => (
          <span key={author}>
            <Icon name="person" small /> {author}
          </span>
        ))}
      </div>
    </div>
  );
}

function whyLine(source: Source): string | null {
  const why = source.why;
  if (!why) return null;
  const how = [why.by_meaning && "meaning", why.by_keyword && "keywords"].filter(Boolean).join(" and ");
  const terms = why.matched_terms.length ? ` (${why.matched_terms.slice(0, 6).join(", ")})` : "";
  return how ? `Found by ${how}${terms}.` : null;
}

/** The cited passage, why it was found, then the stored PDF opened at the cited page. */
function SourceView({ source, pdfUrl }: { source: Source; pdfUrl: SidePanelProps["pdfUrl"] }) {
  const [pdf, setPdf] = useState<{ chunkId: string; url: string | null; failed: boolean } | null>(null);
  useEffect(() => {
    let current = true;
    pdfUrl(source)
      .then((url) => current && setPdf({ chunkId: source.chunkId, url, failed: false }))
      .catch(() => current && setPdf({ chunkId: source.chunkId, url: null, failed: true }));
    return () => {
      current = false;
    };
  }, [source, pdfUrl]);
  const loaded = pdf?.chunkId === source.chunkId ? pdf : null;
  const why = whyLine(source);
  return (
    <div className="aw-doc">
      <div className="aw-doc-head">
        <h3>{source.title}</h3>
      </div>
      <div className="aw-doc-cited">
        <div className="cap">Cited passage</div>
        <Passage source={source} />
        {why && <div className="aw-meta">{why}</div>}
      </div>
      {!loaded ? (
        <div className="aw-empty">Loading the PDF…</div>
      ) : loaded.url ? (
        <iframe
          className="aw-doc-pdf"
          title={`${source.title}, page ${source.page}`}
          src={`${loaded.url}#page=${source.page}&view=FitH`}
        />
      ) : (
        <div className="aw-empty">
          {loaded.failed ? "The PDF couldn't be loaded. Try the PDF button above." : "No stored PDF for this source."}
        </div>
      )}
    </div>
  );
}

function SourceBar({ source, onPdf }: { source: Source; onPdf: (source: Source) => void }) {
  const link = pageLink(source);
  return (
    <div className="aw-panel-bar">
      <span className="aw-tag">{source.pubType}</span>
      {citationYear(source)} · {source.office} · Page {source.printedPage ?? source.page}
      {source.pageCount ? ` of ${source.pageCount}` : ""}
      <span className="spacer" />
      {link && (
        <a className="aw-btn sm link" href={link} target="_blank" rel="noreferrer">
          <Icon name="external" small /> wri.org
        </a>
      )}
      <button className="aw-btn sm link" onClick={() => onPdf(source)}>
        <Icon name="download" small /> PDF
      </button>
    </div>
  );
}

export function SidePanel(props: SidePanelProps) {
  const { turn, tab } = props;
  const sources = turn.answer?.sources ?? [];
  const deep = turn.mode === "deep";
  const openSource = typeof tab === "number" ? sources.find((source) => source.marker === tab) : undefined;
  const markers = sources.map((source) => source.marker);
  const step = (direction: 1 | -1) => {
    if (typeof tab !== "number") return;
    const next = markers[markers.indexOf(tab) + direction];
    if (next !== undefined) props.onMarker(next);
  };

  return (
    <aside className="aw-panel">
      <ResizeHandle width={props.width} onWidth={props.onWidth} />
      <div className="aw-panel-tabs">
        <div className="aw-tablist" role="tablist">
        {deep && (
          <button role="tab" aria-selected={tab === "report"} className={tab === "report" ? "aw-tab on" : "aw-tab"} onClick={() => props.onTab("report")}>
            <Icon name="file" small /> Report
          </button>
        )}
        <button role="tab" aria-selected={tab === "sources"} className={tab === "sources" ? "aw-tab on" : "aw-tab"} onClick={() => props.onTab("sources")}>
          Sources ({sources.length})
        </button>
        {props.openDocs.map((marker) => {
          const source = sources.find((s) => s.marker === marker);
          if (!source) return null;
          return (
            <div key={marker} className={tab === marker ? "aw-tab on" : "aw-tab"}>
              <button role="tab" aria-selected={tab === marker} className="t" title={source.title} onClick={() => props.onTab(marker)}>
                [{marker}] {source.title}
              </button>
              <button className="x" onClick={() => props.onCloseDoc(marker)} aria-label={`Close ${source.title}`}>×</button>
            </div>
          );
        })}
        </div>
        <button className="aw-btn ghost icon aw-panel-close" onClick={props.onClose} title="Close panel">
          <Icon name="close" small label="Close panel" />
        </button>
      </div>

      {tab === "report" && (
        <div className="aw-panel-bar">
          <span className="aw-mode-chip deep"><Icon name="layers" small /> Deep research</span>
          {turn.status === "running" ? "In progress" : turn.answer ? "Ready" : "Ended"}
          <span className="spacer" />
          <label>
            <span className="visually-hidden">Format</span>
            <select className="aw-btn sm" value={props.format} onChange={(event) => props.onFormat(event.target.value as ReportFormat)} disabled={turn.status === "running"}>
              {FORMATS.map((format) => (
                <option key={format.value} value={format.value}>{format.name}</option>
              ))}
            </select>
          </label>
        </div>
      )}
      {openSource && <SourceBar source={openSource} onPdf={props.onPdf} />}

      <div className="aw-panel-body" style={tab === "report" || openSource ? { padding: 0 } : undefined}>
        {tab === "report" && <ReportView {...props} />}
        {tab === "sources" && (
          sources.length === 0 ? (
            <div className="aw-empty">Sources appear here once the answer is ready.</div>
          ) : (
            <ol className="aw-src-rows">
              {sources.map((source) => (
                <li key={source.marker} className="aw-src-row">
                  <button className="aw-src-line" onClick={() => props.onMarker(source.marker)}>
                    <span className="aw-mk">{source.marker}</span>
                    <span className="aw-src-text">
                      <span className="aw-src-title">{source.title}</span>
                      <span className="aw-meta">{sourceMeta(source)}</span>
                    </span>
                  </button>
                </li>
              ))}
            </ol>
          )
        )}
        {openSource && <SourceView source={openSource} pdfUrl={props.pdfUrl} />}
      </div>

      <div className="aw-panel-foot">
        {openSource ? (
          <>
            <button className="aw-btn sm icon" onClick={() => step(-1)} disabled={markers.indexOf(openSource.marker) === 0} title="Previous citation">
              <Icon name="prev" small label="Previous citation" />
            </button>
            <button className="aw-btn sm icon" onClick={() => step(1)} disabled={markers.indexOf(openSource.marker) === markers.length - 1} title="Next citation">
              <Icon name="next" small label="Next citation" />
            </button>
            <span className="spacer" />
            <span className="aw-meta">Source {openSource.marker} of {markers.length}</span>
          </>
        ) : tab === "report" ? (
          <>
            <button className="aw-btn sm" onClick={props.onDownloadReport} disabled={!turn.answer?.report}>
              <Icon name="download" small /> Markdown
            </button>
            <span className="spacer" />
            <span className="aw-meta">Machine-translated versions are labelled</span>
          </>
        ) : (
          <span className="aw-meta">Click a source to open it at the cited page</span>
        )}
      </div>
    </aside>
  );
}
