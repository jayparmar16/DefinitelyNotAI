/** Downloads built in the browser: answer or report as Markdown, sources as CSV or BibTeX. */

import type { Answer, LensResult, Source } from "./agent.ts";
import { citationYear, pageLink } from "./citations.ts";

/** One reference line: title, WRI, year, URL, DOI when present (the "Cite" button). */
export function formatCitation(source: Source): string {
  const parts = [source.title, "World Resources Institute", citationYear(source)];
  if (source.url) parts.push(source.url);
  if (source.doi) parts.push(`https://doi.org/${source.doi}`);
  return `${parts.join(". ")}.`;
}

function sourcesMarkdown(sources: Source[]): string {
  return sources
    .map((source) => {
      const link = pageLink(source);
      const title = link ? `[${source.title}](${link})` : source.title;
      const quote = source.quotable ? ` "${source.passage}"` : "";
      return `[${source.marker}] ${title}. ${source.pubType}, ${citationYear(source)}, ${source.office}, p. ${source.page}.${quote}`;
    })
    .join("\n");
}

/** The answer (and report, in Deep research) with markers kept and the full sources list. */
export function answerMarkdown(question: string, answer: Answer): string {
  const lines = [`# ${answer.report?.title ?? question}`, ""];
  if (answer.machineTranslated) lines.push("_Machine-translated._", "");
  if (answer.scope) lines.push(`_${answer.scope}._`, "");
  if (answer.summary?.length) lines.push("## Summary", "", ...answer.summary.flatMap((text) => [text, ""]));
  if (answer.report) {
    lines.push(answer.report.builtFrom, "", "## Key points", "");
    lines.push(...answer.report.keyPoints.map((point) => `- ${point}`), "");
    lines.push("## Where the evidence is thin", "");
    lines.push(...answer.report.thinEvidence.map((point) => `- ${point}`), "");
  } else {
    lines.push(...answer.paragraphs.flatMap((paragraph) => [paragraph, ""]));
  }
  if (answer.lens) {
    lines.push(`## ${answer.dossier ? "Evidence matrix" : `Through your lens: ${answer.lens.goal}`}`, "");
    lines.push(`| Paper | ${answer.lens.aspects.join(" | ")} |`, `|---|${answer.lens.aspects.map(() => "---").join("|")}|`);
    for (const row of answer.lens.rows) {
      const cells = row.cells.map((cell) => (cell.status === "summarised" ? cell.text : "Not discussed").replaceAll("|", "/"));
      lines.push(`| ${row.title} | ${cells.join(" | ")} |`);
    }
    lines.push("");
  }
  const sections: [string, string[] | undefined][] = [
    ["Where the papers agree", answer.dossier?.agree],
    ["Where they differ", answer.dossier?.differ],
    ["What none of them covers", answer.dossier?.missing],
    ["Possible implications (AskWRI's interpretation, not WRI findings)", answer.implications],
    ["What this can't tell you", answer.report ? [] : answer.limits],
    ["Questions to explore", answer.questions],
  ];
  for (const [heading, items] of sections) {
    if (items?.length) lines.push(`## ${heading}`, "", ...items.map((item) => `- ${item}`), "");
  }
  lines.push("## Sources", "", sourcesMarkdown(answer.sources), "");
  return lines.join("\n");
}

/** The lens or evidence matrix as CSV: one row per paper, one column per aspect. */
export function matrixCsv(lens: LensResult): string {
  const header = ["paper", "type", "year", ...lens.aspects];
  const rows = lens.rows.map((row) =>
    [row.title, row.pubType, row.year, ...row.cells.map((cell) => (cell.status === "summarised" ? cell.text : ""))]
      .map(csvCell)
      .join(","),
  );
  return [header.map(csvCell).join(","), ...rows].join("\n") + "\n";
}

function csvCell(value: string | number | null): string {
  const text = value === null ? "" : String(value);
  return /[",\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

/** One row per source, for spreadsheets and reference managers. */
export function sourcesCsv(sources: Source[]): string {
  const header = ["marker", "title", "type", "year", "office", "page", "url", "doi", "authors"];
  const rows = sources.map((s) =>
    [s.marker, s.title, s.pubType, s.year, s.office, s.page, s.url, s.doi, s.authors.join("; ")]
      .map(csvCell)
      .join(","),
  );
  return [header.join(","), ...rows].join("\n") + "\n";
}

function bibtexKey(source: Source): string {
  const word = source.title.toLowerCase().match(/[a-z]+/)?.[0] ?? "wri";
  return `wri${source.year ?? "nd"}${word}${source.marker}`;
}

/** BibTeX @techreport entries; braces in titles are dropped so entries always parse. */
export function sourcesBibtex(sources: Source[]): string {
  return sources
    .map((source) => {
      const fields: [string, string][] = [
        ["title", source.title.replace(/[{}]/g, "")],
        ["institution", "World Resources Institute"],
        ["type", source.pubType],
      ];
      if (source.year !== null) fields.push(["year", String(source.year)]);
      if (source.authors.length) fields.push(["author", source.authors.join(" and ")]);
      if (source.url) fields.push(["url", source.url]);
      if (source.doi) fields.push(["doi", source.doi]);
      const body = fields.map(([key, value]) => `  ${key} = {${value}}`).join(",\n");
      return `@techreport{${bibtexKey(source)},\n${body}\n}`;
    })
    .join("\n\n")
    .concat("\n");
}

/** Save text as a file through the browser's download. */
export function saveFile(name: string, text: string, type: string): void {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const link = Object.assign(document.createElement("a"), { href: url, download: name });
  link.click();
  URL.revokeObjectURL(url);
}
