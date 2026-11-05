"use client";

/**
 * The research lens in the composer: a bar showing the active lens, and an editor for the goal
 * and its 2-4 aspects. The lens stays on for every question in the chat until it is cleared.
 */

import { type KeyboardEvent, useState } from "react";

import type { Lens } from "@/lib/agent";
import { Icon } from "./Icon";

const MAX_ASPECTS = 4;

export function LensBar({ lens, onEdit, onClear }: { lens: Lens; onEdit: () => void; onClear: () => void }) {
  return (
    <div className="aw-lensbar">
      <span className="k">Your lens</span>
      <span className="goal" title={lens.goal}>{lens.goal}</span>
      {lens.aspects.map((aspect) => (
        <span key={aspect} className="aw-chip">{aspect}</span>
      ))}
      <span className="spacer" />
      <button type="button" className="aw-btn sm ghost" onClick={onEdit}>Edit</button>
      <button type="button" className="aw-btn sm ghost icon" onClick={onClear} title="Turn the lens off">
        <Icon name="close" small label="Turn the lens off" />
      </button>
    </div>
  );
}

type LensEditorProps = { lens: Lens | null; onApply: (lens: Lens) => void; onCancel: () => void };

export function LensEditor({ lens, onApply, onCancel }: LensEditorProps) {
  const [goal, setGoal] = useState(lens?.goal ?? "");
  const [aspects, setAspects] = useState<string[]>(lens?.aspects ?? []);
  const [next, setNext] = useState("");

  // Commas separate aspects, whether typed one at a time or pasted as a list.
  const split = (text: string) => text.split(",").map((a) => a.trim()).filter(Boolean);
  const merged = (more: string[]) => [...new Set([...aspects, ...more])].slice(0, MAX_ASPECTS);
  const add = () => {
    setAspects(merged(split(next)));
    setNext("");
  };
  const onAspectKey = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter" || event.key === ",") {
      event.preventDefault();
      add();
    }
  };
  const ready = goal.trim() && merged(split(next)).length > 0;

  return (
    <div className="aw-lens-editor" role="group" aria-label="Research lens">
      <div className="aw-lens-h">
        <b>Research lens</b>
        <p>Tell AskWRI what you are working on. It reads every paper with your goal in mind.</p>
        <p>Add up to {MAX_ASPECTS} topics to compare. Each paper gets a short summary for each topic.</p>
      </div>
      <label className="aw-lens-field">
        <span>Your goal</span>
        <input
          value={goal}
          maxLength={200}
          onChange={(event) => setGoal(event.target.value)}
          placeholder="For example: plan for extreme heat in a city"
          autoFocus
        />
      </label>
      <div className="aw-lens-field">
        <span>Topics to compare</span>
        <div className="aw-lens-aspects">
          {aspects.map((aspect) => (
            <span key={aspect} className="aw-chip">
              {aspect}
              <button type="button" onClick={() => setAspects(aspects.filter((a) => a !== aspect))} aria-label={`Remove ${aspect}`}>×</button>
            </span>
          ))}
          {aspects.length < MAX_ASPECTS && (
            <input
              value={next}
              maxLength={60}
              onChange={(event) => setNext(event.target.value)}
              onKeyDown={onAspectKey}
              onBlur={add}
              placeholder={aspects.length ? "Add another topic" : "For example: cost, who pays, results"}
            />
          )}
        </div>
      </div>
      <div className="aw-lens-actions">
        <button type="button" className="aw-btn sm" onClick={onCancel}>Cancel</button>
        <button
          type="button"
          className="aw-btn sm brand"
          disabled={!ready}
          onClick={() => onApply({ goal: goal.trim(), aspects: merged(split(next)) })}
        >
          Use this lens
        </button>
      </div>
    </div>
  );
}
