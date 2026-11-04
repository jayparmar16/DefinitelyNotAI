"use client";

/** The research lens applied to an answer: one row per paper, one column per aspect. */

import type { LensResult } from "@/lib/agent";
import { MarkedText } from "./MarkedText";

const EMPTY = {
  not_discussed: "Not discussed in this paper",
  unverified: "No verified summary",
} as const;

type LensTableProps = { lens: LensResult; activeMarker: number | null; onMarker: (marker: number) => void };

export function LensTable({ lens, activeMarker, onMarker }: LensTableProps) {
  return (
    <section className="aw-lens" aria-label="Through your lens">
      <h5>
        Through your lens <span>{lens.goal}</span>
      </h5>
      <div className="aw-lens-scroll">
        <table>
          <thead>
            <tr>
              <th scope="col">Paper</th>
              {lens.aspects.map((aspect) => (
                <th key={aspect} scope="col">{aspect}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {lens.rows.map((row) => (
              <tr key={row.docId}>
                <th scope="row">
                  {row.title}
                  <span className="aw-meta">{[row.pubType, row.year].filter(Boolean).join(" · ")}</span>
                </th>
                {row.cells.map((cell, i) => (
                  <td key={i} className={cell.status === "summarised" ? "" : "empty"}>
                    {cell.status === "summarised" ? (
                      <MarkedText text={cell.text} activeMarker={activeMarker} onMarker={onMarker} />
                    ) : (
                      EMPTY[cell.status]
                    )}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
