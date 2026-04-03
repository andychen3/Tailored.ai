import type { ChatSession } from "../types/chat";

type SidebarProps = {
  isOpen: boolean;
  canStartChat: boolean;
  isDisconnectingNotion: boolean;
  sessions: ChatSession[];
  currentSessionId: string | null;
  deletingSessionId: string | null;
  onToggle: () => void;
  onNewChat: () => void;
  onDisconnectNotion: () => void;
  onSelectSession: (sessionId: string) => void;
  onDeleteSession: (sessionId: string) => void;
};

export function Sidebar({
  isOpen,
  canStartChat,
  isDisconnectingNotion,
  sessions,
  currentSessionId,
  deletingSessionId,
  onToggle,
  onNewChat,
  onDisconnectNotion,
  onSelectSession,
  onDeleteSession,
}: SidebarProps) {
  return (
    <aside
      className={[
        "absolute inset-y-0 left-0 z-30 flex flex-col overflow-hidden border-r border-border bg-bg2 transition-all duration-200 lg:relative",
        isOpen
          ? "w-[220px] translate-x-0"
          : "-translate-x-full w-[56px] lg:translate-x-0",
      ].join(" ")}
    >
      <div className="flex h-[58px] items-center gap-2 border-b border-border px-3">
        <button
          className="flex h-7 w-7 items-center justify-center rounded-md border border-border2 bg-bg3 text-text2 transition hover:bg-bg4 hover:text-text"
          onClick={onToggle}
          title="Toggle sidebar"
          type="button"
        >
          <svg
            width="14"
            height="14"
            viewBox="0 0 14 14"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
          >
            <path d="M2 3.5h10M2 7h10M2 10.5h10" />
          </svg>
        </button>

        <span
          className={[
            "text-[15px] font-medium tracking-[-0.02em] transition-all",
            isOpen ? "opacity-100" : "w-0 overflow-hidden opacity-0",
          ].join(" ")}
        >
          Tailored<span className="text-accent">.ai</span>
        </span>
      </div>

      <div className="border-b border-border p-2.5">
        <button
          className={[
            "flex w-full items-center gap-2 rounded-card border px-2.5 py-2 text-left text-[13px] transition",
            canStartChat
              ? "cursor-pointer border-border2 bg-bg3 text-text hover:bg-bg4"
              : "cursor-not-allowed border-border2 bg-bg3 text-text2 opacity-45",
            !isOpen ? "justify-center px-2" : "",
          ].join(" ")}
          disabled={!canStartChat}
          onClick={onNewChat}
          type="button"
        >
          <svg
            width="13"
            height="13"
            viewBox="0 0 13 13"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M6.5 1.5v10M1.5 6.5h10" />
          </svg>
          <span className={isOpen ? "opacity-100" : "hidden"}>New chat</span>
        </button>
        <button
          className={[
            "mt-2 flex w-full items-center gap-2 rounded-card border px-2.5 py-2 text-left text-[13px] transition",
            "cursor-pointer border-border2 bg-bg3 text-text hover:bg-bg4",
            !isOpen ? "justify-center px-2" : "",
            isDisconnectingNotion ? "opacity-60" : "",
          ].join(" ")}
          disabled={isDisconnectingNotion}
          onClick={onDisconnectNotion}
          type="button"
        >
          {isDisconnectingNotion ? (
            <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" />
          ) : (
            <svg
              width="13"
              height="13"
              viewBox="0 0 13 13"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M5 2.5h-2a1 1 0 0 0-1 1v6a1 1 0 0 0 1 1h2" />
              <path d="M8 9.5 11 6.5 8 3.5" />
              <path d="M11 6.5H5" />
            </svg>
          )}
          <span className={isOpen ? "opacity-100" : "hidden"}>Disconnect Notion</span>
        </button>
      </div>

      <div
        className={[
          "px-3 pb-2 pt-3 text-[10px] font-medium uppercase tracking-[0.08em] text-text3 transition-all",
          isOpen ? "opacity-100" : "opacity-0",
        ].join(" ")}
      >
        Recent
      </div>

      <div className="flex-1 space-y-1 overflow-y-auto px-1.5 pb-2">
        {sessions.length === 0 ? (
          <div
            className={
              isOpen ? "flex h-full items-center justify-center" : "hidden"
            }
          >
            <div className="mx-2 flex flex-col items-center gap-2 rounded-card border border-dashed border-border bg-bg3/40 p-4 text-center">
              <div className="flex h-8 w-8 items-center justify-center rounded-full border border-border bg-bg3 text-text3">
                <svg
                  width="14"
                  height="14"
                  viewBox="0 0 14 14"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.3"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <circle cx="7" cy="7" r="5" />
                  <path d="M7 4v3l2 1" />
                </svg>
              </div>
              <p className="text-xs text-text3">
                No chats yet. Add a source to begin.
              </p>
            </div>
          </div>
        ) : (
          sessions.map((session) => {
            const active = session.id === currentSessionId;
            const isDeleting = deletingSessionId === session.id;
            return (
              <div
                key={session.id}
                className={[
                  "group flex items-center gap-2 rounded-card border p-2 transition",
                  active
                    ? "border-border bg-bg3"
                    : "border-transparent hover:bg-bg3",
                ].join(" ")}
              >
                <button
                  className="flex min-w-0 flex-1 items-center gap-2 text-left"
                  onClick={() => onSelectSession(session.id)}
                  type="button"
                >
                  <div className="flex h-5 w-5 shrink-0 items-center justify-center rounded-md border border-accentBorder bg-accentBg">
                    <svg
                      width="10"
                      height="10"
                      viewBox="0 0 10 10"
                      fill="none"
                      stroke="#a0aaff"
                      strokeWidth="1.4"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    >
                      <path d="M1 5h8M5 1l4 4-4 4" />
                    </svg>
                  </div>

                  <div
                    className={[
                      "min-w-0 transition-all",
                      isOpen ? "opacity-100" : "w-0 overflow-hidden opacity-0",
                    ].join(" ")}
                  >
                    <div
                      className={[
                        "truncate text-xs font-medium",
                        active ? "text-[#a0aaff]" : "text-text",
                      ].join(" ")}
                    >
                      {session.title}
                    </div>
                    <div className="truncate text-[11px] text-text3">
                      {session.createdAtLabel}
                    </div>
                  </div>
                </button>

                {isOpen ? (
                  <button
                    type="button"
                    aria-label={`Delete ${session.title}`}
                    disabled={isDeleting}
                    onClick={(event) => {
                      event.stopPropagation();
                      onDeleteSession(session.id);
                    }}
                    className={[
                      "flex h-7 w-7 shrink-0 items-center justify-center rounded-md border transition",
                      isDeleting
                        ? "cursor-not-allowed border-border2 bg-bg2 text-text3 opacity-50"
                        : [
                            "border-border2 bg-transparent text-text3",
                            "hover:border-red/40 hover:bg-red/10 hover:text-red",
                            active
                              ? "opacity-75"
                              : "opacity-0 group-hover:opacity-100 group-focus-within:opacity-100",
                          ].join(" "),
                    ].join(" ")}
                  >
                    {isDeleting ? (
                      <span className="h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent" />
                    ) : (
                      <svg
                        width="10"
                        height="10"
                        viewBox="0 0 12 12"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="1.3"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      >
                        <path d="M2.5 3.2h7" />
                        <path d="M4.2 3.2V2.3h3.6v0.9" />
                        <path d="M3.5 4.2v4.3a1 1 0 0 0 1 1h3a1 1 0 0 0 1-1V4.2" />
                        <path d="M5 5.2v2.8M7 5.2v2.8" />
                      </svg>
                    )}
                  </button>
                ) : null}
              </div>
            );
          })
        )}
      </div>
    </aside>
  );
}
