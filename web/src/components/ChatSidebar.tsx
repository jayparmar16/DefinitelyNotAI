"use client";

/** The left sidebar: New chat, the topic spaces, then the current space's recent chats by day. */

import { type PointerEvent as ReactPointerEvent, useState } from "react";

import { type SavedChat, whenLabel } from "@/lib/chats";
import type { Spaces } from "@/lib/spaces";
import { Icon } from "./Icon";

type ChatSidebarProps = {
  chats: SavedChat[];
  spaces: Spaces;
  space: string | null; // the open space; null: all of WRI
  onSpace: (space: string | null) => void;
  width: number;
  onWidth: (width: number) => void;
  current: string;
  onOpen: (chat: SavedChat) => void;
  onNew: () => void;
  onClear: () => void;
  onClose: () => void;
};

function isToday(time: number): boolean {
  return new Date(time).toDateString() === new Date().toDateString();
}

export const SIDEBAR_MIN = 240;
export const SIDEBAR_MAX = 560;

/** The sidebar's right edge: drag it to widen the sidebar and read long chat titles. */
function WidthHandle({ width, onWidth }: { width: number; onWidth: (width: number) => void }) {
  const [dragging, setDragging] = useState(false);
  const start = (event: ReactPointerEvent<HTMLDivElement>) => {
    const startX = event.clientX;
    setDragging(true);
    const move = (moveEvent: PointerEvent) =>
      onWidth(Math.min(SIDEBAR_MAX, Math.max(SIDEBAR_MIN, width + moveEvent.clientX - startX)));
    const stop = () => {
      setDragging(false);
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", stop);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", stop);
  };
  return (
    <div
      className={dragging ? "aw-sidebar-resize dragging" : "aw-sidebar-resize"}
      onPointerDown={start}
      onDoubleClick={() => onWidth(300)}
      role="separator"
      aria-orientation="vertical"
      aria-label="Resize the sidebar (double-click to reset)"
      title="Drag to resize · double-click to reset"
    />
  );
}

function count(documents: number | null): string {
  return documents === null ? "" : String(documents);
}

export function ChatSidebar(props: ChatSidebarProps) {
  const inSpace = props.chats.filter((chat) => (chat.space ?? null) === props.space);
  const groups = [
    { name: "Today", chats: inSpace.filter((chat) => isToday(chat.updatedAt)) },
    { name: "Earlier", chats: inSpace.filter((chat) => !isToday(chat.updatedAt)) },
  ].filter((group) => group.chats.length);
  const spaceButton = (name: string | null, label: string, documents: number | null) => (
    <button
      key={label}
      className={props.space === name ? "aw-space on" : "aw-space"}
      aria-current={props.space === name ? "true" : undefined}
      onClick={() => props.onSpace(name)}
      title={documents === null ? label : `${label}: ${documents} publications`}
    >
      <span>{label}</span>
      <span className="aw-space-n">{count(documents)}</span>
    </button>
  );

  return (
    <nav className="aw-sidebar" aria-label="Chats">
      <WidthHandle width={props.width} onWidth={props.onWidth} />
      <div className="aw-sidebar-top">
        <button className="aw-btn aw-sidebar-new" onClick={props.onNew}>
          <Icon name="plus" small /> New chat
        </button>
        <button className="aw-btn ghost icon aw-sidebar-close" onClick={props.onClose} title="Close sidebar">
          <Icon name="panel" small label="Close sidebar" />
        </button>
      </div>

      <div className="aw-sidebar-list">
        <section className="aw-spaces" aria-label="Spaces">
          <h2 className="aw-sidebar-h">Spaces</h2>
          {spaceButton(null, "All of WRI", props.spaces.total)}
          {props.spaces.spaces.map((space) => spaceButton(space.name, space.name, space.documents))}
        </section>
        {groups.length === 0 && (
          <p className="aw-meta aw-sidebar-empty">
            {props.space ? `Your ${props.space} chats will appear here.` : "Your chats will appear here."}
          </p>
        )}
        {groups.map((group) => (
          <section key={group.name}>
            <h2 className="aw-sidebar-h">{group.name}</h2>
            {group.chats.map((chat) => (
              <button
                key={chat.sessionId}
                className={chat.sessionId === props.current ? "aw-sidebar-chat on" : "aw-sidebar-chat"}
                aria-current={chat.sessionId === props.current ? "page" : undefined}
                onClick={() => props.onOpen(chat)}
                title={`${chat.title}\n${chat.turns.length} question${chat.turns.length === 1 ? "" : "s"} · ${whenLabel(chat.updatedAt, Date.now())}`}
              >
                {chat.title}
              </button>
            ))}
          </section>
        ))}
      </div>

      {props.chats.length > 0 && (
        <div className="aw-sidebar-foot">
          <span className="aw-meta">Kept on this browser only</span>
          <button className="aw-btn sm ghost" onClick={props.onClear}>Clear</button>
        </div>
      )}
    </nav>
  );
}
