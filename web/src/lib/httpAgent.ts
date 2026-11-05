/** The AgentClient for the AskWRI API (askwri-api): chat over server-sent events, PDF links. */

import type { AgentClient, Answer, AskRequest } from "./agent.ts";
import { apiHeaders } from "./auth.ts";
import { readEvents } from "./sse.ts";

const LANGUAGE_NAMES: Record<string, string> = {
  en: "English", es: "Spanish", pt: "Portuguese", fr: "French", id: "Indonesian", hi: "Hindi",
};

export function httpAgent(baseUrl: string): AgentClient {
  const base = baseUrl.replace(/\/$/, "");
  const headers = async () => ({ "Content-Type": "application/json", ...(await apiHeaders()) });

  async function* ask(request: AskRequest, signal: AbortSignal) {
    const response = await fetch(`${base}/chat`, {
      method: "POST", headers: await headers(), body: JSON.stringify(request), signal,
    });
    if (!response.ok || !response.body) {
      throw new Error(
        response.status === 401
          ? "Your sign-in has expired. Reload the page to sign in again."
          : `The AskWRI API answered ${response.status}.`,
      );
    }
    yield* readEvents(response.body);
  }

  return {
    ask,

    async sourceDownloadUrl(source) {
      if (!source.pdfKey) return null;
      const response = await fetch(
        `${base}/sources/download?key=${encodeURIComponent(source.pdfKey)}`,
        { headers: await headers() },
      );
      if (!response.ok) throw new Error(`Download link failed (${response.status})`);
      return (await response.json()).url as string;
    },

    // The answer goes back with the request, so the agent translates this answer and not the
    // session's latest one; it checks every number survives.
    async translate(shown, language, sessionId) {
      const request: AskRequest = {
        question: `Now in ${LANGUAGE_NAMES[language] ?? language}`,
        mode: "translate", language, audience: "auto", format: "summary", filters: {}, sessionId,
        answer: shown,
      };
      let answer: Answer | null = null;
      for await (const event of ask(request, new AbortController().signal)) {
        if (event.type === "answer") answer = event.answer;
        if (event.type === "decline") throw new Error(event.decline.message);
      }
      if (!answer) throw new Error("No translation came back");
      const { summary, themes, report, implications, limits, questions } = answer;
      return { summary, paragraphs: report?.keyPoints ?? answer.paragraphs, themes, report, implications, limits, questions };
    },

    async warmup(sessionId) {
      const response = await fetch(`${base}/warm`, {
        method: "POST", headers: await headers(), body: JSON.stringify({ sessionId }),
      });
      if (!response.ok) throw new Error(`Warm-up failed (${response.status})`);
    },
  };
}
