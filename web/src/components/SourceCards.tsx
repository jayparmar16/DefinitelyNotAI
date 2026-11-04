"use client";

/** The sources list under an answer: one card per marker, then the people behind the work. */

import type { Source } from "@/lib/agent";
import { citationYear, pageLink } from "@/lib/citations";
import { Icon } from "./Icon";
import { Menu } from "./Menu";

type SourceCardsProps = {
  turnId: string;
  sources: Source[];
  activeMarker: number | null;
  onOpen: (marker: number) => void;
  onPdf: (source: Source) => void;
  onCite: (source: Source) => void;
  onSources: (format: "csv" | "bibtex") => void;
};

/** DOM id of a source card, so a marker click can scroll to it. */
export function cardId(turnId: string, marker: number): string {
  return `card-${turnId}-${marker}`;
}

export function Passage({ source }: { source: Source }) {
  if (!source.quotable) {
    return (
      <p className="aw-quote">
        <i>Cited by page. This passage was re-ordered in the PDF, so it is not quoted word for word.</i>
      </p>
    );
  }
  return (
    <p className="aw-quote">
      &ldquo;&hellip;<mark>{source.passage}</mark>&hellip;&rdquo;
    </p>
  );
}

export function SourceCards(props: SourceCardsProps) {
  const authors = [...new Set(props.sources.flatMap((source) => source.authors))];
  return (
    <>
      <div className="aw-sources-h">
        <h3>Sources</h3>
        <Menu
          trigger={({ open, toggle }) => (
            <button className="aw-btn sm ghost" onClick={toggle} aria-expanded={open}>
              <Icon name="download" small /> Sources CSV · BibTeX
            </button>
          )}
        >
          {(close) => (
            <>
              <button className="row" role="menuitem" onClick={() => { props.onSources("csv"); close(); }}>
                Sources as CSV
              </button>
              <button className="row" role="menuitem" onClick={() => { props.onSources("bibtex"); close(); }}>
                Sources as BibTeX
              </button>
            </>
          )}
        </Menu>
      </div>

      <div className="aw-cards">
        {props.sources.map((source) => {
          const link = pageLink(source);
          const active = source.marker === props.activeMarker;
          return (
            <div key={source.marker} id={cardId(props.turnId, source.marker)} className={active ? "aw-card active" : "aw-card"}>
              <div className="aw-card-top">
                <button className={active ? "aw-mk active" : "aw-mk"} onClick={() => props.onOpen(source.marker)} aria-label={`Source ${source.marker}`}>
                  {source.marker}
                </button>
                <div>
                  <button className="aw-card-title" onClick={() => props.onOpen(source.marker)}>
                    {source.title}
                  </button>
                  <div className="aw-meta">
                    <span className="aw-tag">{source.pubType}</span>
                    {source.pubType === "Working paper" && " in progress ·"} {citationYear(source)} · {source.office} · p. {source.page}
                  </div>
                </div>
              </div>
              <Passage source={source} />
              <div className="aw-card-btns">
                {link ? (
                  <a className="aw-btn sm link" href={link} target="_blank" rel="noreferrer">
                    <Icon name="external" small /> Open at page
                  </a>
                ) : (
                  <button className="aw-btn sm link" disabled title="No wri.org page for this document">
                    <Icon name="external" small /> Open at page
                  </button>
                )}
                <button className="aw-btn sm" onClick={() => props.onPdf(source)}>
                  <Icon name="download" small /> PDF
                </button>
                <button className="aw-btn sm" onClick={() => props.onCite(source)}>
                  <Icon name="copy" small /> Cite
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {authors.length > 0 && (
        <div>
          <div className="aw-meta" style={{ marginBottom: 8 }}>People who&apos;ve published on this</div>
          <div className="aw-searched">
            {authors.map((author) => (
              <span key={author}>{author}</span>
            ))}
          </div>
        </div>
      )}
    </>
  );
}
