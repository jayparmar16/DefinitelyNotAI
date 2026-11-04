"use client";

/** The one search box: question, Deep research toggle, filters and send. */

import { type FormEvent, type KeyboardEvent, type RefObject, useEffect, useState } from "react";


import type { Filters, Lens } from "@/lib/agent";
import { Icon } from "./Icon";
import { LensBar, LensEditor } from "./LensControl";
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

export type Tool = "ask" | "factcheck" | "explore";

const TOOLS: { value: Tool; name: string; placeholder: string }[] = [
  { value: "ask", name: "Ask", placeholder: 'Ask about WRI research, e.g. "How should civil society track adaptation finance?"' },
  { value: "factcheck", name: "Fact-check", placeholder: "Paste a draft, email or proposal: each claim is checked against WRI's publications" },
  { value: "explore", name: "Explore", placeholder: "A topic to explore, e.g. adaptation finance: timeline, citation links and key figures" },
];

type ComposerProps = {
  inputRef: RefObject<HTMLTextAreaElement | null>;
  draft: string;
  onDraft: (text: string) => void;
  deep: boolean;
  onDeep: (on: boolean) => void;
  tool: Tool; // ask a question, fact-check a pasted draft, or explore a topic's visuals
  onTool: (tool: Tool) => void;
  lens: Lens | null;
  onLens: (lens: Lens | null) => void;
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
  const [editingLens, setEditingLens] = useState(false);

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
        {editingLens && (
          <LensEditor
            lens={props.lens}
            onApply={(lens) => {
              props.onLens(lens);
              setEditingLens(false);
            }}
            onCancel={() => setEditingLens(false)}
          />
        )}
        {props.lens && !editingLens && props.tool === "ask" && (
          <LensBar lens={props.lens} onEdit={() => setEditingLens(true)} onClear={() => props.onLens(null)} />
        )}
        <label className="visually-hidden" htmlFor="aw-question">Your question</label>
        <textarea
          id="aw-question"
          ref={inputRef}
          className="aw-input"
          rows={1}
          value={draft}
          onChange={(event) => props.onDraft(event.target.value)}
          onKeyDown={onKey}
          placeholder={TOOLS.find((tool) => tool.value === props.tool)!.placeholder}
        />
        <div className="aw-composer-row">
          <div className="aw-seg" role="radiogroup" aria-label="What to do">
            {TOOLS.map((tool) => (
              <button
                key={tool.value}
                type="button"
                role="radio"
                aria-checked={props.tool === tool.value}
                className={props.tool === tool.value ? "on" : ""}
                onClick={() => props.onTool(tool.value)}
              >
                {tool.name}
              </button>
            ))}
          </div>
          {props.tool !== "explore" && (
          <button
            type="button"
            className={props.deep ? "aw-toggle on" : "aw-toggle"}
            role="switch"
            aria-checked={props.deep}
            onClick={() => props.onDeep(!props.deep)}
            title={
              props.tool === "factcheck"
                ? "Check harder: more passages per claim, and a second search for unsettled claims"
                : "Search wider over several rounds and build a report (about 30-60 s)"
            }
          >
            <span className="aw-track" />
            Deep research

          </button>
          )}
          <span className="spacer" />

          {props.tool === "ask" && !props.lens && !editingLens && (
            <button type="button" className="aw-btn ghost sm" onClick={() => setEditingLens(true)} title="Summarise every paper for your goal and aspects">
              <Icon name="filter" small /> Lens
            </button>
          )}

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
          <button type="submit" className="aw-btn brand icon" disabled={!canSend} title={TOOLS.find((tool) => tool.value === props.tool)!.name}>
            <Icon name="send" label={TOOLS.find((tool) => tool.value === props.tool)!.name} />
          </button>
        </div>
      </form>
      <div className="aw-hint">Searches public WRI publications only. Answers are generated; check the cited page.</div>
    </div>
  );
}
