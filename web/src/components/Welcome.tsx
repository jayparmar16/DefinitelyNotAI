/** Empty state: headline, how answers are cited, and suggested questions by user journey. */

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
  const count = documents === null ? "" : ` · ${documents} publications`;
  return (
    <div className="aw-welcome">
      <div>
        <h1>{space ? `Ask WRI's research on ${space}` : "Ask WRI's research"}</h1>
        {space && <p className="aw-meta">The {space} space{count}: every answer searches these publications only.</p>}
        <p className="lead">
          Every answer cites the WRI publication and page it came from. Turn on Deep research for a
          fuller report with gaps, authors and newer figures.
        </p>
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
