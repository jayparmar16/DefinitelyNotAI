"use client";

/** The one search box: question, Deep research toggle, filters and send. */

import { type FormEvent, type KeyboardEvent, type RefObject, useEffect } from "react";

import type { Filters } from "@/lib/agent";
import { Icon } from "./Icon";
import { Menu } from "./Menu";

const PUB_TYPES = [
  "Report",
  "Issue brief",
  "Guidebook",
  "Working paper",
  "Technical note",
  "Practice note",
  "Expert note",
];

type ComposerProps = {
  inputRef: RefObject<HTMLTextAreaElement | null>;
  draft: string;
  onDraft: (text: string) => void;
  deep: boolean;
  onDeep: (on: boolean) => void;
  checking: boolean; // fact-check a pasted draft instead of asking a question
  onChecking: (on: boolean) => void;
  filters: Filters;
  onFilters: (filters: Filters) => void;
  running: boolean;
  onSend: () => void;
};

function filtersLabel(filters: Filters): string {
  const year = filters.yearFrom ? `${filters.yearFrom} on` : "any year";
  return `Filters: ${year} · ${filters.pubType ?? "any type"}`;
}

export function Composer(props: ComposerProps) {
  const { inputRef, draft } = props;
  const canSend = draft.trim().length > 0 && !props.running;

  // Grow the box with its text, up to the max height set in CSS.
  useEffect(() => {
    const input = inputRef.current;
    if (!input) return;
    input.style.height = "auto";
    input.style.height = `${input.scrollHeight}px`;
  }, [draft, inputRef]);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (canSend) props.onSend();
  };
  const onKey = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) submit(event);
  };

  return (
    <div className="aw-composer-wrap">
      <form className="aw-composer" onSubmit={submit}>
        <label className="visually-hidden" htmlFor="aw-question">Your question</label>
        <textarea
          id="aw-question"
          ref={inputRef}
          className="aw-input"
          rows={1}
          value={draft}
          onChange={(event) => props.onDraft(event.target.value)}
          onKeyDown={onKey}
          placeholder={
            props.checking
              ? "Paste a draft, email or proposal: each claim is checked against WRI's publications"
              : 'Ask about WRI research, e.g. "What has WRI published on electric buses in Latin America?"'
          }
        />
        <div className="aw-composer-row">
          <div className="aw-seg" role="radiogroup" aria-label="What to do">
            <button type="button" role="radio" aria-checked={!props.checking} className={props.checking ? "" : "on"} onClick={() => props.onChecking(false)}>
              Ask
            </button>
            <button type="button" role="radio" aria-checked={props.checking} className={props.checking ? "on" : ""} onClick={() => props.onChecking(true)}>
              Fact-check
            </button>
          </div>
          {!props.checking && (
          <button
            type="button"
            className={props.deep ? "aw-toggle on" : "aw-toggle"}
            role="switch"
            aria-checked={props.deep}
            onClick={() => props.onDeep(!props.deep)}
          >
            <span className="aw-track" />
            Deep research
            <span className="sub">{props.deep ? "searches wider, builds a report" : "off: Quick answer"}</span>
          </button>
          )}
          <span className="spacer" />

          <Menu
            placement="above"
            trigger={({ open, toggle }) => (
              <button type="button" className="aw-btn ghost sm" onClick={toggle} aria-expanded={open}>
                {filtersLabel(props.filters)} <Icon name="chevron" small />
              </button>
            )}
          >
            {() => (
              <>
                <div className="cap">Narrow the search</div>
                <label className="row">
                  From year
                  <input
                    type="number"
                    min={1982}
                    max={2026}
                    placeholder="any"
                    value={props.filters.yearFrom ?? ""}
                    onChange={(event) =>
                      props.onFilters({
                        ...props.filters,
                        yearFrom: event.target.value ? Number(event.target.value) : undefined,
                      })
                    }
                  />
                </label>
                <label className="row">
                  Type
                  <select
                    value={props.filters.pubType ?? ""}
                    onChange={(event) =>
                      props.onFilters({ ...props.filters, pubType: event.target.value || undefined })
                    }
                  >
                    <option value="">Any type</option>
                    {PUB_TYPES.map((type) => (
                      <option key={type}>{type}</option>
                    ))}
                  </select>
                </label>
                <div className="cap">Undated documents are always included.</div>
              </>
            )}
          </Menu>

          {/* Voice input is a to-do in the design doc; the mic stays hidden until it ships. */}
          <button type="submit" className="aw-btn brand icon" disabled={!canSend} title={props.checking ? "Check" : "Ask"}>
            <Icon name="send" label={props.checking ? "Check" : "Ask"} />
          </button>
        </div>
      </form>
      <div className="aw-hint">Searches public WRI publications only. Answers are generated; check the cited page.</div>
    </div>
  );
}
