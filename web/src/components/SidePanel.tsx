"use client";

/**
 * The resizable, closable side panel: the Deep research report, the sources list, and one
 * tab per opened source showing the cited page with the passage highlighted.
 */

import { type PointerEvent as ReactPointerEvent, useState } from "react";

import type { Audience, ReportFormat, Source } from "@/lib/agent";
import { citationYear, pageLink } from "@/lib/citations";
import { Icon } from "./Icon";
import { MarkedText } from "./MarkedText";
import { Passage } from "./SourceCards";
import type { Turn } from "./turn";

export type PanelTab = "report" | "sources" | number; // a number is an open source's marker

const FORMATS: { value: ReportFormat; name: string }[] = [
  { value: "talking-points", name: "Talking points" },
  { value: "issue-brief", name: "Issue brief" },
  { value: "summary", name: "Researcher summary" },
];
const AUDIENCE_NAMES: Record<Audience, string> = {
  researcher: "a researcher",
  policymaker: "a policymaker",
  partnerships: "partnerships staff",
};
const MIN_WIDTH = 360;
const MAX_WIDTH = 760;

type SidePanelProps = {
  turn: Turn;
  tab: PanelTab;
  openDocs: number[];
  activeMarker: number | null;
  width: number;
  audience: Audience;
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
        <div className="aw-meta">Briefing · for {AUDIENCE_NAMES[props.audience]} · {props.languageName}</div>
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
  const authors = [...new Set(turn.answer!.sources.flatMap((source) => source.authors))];
  const shown = turn.translation && !turn.translation.showOriginal ? turn.translation : null;
  const translation = shown ? shown.paragraphs : null;
  const translatedReport = shown?.report ?? null;
  return (
    <div className="aw-report">
      <div className="aw-meta">
        Briefing · for {AUDIENCE_NAMES[props.audience]} · {props.languageName}
        {(turn.answer!.machineTranslated || translation) && <> · <span className="aw-mt">Machine-translated</span></>}
      </div>
      <h2>{translatedReport?.title ?? report.title}</h2>
      <div className="aw-meta">{report.builtFrom}</div>
      <h4>Key points</h4>
      <ul>
        {(translation ?? report.keyPoints).map((point, index) => (
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
        {(translatedReport?.thinEvidence ?? report.thinEvidence).map((point) => (
          <li key={point}>{point}</li>
        ))}
      </ul>
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

function SourceView({ source }: { source: Source }) {
  // shortcut: a page preview drawn from the passage. The real viewer renders the stored PDF with
  // PDF.js over the presigned URL (design doc, source viewer), once the API serves downloads.
  return (
    <div className="aw-pdf">
      <div className="pg">
        <span>{source.title}</span>
        <span>{source.page}</span>
      </div>
      <div className="aw-bar dark" style={{ width: "60%" }} />
      <div className="aw-bar" /><div className="aw-bar" style={{ width: "94%" }} /><div className="aw-bar" style={{ width: "88%" }} />
      {source.quotable ? (
        <div className="aw-hl">&hellip;<b>{source.passage}</b>&hellip;</div>
      ) : (
        <Passage source={source} />
      )}
      <div className="aw-bar" /><div className="aw-bar" style={{ width: "90%" }} /><div className="aw-bar" style={{ width: "96%" }} />
      <div className="aw-bar dark" style={{ width: "40%", marginTop: 8 }} />
      <div className="aw-bar" /><div className="aw-bar" style={{ width: "85%" }} /><div className="aw-bar" style={{ width: "70%" }} />
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

      <div className="aw-panel-body" style={tab === "report" ? { padding: 0 } : undefined}>
        {tab === "report" && <ReportView {...props} />}
        {tab === "sources" && (
          sources.length === 0 ? (
            <div className="aw-empty">Sources appear here once the answer is ready.</div>
          ) : (
            <div className="aw-src-list">
              {sources.map((source) => (
                <div key={source.marker} className="aw-card">
                  <div className="aw-card-top">
                    <button className="aw-mk" onClick={() => props.onMarker(source.marker)} aria-label={`Source ${source.marker}`}>{source.marker}</button>
                    <div>
                      <button className="aw-card-title" onClick={() => props.onMarker(source.marker)}>{source.title}</button>
                      <div className="aw-meta"><span className="aw-tag">{source.pubType}</span> {citationYear(source)} · {source.office} · p. {source.page}</div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )
        )}
        {openSource && <SourceView source={openSource} />}
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
            <span className="aw-meta">Page preview (mock); the PDF viewer needs stored PDFs</span>
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
