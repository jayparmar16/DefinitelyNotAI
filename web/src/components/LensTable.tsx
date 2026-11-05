"use client";

/** The research lens applied to an answer: one row per paper, one column per aspect. */

import type { LensResult } from "@/lib/agent";
import { rowMeta } from "@/lib/matrix";
import { MarkedText } from "./MarkedText";
import { MatrixTable } from "./MatrixTable";

const EMPTY = {
  not_discussed: "Not discussed in this paper",
  unverified: "No verified summary",
} as const;

type LensTableProps = {
  lens: LensResult;
  activeMarker: number | null;
  onMarker: (marker: number) => void;
  matrix?: boolean; // a dossier's evidence matrix rather than the user's lens
};

export function LensTable({ lens, activeMarker, onMarker, matrix }: LensTableProps) {
  const title = matrix ? "Evidence matrix" : "Through your lens";
  return (
    <section className="aw-lens" aria-label={title}>
      <h5>
        {title} <span>{matrix ? `${lens.rows.length} documents` : lens.goal}</span>
      </h5>
      <MatrixTable
        text
        label={title}
        columns={lens.aspects.map((aspect) => ({ label: aspect }))}
        rows={lens.rows.map((row) => ({
          key: row.docId,
          title: row.title,
          meta: rowMeta(row.pubType, row.year),
          cells: row.cells.map((cell) =>
            cell.status === "summarised"
              ? { content: <MarkedText text={cell.text} activeMarker={activeMarker} onMarker={onMarker} /> }
              : { content: EMPTY[cell.status], empty: true },
          ),
        }))}
      />
    </section>
  );
}
