/**
 * The contract between the UI and the AskWRI agent, and the one place that picks the client.
 *
 * Shapes follow the design doc: the agent returns answer text with [n] markers plus a sources
 * array, and Deep research streams its progress as events so steps and sources show early.
 */

export type Mode = "quick" | "deep";
export type Audience = "researcher" | "policymaker" | "partnerships";
export type ReportFormat = "summary" | "issue-brief" | "talking-points";

export type Filters = {
  yearFrom?: number;
  pubType?: string;
};

export type AskRequest = {
  question: string;
  mode: Mode;
  language: string; // BCP 47 code of the answer language, e.g. "en", "es"
  audience: Audience;
  format: ReportFormat;
  filters: Filters;
  sessionId: string; // AgentCore Memory session, so follow-ups reuse gathered evidence
};

/** One cited passage. `marker` is the [n] used in the answer text. */
export type Source = {
  marker: number;
  chunkId: string;
  docId: string;
  title: string;
  pubType: string; // as WRI names it: Report, Issue brief, Working paper, ...
  year: number | null;
  dateConfidence: "high" | "low" | "undated";
  office: string;
  page: number;
  pageCount: number | null;
  passage: string;
  quotable: boolean; // false: cite the page, never quote the passage verbatim
  url: string | null; // wri.org page; "Open at page" adds #page=N
  doi: string | null;
  authors: string[];
};

export type Report = {
  title: string;
  builtFrom: string; // e.g. "Built from 11 WRI publications, 2008 to 2022"
  keyPoints: string[]; // each with [n] markers
  thinEvidence: string[];
};

export type Answer = {
  mode: Mode;
  language: string;
  machineTranslated: boolean;
  paragraphs: string[]; // every sentence ends with one or more [n] markers
  sources: Source[];
  claimsTotal: number;
  claimsVerified: number;
  elapsedSeconds: number;
  report: Report | null; // Deep research only
};

export type Decline = {
  message: string;
  searched: string[]; // search terms and scope, shown as chips
  related: { title: string; pubType: string; year: number | null; url: string | null }[];
};

export type StepStatus = "done" | "now" | "next";

/** Streamed while the agent works. A run ends with exactly one "answer" or "decline". */
export type AgentEvent =
  | { type: "step"; id: string; label: string; detail?: string; status: StepStatus }
  | { type: "source-found"; title: string; year: number | null }
  | { type: "outdated-figure"; text: string; markers: number[] }
  | { type: "answer"; answer: Answer }
  | { type: "decline"; decline: Decline };

export type AgentClient = {
  /** Streams events for one question; stops early when `signal` aborts (the Stop button). */
  ask(request: AskRequest, signal: AbortSignal): AsyncIterable<AgentEvent>;
  /** A short-lived (5 minute) download link for the stored PDF, or null if there is none. */
  sourceDownloadUrl(docId: string): Promise<string | null>;
  /** Machine translation of answer paragraphs, with numbers checked by the agent. */
  translate(paragraphs: string[], language: string): Promise<string[]>;
};

/** True while the UI runs on the mock agent (no API yet); the header shows a "Mock data" badge. */
export const usingMock = true;

/** The agent client the UI talks to. */
export async function getAgent(): Promise<AgentClient> {
  // shortcut: the mock is the only client until the API (runbook phase 5) exists. To switch,
  // add an HTTP client for the API here, set usingMock to false and delete src/mock/.
  const { mockAgent } = await import("../mock/mockAgent.ts");
  return mockAgent;
}
