/** One question and everything the agent streamed back for it, as the UI keeps it. */

import type { AgentEvent, Answer, Decline, Mode, Report, StepStatus } from "@/lib/agent";

export type Step = { id: string; label: string; detail?: string; status: StepStatus };

export type Turn = {
  id: string;
  question: string;
  mode: Mode;
  status: "running" | "done" | "stopped" | "failed";
  startedAt: number;
  steps: Step[];
  found: { title: string; year: number | null }[];
  outdated: { text: string; markers: number[] }[];
  answer: Answer | null;
  decline: Decline | null;
  error: string | null;
  translation: { language: string; paragraphs: string[]; report: Report | null; showOriginal: boolean } | null;
};

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
    case "decline":
      return { ...turn, decline: event.decline, status: "done" };
  }
}
