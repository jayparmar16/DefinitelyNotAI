/**
 * Ready-made demo chats: /demo-chats.json (written by scripts/record_demo_chats.py from the live
 * system) rebuilt into saved chats, titled by use case. Opening the UI at /?demo=load replaces
 * this browser's chats with them, so a short demo opens finished answers instead of waiting.
 */

import { applyEvent, newTurn, type Turn } from "../components/turn.ts";
import type { AgentEvent, Lens, Mode, ReportFormat } from "./agent.ts";
import type { SavedChat } from "./chats.ts";

export type RecordedChat = {
  title: string;
  space: string | null;
  sessionId: string;
  question: string;
  mode: Mode;
  format?: ReportFormat; // Deep research: the report type it was asked as
  lens?: Lens | null; // the research lens it was asked through
  events: AgentEvent[];
};

/** One recorded chat as the sidebar keeps it: the question's turn, built from its events. */
export function demoChat(recorded: RecordedChat, updatedAt: number): SavedChat {
  const start = {
    ...newTurn(`demo-${recorded.sessionId}`, recorded.question, recorded.mode),
    space: recorded.space,
    ...(recorded.format && { format: recorded.format }),
  };
  const turn: Turn = { ...recorded.events.reduce(applyEvent, start), status: "done" };
  return {
    sessionId: recorded.sessionId, title: recorded.title, named: true, updatedAt, turns: [turn], space: recorded.space,
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
