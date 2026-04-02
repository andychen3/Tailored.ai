import { useRef } from "react";
import type { SourceItem } from "../types/chat";
import { canDeleteSource } from "../lib/chatUtils";
import { getSourceStatusText, getProgressWidth } from "../lib/sourceFormatters";

type SourcesDrawerProps = {
  isOpen: boolean;
  sources: SourceItem[];
  urlInput: string;
  isAddingSource: boolean;
  deletingSourceId: string | null;
  onUrlInputChange: (value: string) => void;
  onAddSource: () => void;
  onDeleteSource: (sourceId: number) => void;
  onUploadFile: (file: File) => void;
  onClose: () => void;
};

export function SourcesDrawer({
  isOpen,
  sources,
  urlInput,
  isAddingSource,
  deletingSourceId,
  onUrlInputChange,
  onAddSource,
  onDeleteSource,
  onUploadFile,
  onClose,
}: SourcesDrawerProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  return (
    <aside
      className={[
        "absolute inset-y-0 right-0 z-30 flex flex-col overflow-hidden bg-bg2 transition-all duration-200 lg:relative",
        isOpen
          ? "w-[280px] translate-x-0 border-l border-border"
          : "w-0 translate-x-full border-l border-transparent lg:translate-x-0",
      ].join(" ")}
    >
      <div className="flex h-[58px] items-center justify-between border-b border-border px-3.5">
        <h2 className="text-sm font-medium text-text">Sources</h2>
        <button
          type="button"
          onClick={onClose}
          className="flex h-6 w-6 items-center justify-center rounded-md border border-border bg-transparent text-text3 transition hover:border-border2 hover:bg-bg3 hover:text-text"
        >
          <svg
            width="10"
            height="10"
            viewBox="0 0 10 10"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
          >
            <path d="M2 2l6 6M8 2l-6 6" />
          </svg>
        </button>
      </div>

      <div className="flex-1 space-y-5 overflow-y-auto px-2.5 py-3.5">
        <section>
          <div className="px-1 text-[10px] font-medium uppercase tracking-[0.08em] text-text3">
            Add source
          </div>

          <div className="mt-2 flex gap-1.5 px-1">
            <input
              value={urlInput}
              onChange={(event) => onUrlInputChange(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  onAddSource();
                }
              }}
              disabled={isAddingSource}
              placeholder="YouTube URL..."
              className="h-8 flex-1 rounded-card border border-border2 bg-bg3 px-2.5 text-xs text-text outline-none transition placeholder:text-text3 focus:border-accentBorder"
            />
            <button
              type="button"
              onClick={onAddSource}
              disabled={isAddingSource}
              className="rounded-card border border-border2 bg-bg3 px-3 text-xs text-text transition hover:bg-bg4 disabled:cursor-not-allowed disabled:opacity-45"
            >
              {isAddingSource ? "Adding..." : "Add"}
            </button>
          </div>

          <div className="my-2 flex items-center gap-2 px-1">
            <div className="h-px flex-1 bg-border" />
            <span className="text-[10px] text-text3">or</span>
            <div className="h-px flex-1 bg-border" />
          </div>

          <input
            ref={fileInputRef}
            type="file"
            accept=".mp4,.mov,.avi,.pdf,.txt"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) {
                onUploadFile(file);
                e.target.value = "";
              }
            }}
          />
          <button
            type="button"
            disabled={isAddingSource}
            onClick={() => fileInputRef.current?.click()}
            className="mx-1 flex w-[calc(100%-8px)] items-center justify-center gap-1.5 rounded-card border border-dashed border-border2 bg-transparent px-2 py-2 text-xs text-text2 transition hover:border-accentBorder hover:bg-accentBg hover:text-[#a0aaff] disabled:cursor-not-allowed disabled:opacity-45"
          >
            <svg
              width="12"
              height="12"
              viewBox="0 0 14 14"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.3"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M7 10V3M4 6l3-3 3 3" />
              <path d="M2 12h10" />
            </svg>
            Upload file
          </button>
        </section>

        <section>
          <div className="px-1 text-[10px] font-medium uppercase tracking-[0.08em] text-text3">
            Your library
          </div>

          {sources.length === 0 ? (
            <div className="mx-1 mt-2 flex flex-col items-center gap-2 rounded-card-lg border border-dashed border-border px-3 py-7 text-center">
              <svg
                width="20"
                height="20"
                viewBox="0 0 20 20"
                fill="none"
                stroke="var(--text3)"
                strokeWidth="1.1"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <rect x="2" y="2" width="16" height="16" rx="3" />
                <path d="M7 10h6M10 7v6" />
              </svg>
              <p className="text-xs font-medium text-text2">No sources yet</p>
              <span className="text-[11px] leading-5 text-text3">
                Paste a YouTube URL or upload a file above to get started
              </span>
            </div>
          ) : (
            <div className="mt-2 space-y-1.5">
              {sources.map((source) => {
                const isReady = source.status === "ready";
                const isMissing = source.syncStatus === "missing";
                const isDeleting = deletingSourceId === source.sourceId;
                const canDelete = canDeleteSource(source);
                return (
                  <article
                    key={source.id}
                    className={[
                      "group rounded-card border px-3 py-2.5 transition",
                      isReady && !isMissing
                        ? "border-accentBorder bg-accentBg"
                        : "border-border bg-bg3 hover:border-border2",
                    ].join(" ")}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div
                        className={[
                          "min-w-0 truncate text-xs font-medium",
                          isReady && !isMissing ? "text-[#c8ccff]" : "text-text",
                        ].join(" ")}
                      >
                        {source.title}
                      </div>

                      {canDelete ? (
                        <button
                          type="button"
                          aria-label={`Delete ${source.title}`}
                          disabled={isDeleting}
                          onClick={(event) => {
                            event.stopPropagation();
                            onDeleteSource(source.id);
                          }}
                          className={[
                            "flex h-6 w-6 shrink-0 items-center justify-center rounded-md border transition",
                            isDeleting
                              ? "cursor-not-allowed border-border2 bg-bg2 text-text3 opacity-50"
                              : [
                                  "border-border2 bg-transparent text-text3",
                                  "hover:border-red/40 hover:bg-red/10 hover:text-red",
                                  "opacity-80 group-hover:opacity-100 group-focus-within:opacity-100",
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

                    <div
                      className={[
                        "mt-0.5 truncate text-[11px]",
                        isReady && !isMissing ? "text-[#a0aaff99]" : "text-text3",
                      ].join(" ")}
                    >
                      {source.url}
                    </div>

                    <div className="mt-1.5 flex items-center gap-1.5">
                      <span
                        className={[
                          "h-1.5 w-1.5 rounded-full",
                          source.status === "uploading" ||
                          source.status === "queued" ||
                          source.status === "processing"
                            ? "animate-pulseSoft bg-amber"
                            : source.syncStatus === "missing"
                              ? "bg-red"
                            : source.status === "error"
                              ? "bg-red"
                              : "bg-green",
                        ].join(" ")}
                      />

                      <span
                        className={[
                          "font-mono text-[11px]",
                          source.status === "uploading" ||
                          source.status === "queued" ||
                          source.status === "processing"
                            ? "text-amber"
                            : source.syncStatus === "missing"
                              ? "text-red"
                            : source.status === "error"
                              ? "text-red"
                              : "text-green",
                        ].join(" ")}
                      >
                        {getSourceStatusText(source)}
                      </span>
                    </div>

                    {source.status === "error" && source.errorMessage ? (
                      <p className="mt-1.5 text-[11px] leading-4 text-red">{source.errorMessage}</p>
                    ) : null}

                    {source.status === "uploading" ||
                    source.status === "queued" ||
                    source.status === "processing" ? (
                      <div className="mt-1.5 h-0.5 overflow-hidden rounded-full bg-border2">
                        <div
                          className="h-full rounded-full bg-amber"
                          style={{ width: getProgressWidth(source) }}
                        />
                      </div>
                    ) : null}
                  </article>
                );
              })}
            </div>
          )}
        </section>
      </div>
    </aside>
  );
}
