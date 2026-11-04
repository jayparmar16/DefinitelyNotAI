"use client";

/** Live progress of the agent loop; collapses to one line when the run is over. */

import { useEffect, useState } from "react";

import { Icon } from "./Icon";
import type { Turn } from "./turn";

function clock(seconds: number): string {
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

function useElapsed(startedAt: number, running: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!running) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [running]);
  return Math.max(0, Math.round(((running ? now : Date.now()) - startedAt) / 1000));
}

export function ProgressTrace({ turn, onStop }: { turn: Turn; onStop: () => void }) {
  const running = turn.status === "running";
  const [expanded, setExpanded] = useState(true);
  const elapsed = useElapsed(turn.startedAt, running);
  const deep = turn.mode === "deep";
  const open = running || expanded;

  // Collapse once the run finishes, as the design asks; a click opens it again.
  useEffect(() => {
    if (!running) setExpanded(false);
  }, [running]);

  const sources = turn.answer?.sources.length ?? turn.found.length;
  const summary = turn.status === "stopped"
    ? `Stopped after ${clock(elapsed)}; kept what was found`
    : `Researched ${sources} sources in ${turn.answer?.elapsedSeconds ?? elapsed} s`;

  return (
    <div className="aw-trace" aria-live="polite">
      <div className="aw-trace-h">
        <span className={deep ? "aw-mode-chip deep" : "aw-mode-chip"}>
          <Icon name="layers" small /> {deep ? "Deep research" : "Quick answer"}
        </span>
        {running ? (
          <span>Working on your {deep ? "report" : "answer"}</span>
        ) : (
          <button className="toggle" onClick={() => setExpanded(!expanded)} aria-expanded={open}>
            {summary} <Icon name="chevron" small />
          </button>
        )}
        <span className="spacer" />
        {running && (
          <>
            <span className="aw-meta">{clock(elapsed)}</span>
            <button className="aw-btn sm" onClick={onStop}>Stop</button>
          </>
        )}
      </div>
      {open && (
        <ol className="aw-steps">
          {turn.steps.map((step, index) => (
            <li key={step.id}>
              <span className={`aw-dot ${step.status}`}>
                {step.status === "done" ? <Icon name="check" small /> : index + 1}
              </span>
              <span className={step.status === "next" ? "muted" : undefined}>
                {step.status === "now" ? <b>{step.label}</b> : step.label}
                {step.detail && <span className="muted"> · {step.detail}</span>}
              </span>
            </li>
          ))}
        </ol>
      )}
      {open && turn.found.length > 0 && (
        <div className="aw-found">
          {turn.found.map((source) => (
            <span key={source.title}>
              {source.title}
              {source.year ? ` ${source.year}` : ""}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
