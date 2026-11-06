/** Answer text with its [n] markers as buttons that jump to the source card. */

import { splitMarkers } from "@/lib/citations";

type MarkedTextProps = {
  text: string;
  activeMarker: number | null;
  onMarker: (marker: number) => void;
};

export function MarkedText({ text, activeMarker, onMarker }: MarkedTextProps) {
  return (
    <>
      {splitMarkers(text).map((segment, index) =>
        segment.kind === "text" ? (
          <span key={index}>{segment.text}</span>
        ) : (
          <button
            key={index}
            className={segment.marker === activeMarker ? "aw-mk active" : "aw-mk"}
            onClick={() => onMarker(segment.marker)}
            aria-label={`Source ${segment.marker}`}
          >
            {segment.marker}
          </button>
        ),
      )}
    </>
  );
}
