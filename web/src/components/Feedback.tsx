/** The two feedback states: the outdated-figure flag and the helpful decline. */

import type { Decline } from "@/lib/agent";
import { Icon } from "./Icon";
import { MarkedText } from "./MarkedText";

type OutdatedFlagProps = {
  text: string;
  markers: number[];
  activeMarker: number | null;
  onMarker: (marker: number) => void;
};

export function OutdatedFlag({ text, markers, activeMarker, onMarker }: OutdatedFlagProps) {
  return (
    <div className="aw-flag" role="note">
      <Icon name="warning" />
      <div>
        <b>Newer figure available</b>
        <MarkedText text={`${text} ${markers.map((m) => `[${m}]`).join("")}`} activeMarker={activeMarker} onMarker={onMarker} />
      </div>
    </div>
  );
}

type DeclineCardProps = {
  decline: Decline;
  onRephrase: () => void;
  onCopySearched: () => void;
};

/** Never shown next to a generated answer: a decline replaces the answer entirely. */
export function DeclineCard({ decline, onRephrase, onCopySearched }: DeclineCardProps) {
  return (
    <div className="aw-decline">
      <div className="aw-decline-h">
        <Icon name="info" /> I couldn&apos;t find WRI evidence that answers this
      </div>
      <p style={{ margin: 0 }}>{decline.message}</p>
      <div>
        <div className="aw-meta" style={{ marginBottom: 8 }}>Searched</div>
        <div className="aw-searched">
          {decline.searched.map((term) => (
            <span key={term}>{term}</span>
          ))}
        </div>
      </div>
      {decline.related.length > 0 && (
        <div className="aw-related">
          <div className="aw-meta">Closest related WRI work</div>
          {decline.related.map((item) => {
            const label = `${item.title} · ${item.pubType} · ${item.year ?? "n.d."} →`;
            return item.url ? (
              <a key={item.title} href={item.url} target="_blank" rel="noreferrer">{label}</a>
            ) : (
              <span key={item.title} className="title">{label}</span>
            );
          })}
        </div>
      )}
      <div className="aw-actions">
        <button className="aw-btn sm" onClick={onRephrase}>Rephrase</button>
        {/* "Try Deep research" is a backlog item in the design doc; its slot stays empty for now. */}
        <button className="aw-btn sm" onClick={onCopySearched}>
          <Icon name="copy" small /> Copy what was searched
        </button>
      </div>
    </div>
  );
}
