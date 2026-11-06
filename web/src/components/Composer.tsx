"use client";

/** The one search box: question, Deep research toggle, filters and send. */

import { type FormEvent, type KeyboardEvent, type RefObject, useEffect, useState } from "react";


import type { Filters, Lens, ReportFormat } from "@/lib/agent";
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

// The ingestion pipeline's regions (askwri/ingest/vocabulary.py); topics are spaces, in the sidebar.
const REGIONS = [
  "Global", "Africa", "Sub-Saharan Africa", "Middle East and North Africa", "Asia", "East Asia",
  "South Asia", "Southeast Asia", "Central Asia", "Europe", "Latin America and the Caribbean",
  "North America", "Oceania", "Small island developing states",
];

export type Tool = "ask" | "factcheck" | "explore";

const TOOLS: { value: Tool; name: string; placeholder: string }[] = [
  { value: "ask", name: "Ask", placeholder: 'Ask about WRI research, e.g. "How should civil society track adaptation finance?"' },
  { value: "factcheck", name: "Fact-check", placeholder: "Paste a draft, email or proposal: each claim is checked against WRI's publications" },
  { value: "explore", name: "Explore", placeholder: "A topic to explore, e.g. adaptation finance: timeline, citation links and key figures" },
];

const REPORT_TYPES: { value: ReportFormat; name: string; hint: string }[] = [
  { value: "talking-points", name: "Talking points", hint: "Short points for a partner or funder meeting" },
  { value: "issue-brief", name: "Issue brief", hint: "Bottom line and implications for policymakers" },
  { value: "summary", name: "Researcher summary", hint: "Precise findings, methods and caveats" },
  { value: "dossier", name: "Topic dossier", hint: "Compare up to 8 papers: evidence matrix, where they agree and differ, what's missing" },
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
  format: ReportFormat;
  onFormat: (format: ReportFormat) => void;
  filters: Filters;
  onFilters: (filters: Filters) => void;
  running: boolean;
  onSend: () => void;
};

/** The filters that are on, as removable chips ("From 2020", "Report", "Africa"). */
export function filterChips(filters: Filters, onFilters: (filters: Filters) => void): { label: string; clear: () => void }[] {
  const chips: { label: string; clear: () => void }[] = [];
  if (filters.yearFrom) chips.push({ label: `From ${filters.yearFrom}`, clear: () => onFilters({ ...filters, yearFrom: undefined }) });
  if (filters.pubType) chips.push({ label: filters.pubType, clear: () => onFilters({ ...filters, pubType: undefined }) });
  if (filters.region) chips.push({ label: filters.region, clear: () => onFilters({ ...filters, region: undefined }) });
  return chips;
}

export function Composer(props: ComposerProps) {
  const { inputRef, draft } = props;
  const canSend = draft.trim().length > 0 && !props.running;
  const chips = filterChips(props.filters, props.onFilters);
  const narrowed = chips.length > 0 || Boolean(props.lens);
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
        {chips.length > 0 && (
          <div className="aw-filter-chips" aria-label="Search filters on">
            {chips.map((chip) => (
              <span key={chip.label} className="aw-chip">
                {chip.label}
                <button type="button" onClick={chip.clear} aria-label={`Remove ${chip.label}`}>×</button>
              </span>
            ))}
          </div>
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
          {props.tool === "ask" && props.deep && (
            <label className="aw-report-type" title={REPORT_TYPES.find((t) => t.value === props.format)?.hint}>
              <span className="visually-hidden">Report type</span>
              <select value={props.format} onChange={(event) => props.onFormat(event.target.value as ReportFormat)}>
                {REPORT_TYPES.map((type) => (
                  <option key={type.value} value={type.value}>{type.name}</option>
                ))}
              </select>
            </label>
          )}
          {/* Lens, filters and send stay together at the right end, so Send never wraps away. */}
          <div className="aw-composer-end">
          {/* One Options menu holds the research lens and the search filters, to keep the box calm. */}
          <Menu
            placement="above"
            trigger={({ open, toggle }) => (
              <button
                type="button"
                className={narrowed ? "aw-btn ghost aw-options on" : "aw-btn ghost aw-options"}
                onClick={toggle}
                aria-expanded={open}
                title="Research lens and filters"
              >
                <Icon name="sliders" small /> Options{narrowed && <span className="aw-options-dot" aria-label="(some on)" />}
              </button>
            )}
          >
            {() => (
              <>
                {props.tool === "ask" && (
                  <>
                    <div className="cap">Research lens</div>
                    <button type="button" className="row" role="menuitem" onClick={() => setEditingLens(true)}>
                      <Icon name="filter" small /> {props.lens ? "Change your lens" : "Read every paper with your goal in mind"}
                    </button>
                    <div className="sep" />
                  </>
                )}
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
                <label className="row">
                  Region
                  <select
                    value={props.filters.region ?? ""}
                    onChange={(event) =>
                      props.onFilters({ ...props.filters, region: event.target.value || undefined })
                    }
                  >
                    <option value="">Anywhere</option>
                    {REGIONS.map((region) => (
                      <option key={region}>{region}</option>
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
        </div>
      </form>
    </div>
  );
}
