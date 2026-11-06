/** One question and everything the agent streamed back for it, as the UI keeps it. */

import type { AgentEvent, Answer, Decline, FactCheck, Filters, Mode, ReportFormat, Source, StepStatus, Translation, Visuals } from "@/lib/agent";

export type Step = { id: string; label: string; detail?: string; status: StepStatus };

export type Turn = {
  space?: string | null; // the topic space it was asked in (null or absent: all of WRI)
  format?: ReportFormat; // Deep research: the report type it was written as
  filters?: Filters; // the year, type and region filters it was asked with
  id: string;
  question: string;
  mode: Mode;
  status: "running" | "done" | "stopped" | "failed";
  startedAt: number;
  steps: Step[];
  found: { title: string; year: number | null }[];
  outdated: { text: string; markers: number[] }[];
  answer: Answer | null;
  factcheck?: FactCheck | null; // a fact-checked draft instead of an answer
  visuals?: Visuals | null; // infographics: asked for on an answer, or an Explore result
  visualsLoading?: boolean;
  exploreSources?: Source[]; // Explore: the topic's best publications
  exploreSummary?: string[]; // Explore: a cited synthesis of those publications
  decline: Decline | null;
  error: string | null;
  translation: (Translation & { language: string; showOriginal: boolean }) | null;
};

/** The answer as the reader sees it: the translation's texts when it is shown, else the original. */
export function shownAnswer(turn: Turn): Answer | null {
  const { answer, translation } = turn;
  if (!answer || !translation || translation.showOriginal) return answer;
  const { language: _language, showOriginal: _showOriginal, ...texts } = translation;
  return { ...answer, ...texts, report: texts.report ?? answer.report };
}

export function newTurn(id: string, question: string, mode: Mode): Turn {
  return {
    id,
    question,
    mode,
    status: "running",
    startedAt: Date.now(),
    steps: [],
    found: [],
    outdated: [],
    answer: null,
    decline: null,
    error: null,
    translation: null,
  };
}

/** Apply one streamed event to a turn. A repeated step id updates that step in place. */
export function applyEvent(turn: Turn, event: AgentEvent): Turn {
  switch (event.type) {
    case "step": {
      const step = { id: event.id, label: event.label, detail: event.detail, status: event.status };
      const index = turn.steps.findIndex((existing) => existing.id === event.id);
      const steps = index < 0 ? [...turn.steps, step] : turn.steps.map((s, i) => (i === index ? step : s));
      return { ...turn, steps };
    }
    case "source-found":
      return { ...turn, found: [...turn.found, { title: event.title, year: event.year }] };
    case "outdated-figure":
      return { ...turn, outdated: [...turn.outdated, { text: event.text, markers: event.markers }] };
    case "answer":
      return { ...turn, answer: event.answer, status: "done" };
    case "factcheck":
      return { ...turn, factcheck: event.factcheck, status: "done" };
    case "visuals":
      return {
        ...turn,
        visuals: event.visuals,
        exploreSources: event.sources ?? turn.exploreSources,
        exploreSummary: event.summary ?? turn.exploreSummary,
        status: "done",
      };
    case "decline":
      return { ...turn, decline: event.decline, status: "done" };
  }
}
