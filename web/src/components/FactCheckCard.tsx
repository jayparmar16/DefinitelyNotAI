"use client";

/**
 * A fact-checked draft: the draft with each claim coloured by its verdict, then one row per claim
 * with the verdict, a suggested correction in WRI's words, and the sources behind it.
 */

import { useState } from "react";

import type { FactCheck } from "@/lib/agent";
import { VERDICT_NAMES, annotate, countsLine } from "@/lib/factcheck";
import { Icon } from "./Icon";
import { MarkedText } from "./MarkedText";

type FactCheckCardProps = {
  turnId: string;
  check: FactCheck;
  activeMarker: number | null;
  onMarker: (marker: number) => void;
  onCopy: () => void;
};

function rowId(turnId: string, index: number): string {
  return `claim-${turnId}-${index}`;
}

export function FactCheckCard({ turnId, check, activeMarker, onMarker, onCopy }: FactCheckCardProps) {
  const [active, setActive] = useState<number | null>(null);
  const focus = (index: number) => {
    setActive(index);
    document.getElementById(rowId(turnId, index))?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  };

  return (
    <div className="aw-answer aw-fc">
      <div className="aw-answer-meta">
        <span className="aw-mode-chip"><Icon name="check" small /> Fact-check</span>
        <span>{countsLine(check)} · {check.elapsedSeconds} s</span>
      </div>

      {check.claims.length === 0 ? (
        <p>No checkable claims were found in this text: no figures, findings or statements about WRI&apos;s work.</p>
      ) : (
        <>
          <div className="aw-fc-draft" aria-label="Your draft, with each claim marked">
            {annotate(check.draft, check.claims).map((segment, i) =>
              segment.claim === null ? (
                <span key={i}>{segment.text}</span>
              ) : (
                // A span, not a button, so a claim flows with the draft's text like a highlighter.
                <span
                  key={i}
                  role="button"
                  tabIndex={0}
                  className={`aw-fc-quote ${check.claims[segment.claim].verdict}${active === segment.claim ? " on" : ""}`}
                  onClick={() => focus(segment.claim!)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      focus(segment.claim!);
                    }
                  }}
                  title={VERDICT_NAMES[check.claims[segment.claim].verdict]}
                >
                  {segment.text}
                </span>
              ),
            )}
          </div>

          <ol className="aw-fc-rows">
            {check.claims.map((claim, index) => (
              <li
                key={index}
                id={rowId(turnId, index)}
                className={active === index ? "aw-fc-row on" : "aw-fc-row"}
                onMouseEnter={() => setActive(index)}
              >
                <span className={`aw-verdict ${claim.verdict}`}>{VERDICT_NAMES[claim.verdict]}</span>
                <div className="aw-fc-body">
                  <div className="aw-fc-claim">
                    {claim.claim}{" "}
                    {claim.markers.map((marker) => (
                      <button
                        key={marker}
                        className={marker === activeMarker ? "aw-mk active" : "aw-mk"}
                        onClick={() => onMarker(marker)}
                        aria-label={`Source ${marker}`}
                      >
                        {marker}
                      </button>
                    ))}
                  </div>
                  {claim.correction && (
                    <div className="aw-fc-fix">
                      <b>Suggested wording:</b> {claim.correction}
                    </div>
                  )}
                  {claim.note && (
                    <div className="aw-meta">
                      <MarkedText text={claim.note} activeMarker={activeMarker} onMarker={onMarker} />
                    </div>
                  )}
                </div>
              </li>
            ))}
          </ol>
        </>
      )}

      <div className="aw-actions">
        <button className="aw-btn sm" onClick={onCopy}>
          <Icon name="copy" small /> Copy report
        </button>
        <span className="aw-meta">Checked only against WRI publications indexed in AskWRI.</span>
      </div>
    </div>
  );
}
