"use client";

/**
 * The AskWRI chat screen: header, conversation, composer and side panel. Holds the session
 * state and talks to the agent only through getAgent() (src/lib/agent.ts).
 */

import { type CSSProperties, useEffect, useRef, useState } from "react";

import { type Audience, type Filters, type Lens, type Mode, type ReportFormat, type Source, getAgent, usingMock } from "@/lib/agent";
import { type SavedChat, readChats, upsertChat, writeChats } from "@/lib/chats";
import { unmatchedMarkers } from "@/lib/citations";
import { answerMarkdown, formatCitation, saveFile, sourcesBibtex, sourcesCsv } from "@/lib/exports";
import { factCheckMarkdown } from "@/lib/factcheck";
import { AnswerCard } from "./AnswerCard";
import { AppHeader, type DownloadChoice, LANGUAGES } from "./AppHeader";
import { ChatSidebar } from "./ChatSidebar";
import { Composer } from "./Composer";
import { FactCheckCard } from "./FactCheckCard";
import { DeclineCard, OutdatedFlag } from "./Feedback";
import { ProgressTrace } from "./ProgressTrace";
import { type PanelTab, SidePanel } from "./SidePanel";
import { SourceCards, cardId } from "./SourceCards";
import { type Turn, applyEvent, newTurn, shownAnswer } from "./turn";
import { Welcome } from "./Welcome";

type Panel = { turnId: string; tab: PanelTab; openDocs: number[] } | null;

/** A short-lived link to a source's stored PDF (module level, so its identity never changes). */
async function pdfUrl(source: Source): Promise<string | null> {
  return (await getAgent()).sourceDownloadUrl(source);
}

/** How the agent read a follow-up in the light of the conversation, if it rewrote it. */
function readAs(turn: Turn): string | undefined {
  return turn.steps.find((step) => step.id === "context")?.detail;
}

function nameOf(code: string): string {
  return LANGUAGES.find((l) => l.code === code)?.name ?? code;
}

function slug(text: string): string {
  return text.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 48) || "askwri";
}

export function ChatApp() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState("");
  const [deep, setDeep] = useState(false);
  const [checking, setChecking] = useState(false);
  const [lens, setLens] = useState<Lens | null>(null);
  const [language, setLanguage] = useState("en");
  const [audience, setAudience] = useState<Audience>("auto");
  const [format, setFormat] = useState<ReportFormat>("talking-points");
  const [filters, setFilters] = useState<Filters>({});
  const [sessionId, setSessionId] = useState(() => crypto.randomUUID());
  const [panel, setPanel] = useState<Panel>(null);
  const [panelWidth, setPanelWidth] = useState(480);
  const [active, setActive] = useState<{ turnId: string; marker: number } | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [recent, setRecent] = useState<SavedChat[]>([]);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const abort = useRef<AbortController | null>(null);
  const warmed = useRef<string | null>(null);
  const warming = useRef<Promise<void> | null>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  const scroller = useRef<HTMLDivElement>(null);

  const running = turns.some((turn) => turn.status === "running");
  const lastAnswered = [...turns].reverse().find((turn) => turn.answer);
  const panelTurn = panel ? turns.find((turn) => turn.id === panel.turnId) : undefined;

  // Reopen the chat that was open before a refresh. Read after the first render: the page is
  // pre-rendered without browser storage.
  useEffect(() => {
    const { chats, current } = readChats();
    setRecent(chats);
    // Open on wide screens; on narrow ones it covers the chat, so it starts closed.
    setSidebarOpen(window.matchMedia("(min-width: 1001px)").matches);
    const chat = chats.find((c) => c.sessionId === current);
    if (chat) {
      setTurns(chat.turns);
      setSessionId(chat.sessionId);
    }
  }, []);

  // Save the chat whenever a turn finishes.
  useEffect(() => {
    if (!turns.length || turns.some((turn) => turn.status === "running")) return;
    const chats = upsertChat(readChats().chats, sessionId, turns, Date.now());
    writeChats(chats, sessionId);
    setRecent(chats);
  }, [turns, sessionId]);

  // Start this conversation's agent at the first keystroke: a new session's runtime takes 6-9 s
  // to start, and that time passes while the user is still typing.
  useEffect(() => {
    if (!draft.trim() || warmed.current === sessionId) return;
    warmed.current = sessionId;
    // A failed warm-up only means the first answer starts cold; the question itself still works.
    warming.current = getAgent()
      .then((agent) => agent.warmup(sessionId))
      .catch((error) => console.warn(error));
  }, [draft, sessionId]);

  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(null), 2600);
    return () => clearTimeout(timer);
  }, [toast]);

  // While a turn streams in, follow its progress; when it finishes, show it from its question,
  // so the answer is read from the top rather than landing on the last source card.
  const latest = turns.at(-1);
  useEffect(() => {
    if (!latest) return;
    if (latest.status === "running") {
      scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: "smooth" });
    } else {
      document.getElementById(`q-${latest.id}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [latest?.id, latest?.steps.length, latest?.found.length, latest?.status]);

  const updateTurn = (id: string, change: (turn: Turn) => Turn) =>
    setTurns((all) => all.map((turn) => (turn.id === id ? change(turn) : turn)));

  async function ask(question: string, mode: Mode, reportFormat = format, reader: Audience = audience) {
    const turn = newTurn(crypto.randomUUID(), question, mode);
    setTurns((all) => [...all, turn]);
    if (mode === "deep") setPanel({ turnId: turn.id, tab: "report", openDocs: [] });
    const controller = new AbortController();
    abort.current = controller;
    try {
      const agent = await getAgent();
      // A question sent while the warm-up is still starting this chat's agent would collide
      // with it (the runtime answers the second call with an error), so it waits.
      await warming.current;
      const request = {
        question, mode, language, audience: reader, format: reportFormat, filters, sessionId,
        deep: mode === "factcheck" && deep,
        lens: mode === "factcheck" ? null : lens,
      };
      for await (const event of agent.ask(request, controller.signal)) {
        if (event.type === "answer") {
          const texts = event.answer.report?.keyPoints ?? event.answer.paragraphs;
          const missing = unmatchedMarkers(texts, event.answer.sources);
          if (missing.length) {
            // An answer with a marker but no source has an uncited claim: never show it.
            throw new Error(`The answer cited sources [${missing.join("], [")}] that were not returned.`);
          }
        }
        updateTurn(turn.id, (current) => applyEvent(current, event));
      }
    } catch (error) {
      if (controller.signal.aborted) {
        updateTurn(turn.id, (current) => ({ ...current, status: "stopped" }));
      } else {
        const message = error instanceof Error ? error.message : String(error);
        updateTurn(turn.id, (current) => ({ ...current, status: "failed", error: message }));
      }
    } finally {
      if (abort.current === controller) abort.current = null;
    }
  }

  function send() {
    const question = draft.trim();
    if (!question || running) return;
    setDraft("");
    ask(question, checking ? "factcheck" : deep ? "deep" : "quick");
  }

  // A suggested follow-up goes into the box, not straight to the agent, so it can be edited first.
  function followUp(question: string) {
    setDraft(question);
    input.current?.focus();
  }

  function newChat() {
    abort.current?.abort();
    setTurns([]);
    setPanel(null);
    setActive(null);
    setDraft("");
    setLens(null);
    const next = crypto.randomUUID();
    setSessionId(next);
    warming.current = null;
    writeChats(readChats().chats, next);
    input.current?.focus();
  }

  function closeSidebarIfNarrow() {
    if (!window.matchMedia("(min-width: 1001px)").matches) setSidebarOpen(false);
  }

  function openChat(chat: SavedChat) {
    closeSidebarIfNarrow();
    abort.current?.abort();
    setTurns(chat.turns);
    setSessionId(chat.sessionId);
    setPanel(null);
    setActive(null);
    warming.current = null;
    writeChats(readChats().chats, chat.sessionId);
  }

  function clearChats() {
    writeChats([], null);
    setRecent([]);
  }

  function openMarker(turnId: string, marker: number) {
    setActive({ turnId, marker });
    document.getElementById(cardId(turnId, marker))?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    setPanel((current) => {
      const openDocs = current?.turnId === turnId ? current.openDocs : [];
      return { turnId, tab: marker, openDocs: openDocs.includes(marker) ? openDocs : [...openDocs, marker] };
    });
  }

  function closeDoc(marker: number) {
    setPanel((current) => {
      if (!current) return current;
      const openDocs = current.openDocs.filter((m) => m !== marker);
      const turn = turns.find((t) => t.id === current.turnId);
      const fallback: PanelTab = turn?.mode === "deep" ? "report" : "sources";
      return { ...current, openDocs, tab: current.tab === marker ? openDocs.at(-1) ?? fallback : current.tab };
    });
  }

  async function copy(text: string, what: string) {
    await navigator.clipboard.writeText(text);
    setToast(`${what} copied`);
  }

async function downloadPdf(source: Source) {
    const agent = await getAgent();
    const url = await agent.sourceDownloadUrl(source);
    if (url) window.open(url, "_blank", "noreferrer");
    else setToast("PDF download needs the API (presigned link from the corpus bucket)");
  }

  async function translate(turn: Turn, target: string) {
    const answer = turn.answer!;
    const texts = answer.report?.keyPoints ?? answer.paragraphs;
    const agent = await getAgent();
    const translated = await agent.translate(texts, target, sessionId);
    if (translated.paragraphs.every((text, i) => text === texts[i])) {
      setToast(usingMock ? "The mock agent only has Spanish translations" : "No translation returned");
      return;
    }
    updateTurn(turn.id, (current) => ({ ...current, translation: { ...translated, language: target, showOriginal: false } }));
  }

  function download(turn: Turn, choice: DownloadChoice) {
    const answer = shownAnswer(turn)!;
    const name = slug(answer.report?.title ?? turn.question);
    if (choice === "markdown") saveFile(`${name}.md`, answerMarkdown(turn.question, answer), "text/markdown");
    if (choice === "csv") saveFile(`${name}-sources.csv`, sourcesCsv(answer.sources), "text/csv");
    if (choice === "bibtex") saveFile(`${name}-sources.bib`, sourcesBibtex(answer.sources), "application/x-bibtex");
    if (choice === "copy") copy(answerMarkdown(turn.question, answer), "Markdown");
  }

  function changeFormat(next: ReportFormat) {
    setFormat(next);
    const turn = panelTurn;
    if (turn?.answer?.report && !running) ask(turn.question, "deep", next);
  }

  const bodyStyle = { "--panel-width": `${panelWidth}px` } as CSSProperties;

  return (
    <div className={sidebarOpen ? "aw-app with-sidebar" : "aw-app"}>
      <AppHeader
        mock={usingMock}
        language={language}
        onLanguage={setLanguage}
        audience={audience}
        onAudience={setAudience}
        canDownload={Boolean(lastAnswered)}
        hasReport={Boolean(lastAnswered?.answer?.report)}
        onDownload={(choice) => lastAnswered && download(lastAnswered, choice)}
        onNewChat={newChat}
        sidebarOpen={sidebarOpen}
        onSidebar={() => setSidebarOpen(true)}
      />
      {sidebarOpen && (
        <ChatSidebar
          chats={recent}
          current={sessionId}
          onOpen={openChat}
          onNew={() => {
            closeSidebarIfNarrow();
            newChat();
          }}
          onClear={clearChats}
          onClose={() => setSidebarOpen(false)}
        />
      )}
      <div className={panelTurn ? "aw-body" : "aw-body no-panel"} style={bodyStyle}>
        <main className="aw-main">
          <div className="aw-scroll" ref={scroller}>
            {turns.length === 0 ? (
              <Welcome
                onPick={(question, needsDeep) => {
                  setDraft(question);
                  setDeep(needsDeep);
                  input.current?.focus();
                }}
              />
            ) : (
              <div className="aw-col">
                {turns.map((turn) => {
                  const activeMarker = active?.turnId === turn.id ? active.marker : null;
                  const onMarker = (marker: number) => openMarker(turn.id, marker);
                  return (
                    <div key={turn.id} style={{ display: "contents" }}>
                      <div className="aw-user" id={`q-${turn.id}`}>{turn.question}</div>
                      {readAs(turn) && (
                        <div className="aw-context" title="AskWRI read your follow-up together with the conversation so far">
                          ↳ Read in context as: <q>{readAs(turn)}</q>
                        </div>
                      )}
                      {(turn.mode === "deep" || turn.status === "running") && (
                        <ProgressTrace turn={turn} onStop={() => abort.current?.abort()} />
                      )}
                      {turn.outdated.map((flag) => (
                        <OutdatedFlag key={flag.text} {...flag} activeMarker={activeMarker} onMarker={onMarker} />
                      ))}
                      {turn.answer && (
                        <>
                          <AnswerCard
                            turn={turn}
                            answer={turn.answer}
                            activeMarker={activeMarker}
                            onMarker={onMarker}
                            onCopy={() => copy(answerMarkdown(turn.question, shownAnswer(turn)!), "Answer")}
                            onDownload={() => download(turn, "markdown")}
                            onTranslate={(target) => translate(turn, target)}
                            onToggleOriginal={() =>
                              updateTurn(turn.id, (current) => ({
                                ...current,
                                translation: current.translation && { ...current.translation, showOriginal: !current.translation.showOriginal },
                              }))
                            }
                            onBriefing={() => {
                              setDeep(true);
                              ask(`Turn this into a briefing: ${turn.question}`, "deep");
                            }}
                            onOpenReport={() => setPanel({ turnId: turn.id, tab: "report", openDocs: [] })}
                            onReader={(reader) => ask(turn.question, turn.mode, format, reader)}
                            onFollowUp={followUp}
                          />
                          <SourceCards
                            turnId={turn.id}
                            sources={turn.answer.sources}
                            activeMarker={activeMarker}
                            onOpen={onMarker}
                            onPdf={downloadPdf}
                            onCite={(source) => copy(formatCitation(source), "Citation")}
                            onSources={(choice) => download(turn, choice)}
                          />
                        </>
                      )}
                      {turn.factcheck && (
                        <>
                          <FactCheckCard
                            turnId={turn.id}
                            check={turn.factcheck}
                            activeMarker={activeMarker}
                            onMarker={onMarker}
                            onCopy={() => copy(factCheckMarkdown(turn.factcheck!), "Fact-check")}
                          />
                          {turn.factcheck.sources.length > 0 && (
                            <SourceCards
                              turnId={turn.id}
                              sources={turn.factcheck.sources}
                              activeMarker={activeMarker}
                              onOpen={onMarker}
                              onPdf={downloadPdf}
                              onCite={(source) => copy(formatCitation(source), "Citation")}
                              onSources={(choice) => {
                                const sources = turn.factcheck!.sources;
                                if (choice === "csv") saveFile("fact-check-sources.csv", sourcesCsv(sources), "text/csv");
                                else saveFile("fact-check-sources.bib", sourcesBibtex(sources), "application/x-bibtex");
                              }}
                            />
                          )}
                        </>
                      )}
                      {turn.decline && (
                        <DeclineCard
                          decline={turn.decline}
                          onRephrase={() => {
                            setDraft(turn.question);
                            input.current?.focus();
                          }}
                          onCopySearched={() => copy(turn.decline!.searched.join("\n"), "Search terms")}
                        />
                      )}
                      {turn.status === "failed" && (
                        <div className="aw-decline" role="alert">
                          <div className="aw-decline-h"><span>Something went wrong</span></div>
                          <p style={{ margin: 0 }}>{turn.error}</p>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
          <Composer
            inputRef={input}
            draft={draft}
            onDraft={setDraft}
            deep={deep}
            onDeep={setDeep}
            checking={checking}
            onChecking={setChecking}
            lens={lens}
            onLens={setLens}
            filters={filters}
            onFilters={setFilters}
            running={running}
            onSend={send}
          />
        </main>
        {panel && panelTurn && (
          <SidePanel
            turn={panelTurn}
            tab={panel.tab}
            openDocs={panel.openDocs}
            activeMarker={active?.turnId === panelTurn.id ? active.marker : null}
            width={panelWidth}
            format={format}
            onFollowUp={followUp}
            pdfUrl={pdfUrl}
            languageName={nameOf(
              panelTurn.translation && !panelTurn.translation.showOriginal
                ? panelTurn.translation.language
                : panelTurn.answer?.language ?? language,
            )}
            onTab={(tab) => setPanel({ ...panel, tab })}
            onCloseDoc={closeDoc}
            onMarker={(marker) => openMarker(panelTurn.id, marker)}
            onFormat={changeFormat}
            onPdf={downloadPdf}
            onDownloadReport={() => download(panelTurn, "markdown")}
            onWidth={setPanelWidth}
            onClose={() => setPanel(null)}
          />
        )}
      </div>
      {toast && <div className="aw-toast" role="status">{toast}</div>}
    </div>
  );
}
