"use client";

/**
 * The one matrix layout every view uses (evidence matrix, research lens, topic dossier): a
 * publication per row, a short heading per column, sized to fit in one view.
 */

import type { ReactNode } from "react";

export type MatrixTableProps = {
  label: string;
  text?: boolean; // cells hold sentences (lens, dossier): readable widths, scrolling sideways
  columns: { label: string; title?: string }[];
  rows: { key: string; title: string; meta: string; cells: { content: ReactNode; empty?: boolean; tick?: boolean }[] }[];
};

export function MatrixTable({ label, columns, rows, text }: MatrixTableProps) {
  return (
    <div className={text ? "aw-matrix text" : "aw-matrix"} role="region" aria-label={label}>
      <table>
        <thead>
          <tr>
            <th scope="col">Publication</th>
            {columns.map((column, i) => (
              <th key={i} scope="col" title={column.title ?? column.label}>{column.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.key}>
              <th scope="row" title={row.title}>
                <span className="aw-matrix-title">{row.title}</span>
                <span className="aw-meta">{row.meta}</span>
              </th>
              {row.cells.map((cell, i) => (
                <td key={i} className={[cell.tick && "tick", cell.empty && "empty"].filter(Boolean).join(" ") || undefined}>{cell.content}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
