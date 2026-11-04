/**
 * The contract between the UI and the AskWRI agent, and the one place that picks the client.
 *
 * Shapes follow the design doc: the agent returns answer text with [n] markers plus a sources
 * array, and Deep research streams its progress as events so steps and sources show early.
 */

export type Mode = "quick" | "deep" | "factcheck";
/** Who an answer is written for. */
export type Reader = "researcher" | "policymaker" | "partnerships";
/** "auto": nobody picks a persona when typing, so the agent infers the reader from the question. */
export type Audience = "auto" | Reader;
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
  page: number; // PDF page: opens the PDF there
  printedPage?: string | null; // the number printed on the page, for display
  pageCount: number | null;
  passage: string;
  quotable: boolean; // false: cite the page, never quote the passage verbatim
  url: string | null; // wri.org page; "Open at page" adds #page=N
  doi: string | null;
  authors: string[];
  pdfKey?: string | null; // stored copy in the corpus bucket, for the download link
  why?: {
    by_meaning: boolean;
    by_keyword: boolean;
    matched_terms: string[];
    date_source: string;
    label_source: string;
    type_weight?: number; // ranking weight from the publication type: above 1 lifts, below 1 lowers
  } | null;
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
  // Optional so older agents and the mock still fit; the AskWRI agent always sends them.
  audience?: Reader; // the reader the answer was written for (inferred when "auto")
  scope?: string; // e.g. "Based on 2 of the 5 WRI publications indexed in AskWRI"
  implications?: string[]; // AskWRI's interpretation, uncited, never new facts or numbers
  limits?: string[]; // what the question asks that the evidence doesn't cover (Quick answer)
  questions?: string[]; // follow-ups the user could ask next
  removedClaims?: string[]; // drafted claims verification removed
};

export type Decline = {
  message: string;
  searched: string[]; // search terms and scope, shown as chips
  related: { title: string; pubType: string; year: number | null; url: string | null }[];
};

export type Verdict = "supported" | "contradicted" | "outdated" | "not_found";

/** One claim from a fact-checked draft. `quote` is its exact wording in the draft. */
export type CheckedClaim = {
  quote: string;
  claim: string;
  verdict: Verdict;
  markers: number[]; // [n] into the fact-check's sources
  correction: string; // for contradicted or outdated: the claim as WRI's passages support it
  note: string; // why, with [n] markers
};

export type FactCheck = {
  draft: string;
  claims: CheckedClaim[];
  counts: Record<Verdict, number>;
  sources: Source[];
  elapsedSeconds: number;
};

export type StepStatus = "done" | "now" | "next";

/** Streamed while the agent works. A run ends with exactly one "answer" or "decline". */
export type AgentEvent =
  | { type: "step"; id: string; label: string; detail?: string; status: StepStatus }
  | { type: "source-found"; title: string; year: number | null }
  | { type: "outdated-figure"; text: string; markers: number[] }
  | { type: "answer"; answer: Answer }
  | { type: "factcheck"; factcheck: FactCheck }
  | { type: "decline"; decline: Decline };

/** A translated answer: every text the reader sees, in the target language. */
export type Translation = Pick<Answer, "paragraphs" | "report" | "implications" | "limits" | "questions">;

export type AgentClient = {
  /** Streams events for one question; stops early when `signal` aborts (the Stop button). */
  ask(request: AskRequest, signal: AbortSignal): AsyncIterable<AgentEvent>;
  /** A short-lived (5 minute) download link for the stored PDF, or null if there is none. */
  sourceDownloadUrl(source: Source): Promise<string | null>;
  /** The session's last answer machine-translated, with numbers checked by the agent. */
  translate(paragraphs: string[], language: string, sessionId: string): Promise<Translation>;
  /** Start the session's agent while the user is still typing, so the first answer is faster. */
  warmup(sessionId: string): Promise<void>;
};

const apiUrl = process.env.NEXT_PUBLIC_ASKWRI_API_URL;

/** True when no API URL is set, so the UI runs on the mock agent and shows a "Mock data" badge. */
export const usingMock = !apiUrl;

/**
 * The agent client the UI talks to: the AskWRI API when NEXT_PUBLIC_ASKWRI_API_URL is set,
 * otherwise the mock in src/mock/ (delete that folder once the mock is no longer wanted).
 */
export async function getAgent(): Promise<AgentClient> {
  if (apiUrl) {
    const { httpAgent } = await import("./httpAgent.ts");
    return httpAgent(apiUrl, process.env.NEXT_PUBLIC_ASKWRI_API_KEY ?? "");
  }
  const { mockAgent } = await import("../mock/mockAgent.ts");
  return mockAgent;
}
