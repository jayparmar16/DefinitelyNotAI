"use client";

/** The summary every mode opens with: a cited synthesis across the publications it used. */

import { splitMarkers } from "@/lib/citations";
import { MarkedText } from "./MarkedText";

type SummaryProps = {
  texts: string[] | undefined;
  activeMarker: number | null;
  onMarker: (marker: number) => void;
};

export function Summary({ texts, activeMarker, onMarker }: SummaryProps) {
  if (!texts?.length) return null;
  const cited = new Set(texts.flatMap((text) => splitMarkers(text).flatMap((s) => (s.kind === "text" ? [] : [s.marker]))));
  return (
    <section className="aw-summary" aria-label="Summary">
      <div className="aw-summary-h">
        Summary
        <span className="aw-meta">from {cited.size} cited source{cited.size === 1 ? "" : "s"} · every claim checked</span>
      </div>
      {texts.map((text, index) => (
        <p key={index}>
          <MarkedText text={text} activeMarker={activeMarker} onMarker={onMarker} />
        </p>
      ))}
    </section>
  );
}
