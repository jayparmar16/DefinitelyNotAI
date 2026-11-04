/** Downloads built in the browser: answer or report as Markdown, sources as CSV or BibTeX. */

import type { Answer, Source } from "./agent.ts";
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
  if (answer.report) {
    lines.push(answer.report.builtFrom, "", "## Key points", "");
    lines.push(...answer.report.keyPoints.map((point) => `- ${point}`), "");
    lines.push("## Where the evidence is thin", "");
    lines.push(...answer.report.thinEvidence.map((point) => `- ${point}`), "");
  } else {
    lines.push(...answer.paragraphs.flatMap((paragraph) => [paragraph, ""]));
  }
  lines.push("## Sources", "", sourcesMarkdown(answer.sources), "");
  return lines.join("\n");
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
