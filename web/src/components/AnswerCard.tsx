"use client";

/** A cited answer: header chips, paragraphs (or report key points) with markers, and actions. */

import type { Answer, Reader } from "@/lib/agent";
import { LANGUAGES } from "./AppHeader";
import { AnswerSections, ReaderChip, VerifiedChip } from "./AnswerSections";
import { Icon } from "./Icon";
import { LensTable } from "./LensTable";
import { MarkedText } from "./MarkedText";
import { Menu } from "./Menu";
import { Summary } from "./Summary";
import { type Turn, shownAnswer } from "./turn";

type AnswerCardProps = {
  turn: Turn;
  answer: Answer;
  activeMarker: number | null;
  onMarker: (marker: number) => void;
  onCopy: () => void;
  onDownload: () => void;
  onTranslate: (language: string) => void;
  onToggleOriginal: () => void;
  onBriefing: () => void;
  onOpenReport: () => void;
  onReader: (reader: Reader) => void;
  onFollowUp: (question: string) => void;
  onVisuals: () => void;
};

export function AnswerCard(props: AnswerCardProps) {
  const { turn } = props;
  const translation = turn.translation;
  const showTranslation = translation !== null && !translation.showOriginal;
  const answer = shownAnswer(turn) ?? props.answer;
  const shown = showTranslation ? answer.paragraphs : answer.report?.keyPoints ?? answer.paragraphs;
  const deep = answer.mode === "deep";

  return (
    <div className="aw-answer">
      <div className="aw-answer-meta">
        <span className={deep ? "aw-mode-chip deep" : "aw-mode-chip"}>
          <Icon name="layers" small /> {deep ? "Deep research" : "Quick answer"}
        </span>
        <VerifiedChip answer={answer} />
        <ReaderChip answer={answer} onReader={props.onReader} />
        <span>
          · {answer.sources.length} sources · {answer.elapsedSeconds} s
        </span>
        {(answer.machineTranslated || showTranslation) && <span className="aw-mt">Machine-translated</span>}
        {answer.widened && (
          <span className="aw-mt" title="The quick search found too little, so AskWRI searched as widely as Deep research. Every claim was still checked against its sources.">
            Searched more widely
          </span>
        )}
      </div>

      {answer.scope && <div className="aw-scope">{answer.scope}</div>}
      <Summary texts={answer.summary} activeMarker={props.activeMarker} onMarker={props.onMarker} />
      {answer.summary?.length ? <div className="aw-detail-h">{deep ? "The report" : "In detail"}</div> : null}
      {answer.report && (
        <>
          <h3 style={{ margin: "0 0 4px", fontSize: 20, lineHeight: "28px" }}>{answer.report.title}</h3>
          <div className="aw-meta" style={{ marginBottom: 12 }}>{answer.report.builtFrom}</div>
        </>
      )}
      {answer.report ? (
        <ul style={{ margin: 0, paddingLeft: 20, display: "flex", flexDirection: "column", gap: 8 }}>
          {shown.map((text, index) => (
            <li key={index}>
              <MarkedText text={text} activeMarker={props.activeMarker} onMarker={props.onMarker} />
            </li>
          ))}
        </ul>
      ) : (
        shown.map((text, index) => (
          <p key={index}>
            <MarkedText text={text} activeMarker={props.activeMarker} onMarker={props.onMarker} />
          </p>
        ))
      )}

      {answer.lens && !answer.dossier && (
        <LensTable lens={answer.lens} activeMarker={props.activeMarker} onMarker={props.onMarker} />
      )}
      <AnswerSections answer={answer} onFollowUp={props.onFollowUp} showLimits={!deep} />

      <div className="aw-actions">
        <button className="aw-btn sm" onClick={props.onCopy}>
          <Icon name="copy" small /> Copy
        </button>
        <button className="aw-btn sm" onClick={props.onDownload}>
          <Icon name="download" small /> Download {deep ? "report" : "answer"}
        </button>
        {translation ? (
          <button className="aw-btn sm" onClick={props.onToggleOriginal}>
            <Icon name="translate" small /> {translation.showOriginal ? "Show translation" : "Show original"}
          </button>
        ) : (
          <Menu
            align="left"
            trigger={({ open, toggle }) => (
              <button className="aw-btn sm" onClick={toggle} aria-expanded={open}>
                <Icon name="translate" small /> Translate <Icon name="chevron" small />
              </button>
            )}
          >
            {(close) =>
              LANGUAGES.filter((language) => language.code !== answer.language).map((language) => (
                <button
                  key={language.code}
                  className="row"
                  role="menuitem"
                  onClick={() => {
                    props.onTranslate(language.code);
                    close();
                  }}
                >
                  {language.name}
                </button>
              ))
            }
          </Menu>
        )}
        <button className="aw-btn sm" onClick={props.onVisuals} title="Timeline, citation flow and key figures">
          <Icon name="layers" small /> Visuals
        </button>
        {deep ? (
          <button className="aw-btn sm" onClick={props.onOpenReport}>
            <Icon name="file" small /> Open report
          </button>
        ) : (
          <button className="aw-btn sm" onClick={props.onBriefing}>
            <Icon name="layers" small /> Turn into briefing
          </button>
        )}
      </div>
    </div>
  );
}
