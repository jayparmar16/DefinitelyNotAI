"use client";

/** Empty state: "Ask" + a rotating WRI fact, and suggested questions by user journey. */

import { useEffect, useState } from "react";

import { FACT_SECONDS, askFacts } from "@/lib/welcome";

const SUGGESTIONS = [
  { journey: "Find cited work", question: "What has WRI published on electric buses in Latin America?", deep: false },
  { journey: "Recover older work", question: "What did WRI recommend on urban transport before 2010?", deep: false },
  { journey: "Build a briefing", question: "Talking points on bus financing for a partner meeting", deep: true },
  { journey: "Find gaps", question: "Where is WRI's work on bus electrification thin?", deep: true },
];

/** Starting points inside a topic space, by the same journeys. */
function spaceSuggestions(space: string) {
  const topic = space.toLowerCase();
  return [
    { journey: "Find cited work", question: `What are WRI's main findings on ${topic}?`, deep: false },
    { journey: "Recent work", question: `What did WRI publish in 2025 on ${topic}?`, deep: false },
    { journey: "Build a briefing", question: `Talking points on ${topic} for a partner meeting`, deep: true },
    { journey: "Find gaps", question: `Where is WRI's work on ${topic} thin?`, deep: true },
  ];
}

type WelcomeProps = {
  space: string | null;
  documents: number | null;
  onPick: (question: string, deep: boolean) => void;
};

/** Clicking a suggestion fills the composer (and sets the mode it needs); it never sends. */
export function Welcome({ space, documents, onPick }: WelcomeProps) {
  const suggestions = space ? spaceSuggestions(space) : SUGGESTIONS;
  const facts = askFacts(space, documents);
  const [shown, setShown] = useState(0);
  useEffect(() => {
    setShown(0);
    // Changes every few seconds; still for anyone who asked their system to reduce motion.
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const timer = setInterval(() => {
      if (!document.hidden) setShown((i) => (i + 1) % facts.length);
    }, FACT_SECONDS * 1000);
    return () => clearInterval(timer);
  }, [space, facts.length]);
  return (
    <div className="aw-welcome">
      <div>
        <h1 className="aw-ask-line" aria-label={`Ask ${facts[0]}`}>
          <span>Ask</span>
          <span key={shown} className="aw-ask-fact in" aria-hidden="true">{facts[shown]}</span>
        </h1>
        <div className="aw-ask-dots" aria-hidden="true">
          {facts.map((fact, i) => <span key={fact} className={i === shown ? "on" : ""} />)}
        </div>
        {space && <p className="aw-meta">Every answer in this space searches its publications only.</p>}
      </div>
      <div className="aw-suggest">
        {suggestions.map((item) => (
          <button key={item.question} onClick={() => onPick(item.question, item.deep)}>
            <b>{item.journey}</b>
            {item.question}
          </button>
        ))}
      </div>
    </div>
  );
}
