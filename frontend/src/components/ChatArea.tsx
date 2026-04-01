import { useEffect, useRef } from "react";

import { EMPTY_STATE_CONTENT, EMPTY_STATE_STEPS } from "../constants/chatUi";
import type { ChatMessage } from "../types/chat";

type ChatAreaProps = {
  title: string;
  isDrawerOpen: boolean;
  hasReadySource: boolean;
  showEmptyState: boolean;
  messages: ChatMessage[];
  chatInput: string;
  isSendingMessage: boolean;
  requestError: string | null;
  onChatInputChange: (value: string) => void;
  onSendMessage: () => void;
  onToggleDrawer: () => void;
  onOpenDrawer: () => void;
};

export function ChatArea({
  title,
  isDrawerOpen,
  hasReadySource,
  showEmptyState,
  messages,
  chatInput,
  isSendingMessage,
  requestError,
  onChatInputChange,
  onSendMessage,
  onToggleDrawer,
  onOpenDrawer,
}: ChatAreaProps) {
  const messagesRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (messagesRef.current) {
      messagesRef.current.scrollTop = messagesRef.current.scrollHeight;
    }
  }, [messages]);

  return (
    <main className="flex min-w-0 flex-1 flex-col bg-bg">
      <header className="flex h-[58px] items-center justify-between gap-3 border-b border-border px-4 lg:px-5">
        <h1
          className={[
            "truncate text-sm font-medium",
            showEmptyState ? "text-text2" : "text-text",
          ].join(" ")}
        >
          {title}
        </h1>

        <button
          type="button"
          onClick={onToggleDrawer}
          className={[
            "flex items-center gap-1.5 rounded-card border px-3 py-1.5 text-xs transition",
            isDrawerOpen
              ? "border-accentBorder bg-accentBg text-[#a0aaff]"
              : "border-border2 bg-bg2 text-text2 hover:bg-bg3 hover:text-text",
          ].join(" ")}
        >
          <svg
            width="13"
            height="13"
            viewBox="0 0 14 14"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.3"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <rect x="2" y="2" width="10" height="10" rx="2" />
            <path d="M2 6h10M6 6v6" />
          </svg>
          Sources
        </button>
      </header>

      {requestError ? (
        <div className="border-b border-red/40 bg-red/10 px-4 py-2 text-xs text-red lg:px-5">
          {requestError}
        </div>
      ) : null}

      {showEmptyState ? (
        <section className="flex flex-1 flex-col items-center justify-center gap-6 px-5 py-8 text-center lg:px-8">
          <div className="flex h-14 w-14 items-center justify-center rounded-full border border-border2 bg-bg2">
            <svg
              width="24"
              height="24"
              viewBox="0 0 24 24"
              fill="none"
              stroke="var(--text2)"
              strokeWidth="1.2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M12 2C6.48 2 2 6.2 2 11.4c0 2.8 1.35 5.3 3.5 7L4.5 22l4.4-2.2C10 20.25 11 20.3 12 20.3c5.52 0 10-4.2 10-8.9S17.52 2 12 2z" />
            </svg>
          </div>

          <div className="space-y-2">
            <h2 className="text-2xl font-medium tracking-[-0.03em] text-text">
              {EMPTY_STATE_CONTENT.heading}
            </h2>
            <p className="mx-auto max-w-[380px] text-sm leading-7 text-text2">
              {EMPTY_STATE_CONTENT.sub}
            </p>
          </div>

          <div className="w-full max-w-[390px] space-y-2.5 text-left">
            {EMPTY_STATE_STEPS.map((step, index) => (
              <div
                key={step.title}
                className="card-surface flex items-start gap-3 rounded-card-lg px-4 py-3.5 transition hover:border-border2"
              >
                <div className="mt-0.5 flex h-[22px] w-[22px] shrink-0 items-center justify-center rounded-full border border-accentBorder bg-accentBg font-mono text-[11px] font-medium text-[#a0aaff]">
                  {index + 1}
                </div>
                <div>
                  <div className="text-[13px] font-medium text-text">{step.title}</div>
                  <p className="mt-0.5 text-xs leading-5 text-text3">{step.desc}</p>
                </div>
              </div>
            ))}
          </div>

          <button
            type="button"
            onClick={onOpenDrawer}
            className="flex items-center gap-2 rounded-card border border-accentBorder bg-accentBg px-5 py-2.5 text-sm text-[#a0aaff] transition hover:border-[#7580ff] hover:bg-[#5b6af033]"
          >
            <svg
              width="13"
              height="13"
              viewBox="0 0 14 14"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.3"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <rect x="2" y="2" width="10" height="10" rx="2" />
              <path d="M2 6h10M6 6v6" />
            </svg>
            Open sources panel
          </button>
        </section>
      ) : (
        <section
          ref={messagesRef}
          className="flex flex-1 flex-col gap-4 overflow-y-auto px-4 py-5 lg:px-6"
        >
          {messages.map((message) => {
            const isUser = message.role === "user";

            return (
              <article
                key={message.id}
                className={[
                  "flex items-start gap-3",
                  isUser ? "flex-row-reverse" : "",
                ].join(" ")}
              >
                <div
                  className={[
                    "flex h-[30px] w-[30px] shrink-0 items-center justify-center rounded-full border text-[11px] font-medium",
                    isUser
                      ? "border-border bg-bg3 text-text2"
                      : "border-accentBorder bg-accentBg font-mono text-[#a0aaff]",
                  ].join(" ")}
                >
                  {isUser ? "A" : "AI"}
                </div>

                <div className={isUser ? "items-end" : "items-start"}>
                  <div
                    className={[
                      "max-w-[min(72vw,680px)] whitespace-pre-wrap break-words rounded-xl border px-3.5 py-2.5 text-[13.5px] leading-[1.65]",
                      isUser
                        ? "rounded-tr-sm border-accentBorder bg-accentBg text-[#c8ccff]"
                        : "rounded-tl-sm border-border bg-bg2 text-text",
                    ].join(" ")}
                  >
                    {message.text}
                  </div>

                  {message.chips && message.chips.length > 0 ? (
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {message.chips.map((chip, index) => {
                        const parts = chip.ts.split(":").map(Number);
                        const seconds = parts.length === 2 ? parts[0] * 60 + parts[1] : parts[0];
                        const href = chip.url ? `${chip.url}&t=${seconds}s` : undefined;
                        const chipClass =
                          "inline-flex items-center gap-1 rounded-full border border-border2 bg-bg3 px-2.5 py-1 font-mono text-[11px] text-text2 transition hover:border-accentBorder hover:text-[#a0aaff]";
                        const label = chip.ts
                          ? chip.ts
                          : chip.pageNumber
                            ? `p.${chip.pageNumber}`
                            : null;
                        const inner = (
                          <>
                            {label ? (
                              <>
                                <span className="font-medium text-accent">{label}</span>
                                <span className="h-1 w-1 rounded-full bg-text3" />
                              </>
                            ) : null}
                            <span>{chip.title}</span>
                          </>
                        );
                        return href ? (
                          <a
                            key={`${chip.ts}-${chip.title}-${index}`}
                            href={href}
                            target="_blank"
                            rel="noopener noreferrer"
                            className={chipClass}
                          >
                            {inner}
                          </a>
                        ) : (
                          <span
                            key={`${chip.ts}-${chip.title}-${index}`}
                            className={chipClass}
                          >
                            {inner}
                          </span>
                        );
                      })}
                    </div>
                  ) : null}
                </div>
              </article>
            );
          })}
        </section>
      )}

      <footer className="flex items-center gap-2.5 border-t border-border px-4 py-3.5 lg:px-6">
        <input
          value={chatInput}
          onChange={(event) => onChatInputChange(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              onSendMessage();
            }
          }}
          disabled={!hasReadySource}
          placeholder={
            hasReadySource
              ? "Ask about your sources..."
              : "Add a source first to start chatting..."
          }
          className="h-10 flex-1 rounded-full border border-border2 bg-bg2 px-4 text-[13px] text-text outline-none transition placeholder:text-text3 focus:border-accentBorder disabled:cursor-not-allowed disabled:opacity-45"
        />

        <button
          type="button"
          onClick={onSendMessage}
          disabled={!hasReadySource || chatInput.trim().length === 0 || isSendingMessage}
          className={[
            "flex h-9 w-9 shrink-0 items-center justify-center rounded-full border transition",
            hasReadySource && chatInput.trim().length > 0 && !isSendingMessage
              ? "border-accentBorder bg-accentBg text-accent hover:bg-[#5b6af033]"
              : "cursor-not-allowed border-border2 bg-bg2 text-text3 opacity-45",
          ].join(" ")}
        >
          {isSendingMessage ? (
            <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-accent border-t-transparent" />
          ) : (
            <svg
              width="14"
              height="14"
              viewBox="0 0 14 14"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M7 11V3M3 7l4-4 4 4" />
            </svg>
          )}
        </button>
      </footer>
    </main>
  );
}
