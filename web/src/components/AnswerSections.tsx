"use client";

/**
 * What surrounds the cited findings: AskWRI's labelled interpretation, what the evidence can't
 * tell you, and follow-up questions. Shared by the chat answer and the report panel.
 */

import type { Answer, Reader } from "@/lib/agent";
import { Icon } from "./Icon";
import { Menu } from "./Menu";

export const READERS: { value: Reader; name: string }[] = [
  { value: "researcher", name: "Researcher" },
  { value: "policymaker", name: "Policymaker" },
  { value: "partnerships", name: "Partnerships" },
];

export function readerName(reader: Reader | undefined): string {
  return READERS.find((r) => r.value === reader)?.name ?? "Researcher";
}

/** "Written for: Policymaker": shows who the agent wrote for, and re-asks for another reader. */
export function ReaderChip({ answer, onReader }: { answer: Answer; onReader: (reader: Reader) => void }) {
  return (
    <Menu
      align="left"
      trigger={({ open, toggle }) => (
        <button
          className="aw-reader"
          onClick={toggle}
          aria-expanded={open}
          title="AskWRI picks the reader from your question. Choose another to rewrite the answer for them."
        >
          Written for: {readerName(answer.audience)} <Icon name="chevron" small />
        </button>
      )}
    >
      {(close) => (
        <>
          <div className="cap">Rewrite this answer for</div>
          {READERS.filter((r) => r.value !== answer.audience).map((reader) => (
            <button
              key={reader.value}
              className="row"
              role="menuitem"
              onClick={() => {
                onReader(reader.value);
                close();
              }}
            >
              {reader.name}
            </button>
          ))}
        </>
      )}
    </Menu>
  );
}

/** "5 of 6 claims verified", expandable to the claims the sources didn't support. */
export function VerifiedChip({ answer }: { answer: Answer }) {
  const removed = answer.removedClaims ?? [];
  const label = (
    <>
      <Icon name="check" small /> {answer.claimsVerified} of {answer.claimsTotal} claims verified
    </>
  );
  if (!removed.length) return <span className="aw-verified">{label}</span>;
  return (
    <details className="aw-removed">
      <summary className="aw-verified">
        {label} · {removed.length} removed <Icon name="chevron" small />
      </summary>
      <div className="aw-removed-body">
        <div className="aw-meta">Removed because the cited sources didn&apos;t state them:</div>
        <ul>
          {removed.map((claim) => (
            <li key={claim}>{claim}</li>
          ))}
        </ul>
      </div>
    </details>
  );
}

type SectionsProps = {
  answer: Answer;
  onFollowUp: (question: string) => void;
  /** Off in the report, which shows its own "Where the evidence is thin". */
  showLimits?: boolean;
};

export function AnswerSections({ answer, onFollowUp, showLimits = true }: SectionsProps) {
  const implications = answer.implications ?? [];
  const limits = showLimits ? answer.limits ?? [] : [];
  const questions = answer.questions ?? [];
  return (
    <>
      {implications.length > 0 && (
        <section className="aw-interp" aria-label="Possible implications">
          <h5>
            Possible implications <span>AskWRI&apos;s interpretation, not WRI findings</span>
          </h5>
          <ul>
            {implications.map((text) => (
              <li key={text}>{text}</li>
            ))}
          </ul>
        </section>
      )}
      {limits.length > 0 && (
        <section className="aw-section" aria-label="What this can't tell you">
          <h5>What this can&apos;t tell you</h5>
          <ul>
            {limits.map((text) => (
              <li key={text}>{text}</li>
            ))}
          </ul>
        </section>
      )}
      {questions.length > 0 && (
        <section className="aw-section" aria-label="Questions to explore">
          <h5>Questions to explore</h5>
          <div className="aw-followups">
            {questions.map((question) => (
              <button key={question} className="aw-btn sm" onClick={() => onFollowUp(question)}>
                {question}
              </button>
            ))}
          </div>
        </section>
      )}
    </>
  );
}
