"use client";

/**
 * The sources under an answer: a one-line summary that expands into slim rows, one per marker.
 * A row expands to its passage and actions; clicking a [n] marker opens the list at that row.
 */

import { useEffect, useState } from "react";

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

/** DOM id of a source row, so a marker click can scroll to it. */
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

/** "Type · year · office · p. 12", shared by the rows and the side panel. */
export function sourceMeta(source: Source): string {
  const progress = source.pubType === "Working paper" ? " (in progress)" : "";
  const cited = source.citedBy ? ` · cited by ${source.citedBy} in AskWRI` : "";
  return `${source.pubType}${progress} · ${citationYear(source)} · ${source.office} · p. ${source.printedPage ?? source.page}${cited}`;
}

export function SourceCards(props: SourceCardsProps) {
  const [listOpen, setListOpen] = useState(false);
  const [openRows, setOpenRows] = useState<number[]>([]);
  const { activeMarker } = props;
  const documents = new Set(props.sources.map((source) => source.docId)).size;
  const authors = [...new Set(props.sources.flatMap((source) => source.authors))];

  // A marker clicked in the answer opens the list at its row (the panel opens the page).
  useEffect(() => {
    if (activeMarker === null) return;
    setListOpen(true);
    setOpenRows((rows) => (rows.includes(activeMarker) ? rows : [...rows, activeMarker]));
  }, [activeMarker]);

  const toggleRow = (marker: number) =>
    setOpenRows((rows) => (rows.includes(marker) ? rows.filter((m) => m !== marker) : [...rows, marker]));

  return (
    <section className="aw-srcs" aria-label="Sources">
      <div className="aw-srcs-h">
        <button className="aw-srcs-toggle" onClick={() => setListOpen(!listOpen)} aria-expanded={listOpen}>
          <span className={listOpen ? "aw-caret open" : "aw-caret"}><Icon name="chevron" small /></span>
          <b>Sources</b>
          <span className="aw-meta">
            {props.sources.length} passage{props.sources.length === 1 ? "" : "s"} from {documents} publication{documents === 1 ? "" : "s"}
          </span>
        </button>
        {!listOpen && (
          <span className="aw-srcs-peek" aria-hidden>
            {props.sources.map((source) => (
              <span key={source.marker} className="aw-mk">{source.marker}</span>
            ))}
          </span>
        )}
        <span className="spacer" />
        <Menu
          trigger={({ open, toggle }) => (
            <button className="aw-btn sm ghost icon" onClick={toggle} aria-expanded={open} title="Export sources">
              <Icon name="download" small label="Export sources" />
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

      {listOpen && (
        <ol className="aw-src-rows">
          {props.sources.map((source) => {
            const link = pageLink(source);
            const active = source.marker === activeMarker;
            const open = openRows.includes(source.marker);
            return (
              <li key={source.marker} id={cardId(props.turnId, source.marker)} className={active ? "aw-src-row active" : "aw-src-row"}>
                <button className="aw-src-line" onClick={() => toggleRow(source.marker)} aria-expanded={open}>
                  <span className={active ? "aw-mk active" : "aw-mk"}>{source.marker}</span>
                  <span className="aw-src-text">
                    <span className="aw-src-title">{source.title}</span>
                    <span className="aw-meta">{sourceMeta(source)}</span>
                  </span>
                  <span className={open ? "aw-caret open" : "aw-caret"}><Icon name="chevron" small /></span>
                </button>
                {open && (
                  <div className="aw-src-more">
                    <Passage source={source} />
                    <div className="aw-card-btns">
                      <button className="aw-btn sm" onClick={() => props.onOpen(source.marker)}>
                        <Icon name="file" small /> View page
                      </button>
                      {link && (
                        <a className="aw-btn sm link" href={link} target="_blank" rel="noreferrer">
                          <Icon name="external" small /> wri.org
                        </a>
                      )}
                      <button className="aw-btn sm" onClick={() => props.onPdf(source)}>
                        <Icon name="download" small /> PDF
                      </button>
                      <button className="aw-btn sm" onClick={() => props.onCite(source)}>
                        <Icon name="copy" small /> Cite
                      </button>
                    </div>
                  </div>
                )}
              </li>
            );
          })}
        </ol>
      )}

      {listOpen && authors.length > 0 && (
        <div className="aw-meta aw-src-people">
          <Icon name="person" small /> People who&apos;ve published on this: {authors.join(", ")}
        </div>
      )}
    </section>
  );
}
