/**
 * Ready-made demo chats: /demo-chats.json (written by scripts/record_demo_chats.py from the live
 * system) rebuilt into saved chats, titled by use case. Opening the UI at /?demo=load replaces
 * this browser's chats with them, so a short demo opens finished answers instead of waiting.
 */

import { applyEvent, newTurn, type Turn } from "../components/turn.ts";
import type { AgentEvent, Filters, Lens, Mode, ReportFormat } from "./agent.ts";
import type { SavedChat } from "./chats.ts";

export type RecordedTurn = { question: string; mode: Mode; format?: ReportFormat; filters?: Filters; events: AgentEvent[] };

export type RecordedChat = {
  title: string;
  space: string | null;
  sessionId: string;
  turns?: RecordedTurn[]; // a story: several questions asked in order in one chat
  question: string;
  mode: Mode;
  format?: ReportFormat; // Deep research: the report type it was asked as
  filters?: Filters; // the filters it was asked with
  lens?: Lens | null; // the research lens it was asked through
  events: AgentEvent[];
};

function demoTurn(id: string, recorded: RecordedTurn, space: string | null): Turn {
  const start = {
    ...newTurn(id, recorded.question, recorded.mode),
    space,
    ...(recorded.format && { format: recorded.format }),
    ...(recorded.filters && { filters: recorded.filters }),
  };
  return { ...recorded.events.reduce(applyEvent, start), status: "done" };
}

/** One recorded chat as the sidebar keeps it: its turns, built from their events. */
export function demoChat(recorded: RecordedChat, updatedAt: number): SavedChat {
  const asked = recorded.turns ?? [recorded];
  const turns = asked.map((turn, i) => demoTurn(`demo-${recorded.sessionId}-${i}`, turn, recorded.space));
  return {
    sessionId: recorded.sessionId, title: recorded.title, named: true, updatedAt, turns, space: recorded.space,
    lens: recorded.lens ?? null,
  };
}

/** The demo chats, first one newest so the sidebar lists them in order. */
export function demoChats(recorded: RecordedChat[], now: number): SavedChat[] {
  return recorded.map((chat, i) => demoChat(chat, now - i * 1000));
}

export async function fetchDemoChats(now: number): Promise<SavedChat[]> {
  const response = await fetch("/demo-chats.json", { cache: "no-cache" });
  if (!response.ok) throw new Error(`No demo chats on this site (${response.status})`);
  return demoChats(((await response.json()) as { chats: RecordedChat[] }).chats, now);
}
