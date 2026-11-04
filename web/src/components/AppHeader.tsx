"use client";

/** The dark header band: mark, audience (Auto by default), language, Download, New chat. */

import type { Audience } from "@/lib/agent";
import { Icon } from "./Icon";
import { Menu } from "./Menu";

export const LANGUAGES = [
  { code: "en", name: "English" },
  { code: "es", name: "Español" },
  { code: "pt", name: "Português" },
  { code: "id", name: "Bahasa Indonesia" },
];

const AUDIENCES: { value: Audience; name: string }[] = [
  { value: "auto", name: "Auto" },
  { value: "researcher", name: "Researcher" },
  { value: "policymaker", name: "Policymaker" },
  { value: "partnerships", name: "Partnerships" },
];

export type DownloadChoice = "markdown" | "csv" | "bibtex" | "copy";

type AppHeaderProps = {
  mock: boolean;
  language: string;
  onLanguage: (code: string) => void;
  audience: Audience;
  onAudience: (audience: Audience) => void;
  canDownload: boolean;
  hasReport: boolean;
  onDownload: (choice: DownloadChoice) => void;
  onNewChat: () => void;
};

export function AppHeader(props: AppHeaderProps) {
  const thing = props.hasReport ? "report" : "answer";
  return (
    <header className="aw-header">
      <div className="aw-logo">
        {/* shortcut: placeholder mark until the Data Lab shares WRI's official logo files */}
        <span className="aw-logo-mark">WRI</span>AskWRI<small>Research assistant</small>
      </div>
      {props.mock && <span className="aw-mock" title="Answers come from the mock agent in src/mock">Mock data</span>}
      <span className="spacer" />

      <label className="aw-select" title="Who answers are written for. Auto reads it from each question.">
          <span className="k lbl">Audience</span>
          <select
            className="aw-select-native"
            value={props.audience}
            onChange={(event) => props.onAudience(event.target.value as Audience)}
          >
            {AUDIENCES.map((option) => (
              <option key={option.value} value={option.value}>{option.name}</option>
            ))}
          </select>
          <Icon name="chevron" small />
        </label>

      <label className="aw-select">
        <Icon name="globe" small />
        <span className="k lbl">Language</span>
        <select
          className="aw-select-native"
          value={props.language}
          onChange={(event) => props.onLanguage(event.target.value)}
        >
          {LANGUAGES.map((option) => (
            <option key={option.code} value={option.code}>{option.name}</option>
          ))}
        </select>
        <Icon name="chevron" small />
      </label>

      <Menu
        trigger={({ open, toggle }) => (
          <button
            className="aw-btn on-dark"
            onClick={toggle}
            aria-expanded={open}
            disabled={!props.canDownload}
            title={props.canDownload ? undefined : "Ask a question first"}
          >
            <Icon name="download" small /> <span className="lbl">Download</span> <Icon name="chevron" small />
          </button>
        )}
      >
        {(close) => {
          const pick = (choice: DownloadChoice) => () => {
            props.onDownload(choice);
            close();
          };
          return (
            <>
              <div className="cap">Download this {thing}</div>
              <button className="row" role="menuitem" onClick={pick("markdown")}>
                <Icon name="file" small /> {props.hasReport ? "Report" : "Answer"} as Markdown
              </button>
              <div className="sep" />
              <div className="cap">Sources only</div>
              <button className="row" role="menuitem" onClick={pick("csv")}>
                <Icon name="file" small /> Sources as CSV
              </button>
              <button className="row" role="menuitem" onClick={pick("bibtex")}>
                <Icon name="file" small /> Sources as BibTeX
              </button>
              <div className="sep" />
              <button className="row" role="menuitem" onClick={pick("copy")}>
                <Icon name="copy" small /> Copy as Markdown
              </button>
            </>
          );
        }}
      </Menu>

      <button className="aw-btn on-dark icon" onClick={props.onNewChat} title="New chat">
        <Icon name="plus" small label="New chat" />
      </button>
    </header>
  );
}
