"use client";

/** The left sidebar of chats, as in Claude: New chat, then this browser's recent chats by day. */

import { type SavedChat, whenLabel } from "@/lib/chats";
import { Icon } from "./Icon";

type ChatSidebarProps = {
  chats: SavedChat[];
  current: string;
  onOpen: (chat: SavedChat) => void;
  onNew: () => void;
  onClear: () => void;
  onClose: () => void;
};

function isToday(time: number): boolean {
  return new Date(time).toDateString() === new Date().toDateString();
}

export function ChatSidebar(props: ChatSidebarProps) {
  const groups = [
    { name: "Today", chats: props.chats.filter((chat) => isToday(chat.updatedAt)) },
    { name: "Earlier", chats: props.chats.filter((chat) => !isToday(chat.updatedAt)) },
  ].filter((group) => group.chats.length);

  return (
    <nav className="aw-sidebar" aria-label="Chats">
      <div className="aw-sidebar-top">
        <button className="aw-btn aw-sidebar-new" onClick={props.onNew}>
          <Icon name="plus" small /> New chat
        </button>
        <button className="aw-btn ghost icon aw-sidebar-close" onClick={props.onClose} title="Close sidebar">
          <Icon name="panel" small label="Close sidebar" />
        </button>
      </div>

      <div className="aw-sidebar-list">
        {groups.length === 0 && <p className="aw-meta aw-sidebar-empty">Your chats will appear here.</p>}
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
