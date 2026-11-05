/**
 * Topic spaces: one per WRI topic, each a scope for search and its own list of chats. Counts come
 * from /spaces.json, written by `python -m askwri.spaces` at deploy time; without it (local
 * development) the spaces still work, without counts.
 */

// WRI's topics, in the ingestion pipeline's order (askwri/ingest/model_labels.py TOPICS).
export const TOPICS = ["Business", "Cities", "Climate", "Economics", "Energy", "Equity", "Finance", "Food", "Forests", "Freshwater", "Ocean"];

export type Space = { name: string; documents: number | null };
export type Spaces = { total: number | null; spaces: Space[] };

const SPACE_KEY = "askwri.space";

export const FALLBACK: Spaces = { total: null, spaces: TOPICS.map((name) => ({ name, documents: null })) };

/** The spaces with their counts, or the topics alone when the counts file is missing. */
export async function loadSpaces(): Promise<Spaces> {
  try {
    const response = await fetch("/spaces.json", { cache: "no-cache" });
    if (!response.ok) return FALLBACK;
    const data = (await response.json()) as Spaces;
    return { total: data.total, spaces: data.spaces.filter((s) => TOPICS.includes(s.name)) };
  } catch {
    return FALLBACK;
  }
}

/** The filter a request sends for a space: its topic, or nothing for all of WRI. */
export function scoped<T extends object>(filters: T, space: string | null): T & { topic?: string } {
  return space ? { ...filters, topic: space } : filters;
}

// Browser storage can throw (private windows): the space then resets to all of WRI.
export function readSpace(): string | null {
  try {
    const space = localStorage.getItem(SPACE_KEY);
    return space && TOPICS.includes(space) ? space : null;
  } catch {
    return null;
  }
}

export function writeSpace(space: string | null): void {
  try {
    if (space) localStorage.setItem(SPACE_KEY, space);
    else localStorage.removeItem(SPACE_KEY);
  } catch {
    // Not remembered after a refresh; the space still applies now.
  }
}
