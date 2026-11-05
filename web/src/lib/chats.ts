/**
 * Recent chats kept in this browser, so a refresh doesn't lose the conversation and earlier
 * chats can be reopened. The agent's own memory of each chat is in AgentCore Memory (7 days),
 * keyed by the same session ID, so a reopened chat's follow-ups still have context.
 */

import type { Turn } from "../components/turn.ts";
import type { Lens } from "./agent.ts";

// `space`: the topic space the chat was asked in (absent or null: all of WRI). `named`: the
// title was given (a demo chat's use case), so it is kept instead of the first question.
export type SavedChat = {
  sessionId: string; title: string; updatedAt: number; turns: Turn[]; lens?: Lens | null; space?: string | null; named?: boolean;
};

const CHATS_KEY = "askwri.chats.v1";
const CURRENT_KEY = "askwri.current";
const MAX_CHATS = 12;

/**
 * Save a chat's finished turns and cap the list. A chat moves to the top only when it has a new
 * finished question; opening it, or translating or drawing visuals for an answer in it, updates
 * it where it is, so switching between chats doesn't reorder the list.
 */
export function upsertChat(
  chats: SavedChat[], sessionId: string, turns: Turn[], now: number, lens: Lens | null = null,
  space: string | null = null,
): SavedChat[] {
  const finished = turns.filter((turn) => turn.status !== "running");
  if (!finished.length) return chats;
  const title = finished[0].question.slice(0, 80);
  const index = chats.findIndex((c) => c.sessionId === sessionId);
  if (index >= 0 && chats[index].turns.length >= finished.length) {
    const updated = { ...chats[index], title: chats[index].named ? chats[index].title : title, turns: finished, lens, space };
    return chats.map((c, i) => (i === index ? updated : c));
  }
  const chat = { sessionId, title, updatedAt: now, turns: finished, lens, space };
  return [chat, ...chats.filter((c) => c.sessionId !== sessionId)].slice(0, MAX_CHATS);
}

// Browser storage can be missing or full (private windows, blocked site data): saving chats is a
// convenience, so failures are ignored and the app works without it.
export function readChats(): { chats: SavedChat[]; current: string | null } {
  try {
    const chats = JSON.parse(localStorage.getItem(CHATS_KEY) ?? "[]");
    return { chats: Array.isArray(chats) ? chats : [], current: localStorage.getItem(CURRENT_KEY) };
  } catch {
    return { chats: [], current: null };
  }
}

export function writeChats(chats: SavedChat[], current: string | null): void {
  try {
    localStorage.setItem(CHATS_KEY, JSON.stringify(chats));
    if (current) localStorage.setItem(CURRENT_KEY, current);
    else localStorage.removeItem(CURRENT_KEY);
  } catch {
    // Storage full or blocked: the chat still works, it just isn't kept after a refresh.
  }
}

/** "just now", "5 min ago", "3 h ago", or the date. */
export function whenLabel(updatedAt: number, now: number): string {
  const minutes = Math.round((now - updatedAt) / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  if (minutes < 24 * 60) return `${Math.round(minutes / 60)} h ago`;
  return new Date(updatedAt).toLocaleDateString();
}
