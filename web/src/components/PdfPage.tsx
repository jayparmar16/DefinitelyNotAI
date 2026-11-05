"use client";

/**
 * One page of a stored PDF, drawn with PDF.js, with the cited passage highlighted in the page's
 * text layer and scrolled into view. The browser's own PDF viewer can't be highlighted from our
 * page (it is a separate document), so we draw the page ourselves.
 */

import { useEffect, useRef, useState } from "react";

import { highlightRanges } from "@/lib/highlight";

type PdfJs = typeof import("pdfjs-dist");
type PdfDocument = Awaited<ReturnType<PdfJs["getDocument"]>["promise"]>;

let pdfjs: Promise<PdfJs> | null = null;
const documents = new Map<string, Promise<PdfDocument>>(); // by stored PDF key: one download per document

function loadPdfJs(): Promise<PdfJs> {
  pdfjs ??= import("pdfjs-dist").then((module) => {
    module.GlobalWorkerOptions.workerSrc = new URL("pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url).toString();
    return module;
  });
  return pdfjs;
}

function loadDocument(key: string, url: string): Promise<PdfDocument> {
  let document = documents.get(key);
  if (!document) {
    // The whole file is fetched once (presigned links expire after 5 minutes), then kept.
    document = Promise.all([loadPdfJs(), fetch(url)]).then(async ([lib, response]) => {
      if (!response.ok) throw new Error(`PDF download failed (${response.status})`);
      return lib.getDocument({ data: new Uint8Array(await response.arrayBuffer()) }).promise;
    });
    document.catch(() => documents.delete(key)); // a failed download can be retried
    documents.set(key, document);
  }
  return document;
}

/** Wrap [start, end) of a text layer span's text in <mark class="cite-highlight">. */
function markSpan(span: HTMLElement, start: number, end: number): HTMLElement {
  const text = span.textContent ?? "";
  const mark = document.createElement("mark");
  mark.className = "cite-highlight";
  mark.textContent = text.slice(start, end);
  span.replaceChildren(text.slice(0, start), mark, text.slice(end));
  return mark;
}

type PdfPageProps = { pdfKey: string; url: string; page: number; passage: string; title: string };
type Status = "loading" | "highlighted" | "not-found" | "failed";

export function PdfPage({ pdfKey, url, page, passage, title }: PdfPageProps) {
  const holder = useRef<HTMLDivElement>(null);
  const [status, setStatus] = useState<Status>("loading");
  const [pageCount, setPageCount] = useState<number | null>(null);

  useEffect(() => {
    const box = holder.current;
    if (!box) return;
    let cancelled = false;
    setStatus("loading");
    (async () => {
      const lib = await loadPdfJs();
      const pdf = await loadDocument(pdfKey, url);
      if (cancelled) return;
      setPageCount(pdf.numPages);
      const pdfPage = await pdf.getPage(Math.min(Math.max(page, 1), pdf.numPages));
      const width = box.clientWidth || 480;
      const viewport = pdfPage.getViewport({ scale: width / pdfPage.getViewport({ scale: 1 }).width });

      const sheet = document.createElement("div");
      sheet.className = "aw-pdfpage";
      sheet.style.setProperty("--total-scale-factor", String(viewport.scale));
      sheet.style.width = `${viewport.width}px`;
      sheet.style.height = `${viewport.height}px`;
      const canvas = document.createElement("canvas");
      const ratio = window.devicePixelRatio || 1;
      canvas.width = Math.floor(viewport.width * ratio);
      canvas.height = Math.floor(viewport.height * ratio);
      const layer = document.createElement("div");
      layer.className = "textLayer";
      sheet.append(canvas, layer);
      box.replaceChildren(sheet);

      await pdfPage.render({
        canvas,
        viewport,
        transform: ratio === 1 ? undefined : [ratio, 0, 0, ratio, 0, 0],
      }).promise;
      const textLayer = new lib.TextLayer({ textContentSource: pdfPage.streamTextContent(), container: layer, viewport });
      await textLayer.render();
      if (cancelled) return;

      const spans = textLayer.textDivs;
      const ranges = highlightRanges(spans.map((span) => span.textContent ?? ""), passage);
      const marks = ranges.map((range) => markSpan(spans[range.span], range.start, range.end));
      marks[0]?.scrollIntoView({ block: "center", behavior: "smooth" });
      setStatus(marks.length ? "highlighted" : "not-found");
    })().catch((error) => {
      console.warn(error);
      if (!cancelled) setStatus("failed");
    });
    return () => {
      cancelled = true;
    };
  }, [pdfKey, url, page, passage]);

  return (
    <div className="aw-pdfview">
      <div className="aw-pdfview-bar" role="status">
        <span>
          {status === "loading" && "Loading the page…"}
          {status === "highlighted" && <><span className="aw-swatch" /> Cited text highlighted on page {page}{pageCount ? ` of ${pageCount}` : ""}</>}
          {status === "not-found" && `Page ${page}: the exact wording couldn't be matched on this page (tables and figures often differ)`}
          {status === "failed" && "The page couldn't be drawn here."}
        </span>
        <a className="aw-btn sm link" href={`${url}#page=${page}`} target="_blank" rel="noreferrer">
          Open full PDF
        </a>
      </div>
      <div className="aw-pdfview-page" ref={holder} aria-label={`${title}, page ${page}`} />
    </div>
  );
}
