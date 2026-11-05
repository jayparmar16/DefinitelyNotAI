/** Empty state: headline, how answers are cited, and suggested questions by user journey. */

const SUGGESTIONS = [
  { journey: "Find cited work", question: "What has WRI published on electric buses in Latin America?", deep: false },
  { journey: "Recover older work", question: "What did WRI recommend on urban transport before 2010?", deep: false },
  { journey: "Build a briefing", question: "Talking points on bus financing for a partner meeting", deep: true },
  { journey: "Find gaps", question: "Where is WRI's work on bus electrification thin?", deep: true },
];

/** Clicking a suggestion fills the composer (and sets the mode it needs); it never sends. */
export function Welcome({ onPick }: { onPick: (question: string, deep: boolean) => void }) {
  return (
    <div className="aw-welcome">
      <div>
        <h1>Ask WRI&apos;s research</h1>
        <p className="lead">
          Every answer cites the WRI publication and page it came from. Turn on Deep research for a
          fuller report with gaps, authors and newer figures.
        </p>
      </div>
      <div className="aw-suggest">
        {SUGGESTIONS.map((item) => (
          <button key={item.question} onClick={() => onPick(item.question, item.deep)}>
            <b>{item.journey}</b>
            {item.question}
          </button>
        ))}
      </div>
    </div>
  );
}
