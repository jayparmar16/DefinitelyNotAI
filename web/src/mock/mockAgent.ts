/**
 * A stand-in for the AskWRI agent so the UI can be built before the backend exists.
 *
 * Routing is by keyword: transport questions get the canned cited answer (Quick answer) or a
 * streamed report (Deep research); anything else gets the helpful decline. "Now in Spanish"
 * after a report reuses it, machine-translated. To remove: delete src/mock/ and switch
 * getAgent() in src/lib/agent.ts to the real client.
 */

import type { AgentClient, AgentEvent, AskRequest, Answer, ReportFormat } from "../lib/agent.ts";
import { QUICK_PARAGRAPHS, REPORT_POINTS, SOURCES, SUB_QUESTIONS, THIN_EVIDENCE } from "./fixtures.ts";

const ON_TOPIC = /\b(bus|buses|transit|transport|electri\w*|mobility|fleets?|brt|briefing|talking points)\b/i;
const SPANISH_FOLLOW_UP = /\b(spanish|español|espanol)\b/i;
const FORMAT_TITLES: Record<ReportFormat, string> = {
  summary: "Researcher summary",
  "issue-brief": "Issue brief",
  "talking-points": "Talking points",
};

// Sessions that already have a report, so a follow-up can reuse the gathered evidence.
const reports = new Set<string>();

function pause(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(resolve, ms);
    signal.addEventListener("abort", () => {
      clearTimeout(timer);
      reject(signal.reason);
    });
  });
}

function quickAnswer(language: string, startedAt: number): Answer {
  const translated = language === "es";
  const paragraphs = translated ? QUICK_PARAGRAPHS.es : QUICK_PARAGRAPHS.en;
  return {
    mode: "quick",
    language,
    machineTranslated: translated,
    paragraphs,
    sources: SOURCES.slice(0, 4),
    claimsTotal: 5,
    claimsVerified: 5,
    elapsedSeconds: Math.round((Date.now() - startedAt) / 1000),
    report: null,
  };
}

function deepAnswer(request: AskRequest, language: string, startedAt: number): Answer {
  const translated = language === "es";
  const keyPoints = translated ? REPORT_POINTS.es : REPORT_POINTS.en;
  return {
    mode: "deep",
    language,
    machineTranslated: translated,
    paragraphs: keyPoints,
    sources: SOURCES,
    claimsTotal: 7,
    claimsVerified: 7,
    elapsedSeconds: Math.round((Date.now() - startedAt) / 1000),
    report: {
      title: `${FORMAT_TITLES[request.format]}: electric buses in Latin America`,
      builtFrom: `Built from ${SOURCES.length} WRI publications, 2006 to 2022`,
      keyPoints,
      thinEvidence: translated ? THIN_EVIDENCE.es : THIN_EVIDENCE.en,
    },
  };
}

async function* quickRun(request: AskRequest, signal: AbortSignal): AsyncGenerator<AgentEvent> {
  const startedAt = Date.now();
  yield { type: "step", id: "search", label: "Searching WRI publications", status: "now" };
  await pause(700, signal);
  yield { type: "step", id: "search", label: "Searched WRI publications", detail: "4 sources", status: "done" };
  yield { type: "step", id: "verify", label: "Verifying 5 claims against passages", status: "now" };
  await pause(600, signal);
  yield { type: "answer", answer: quickAnswer(request.language, startedAt) };
}

async function* deepRun(request: AskRequest, signal: AbortSignal): AsyncGenerator<AgentEvent> {
  const startedAt = Date.now();
  const steps: [string, string, string?][] = [
    ["plan", "Planned 4 sub-questions", SUB_QUESTIONS],
    ["round-1", "Round 1: searched 2015 to 2024", "4 sources"],
    ["round-2", 'Round 2: added pre-2010 terms ("diesel bus fleet", "BRT")', "2 more sources"],
    ["figures", "Checked for revised figures", "1 newer estimate found"],
    ["verify", "Verifying 7 claims against passages"],
    ["draft", `Drafting ${FORMAT_TITLES[request.format].toLowerCase()} for a ${request.audience}`],
  ];
  for (const [id, label] of steps) yield { type: "step", id, label, status: "next" };
  for (const [index, [id, label, detail]] of steps.entries()) {
    yield { type: "step", id, label, status: "now" };
    await pause(900, signal);
    yield { type: "step", id, label, detail, status: "done" };
    if (index === 1) {
      for (const source of SOURCES.slice(0, 4)) {
        yield { type: "source-found", title: source.title, year: source.year };
      }
    }
    if (index === 2) {
      for (const source of SOURCES.slice(5)) yield { type: "source-found", title: source.title, year: source.year };
    }
    if (index === 3) {
      yield { type: "source-found", title: SOURCES[4].title, year: SOURCES[4].year };
      yield {
        type: "outdated-figure",
        text: "A 2022 issue brief revises the fleet cost estimate from the 2019 report. The report uses the 2022 figure and cites both.",
        markers: [5, 1],
      };
    }
  }
  reports.add(request.sessionId);
  yield { type: "answer", answer: deepAnswer(request, request.language, startedAt) };
}

async function* translatedFollowUp(request: AskRequest, signal: AbortSignal): AsyncGenerator<AgentEvent> {
  const startedAt = Date.now();
  yield { type: "step", id: "reuse", label: "Reusing the evidence from your last report", detail: "no new search", status: "done" };
  yield { type: "step", id: "translate", label: "Translating to Spanish; checking every number survived", status: "now" };
  await pause(900, signal);
  yield { type: "step", id: "translate", label: "Translated to Spanish; every number checked", status: "done" };
  yield { type: "answer", answer: deepAnswer(request, "es", startedAt) };
}

async function* declineRun(request: AskRequest, signal: AbortSignal): AsyncGenerator<AgentEvent> {
  const rounds = request.mode === "deep" ? 3 : 2;
  for (let round = 1; round <= rounds; round++) {
    yield { type: "step", id: `round-${round}`, label: `Round ${round}: searching`, status: "now" };
    await pause(600, signal);
    yield { type: "step", id: `round-${round}`, label: `Round ${round}: no passage strong enough`, status: "done" };
  }
  const terms = request.question.toLowerCase().match(/[a-zà-ÿ]{5,}/g)?.slice(0, 3) ?? [];
  const scope = [
    `${rounds} rounds`,
    request.filters.yearFrom ? `${request.filters.yearFrom} to 2024` : "1998 to 2024",
    request.filters.pubType ?? "all types",
  ].join(" · ");
  yield {
    type: "decline",
    decline: {
      message:
        "No WRI publication in the searched collection answers this. Rather than guess, here is what was searched and the closest related WRI work.",
      searched: [...terms, scope],
      related: SOURCES.slice(0, 2).map(({ title, pubType, year, url }) => ({ title, pubType, year, url })),
    },
  };
}

export const mockAgent: AgentClient = {
  ask(request, signal) {
    if (request.mode === "deep" && reports.has(request.sessionId) && SPANISH_FOLLOW_UP.test(request.question)) {
      return translatedFollowUp(request, signal);
    }
    if (!ON_TOPIC.test(request.question)) return declineRun(request, signal);
    return request.mode === "deep" ? deepRun(request, signal) : quickRun(request, signal);
  },

  async sourceDownloadUrl() {
    return null; // no stored PDFs without the backend
  },

  async warmup() {
    // nothing to start: the mock answers at once
  },

  async translate(paragraphs, language) {
    if (language !== "es") return { paragraphs, report: null };
    const canned = new Map(
      [...QUICK_PARAGRAPHS.en.map((text, i) => [text, QUICK_PARAGRAPHS.es[i]] as const),
       ...REPORT_POINTS.en.map((text, i) => [text, REPORT_POINTS.es[i]] as const)],
    );
    return { paragraphs: paragraphs.map((text) => canned.get(text) ?? text), report: null };
  },
};
