import { useCallback, useEffect, useMemo, useReducer, useState } from "react";

import { DEFAULT_SESSION_TITLE } from "../constants/chatUi";
import { createId, detectSourceTitle, truncateSessionTitle } from "../lib/chatUtils";
import {
  createSession as createSessionApi,
  getSession as getSessionApi,
  getIngestJob,
  ingestFile,
  ingestYoutube,
  listModels,
  listSources,
  listSessions as listSessionsApi,
  sendMessageStream,
  sendMessage as sendMessageApi,
  toUserFacingError,
} from "../lib/api";
import type { SourceType } from "../types/chat";
import { chatReducer, createInitialChatState } from "../state/chatReducer";
import type { ChatSession, SourceChip } from "../types/chat";

const DEFAULT_USER_ID = import.meta.env.VITE_DEFAULT_USER_ID ?? "default_user";
const DEFAULT_MODEL = import.meta.env.VITE_OPENAI_MODEL ?? "gpt-4o-mini";
const ENABLE_STREAMING_CHAT = import.meta.env.VITE_ENABLE_STREAMING_CHAT !== "false";
const INGEST_POLL_INTERVAL_MS = 1500;
const ZERO_USAGE = { promptTokens: 0, completionTokens: 0, totalTokens: 0 };

function detectFileSourceType(fileName: string): SourceType | undefined {
  const extension = fileName.split(".").pop()?.toLowerCase();
  if (extension === "mp4" || extension === "mov" || extension === "avi") {
    return "video_file";
  }
  if (extension === "pdf") {
    return "pdf";
  }
  if (extension === "txt") {
    return "text";
  }
  return undefined;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function toCreatedAtLabel(isoDate: string): string {
  const createdAt = new Date(isoDate);
  const now = new Date();
  if (
    createdAt.getFullYear() === now.getFullYear() &&
    createdAt.getMonth() === now.getMonth() &&
    createdAt.getDate() === now.getDate()
  ) {
    return "Today";
  }
  return createdAt.toLocaleDateString();
}

export function useChatController() {
  const initialIsLarge = typeof window !== "undefined" ? window.innerWidth >= 1024 : true;

  const [state, dispatch] = useReducer(chatReducer, initialIsLarge, createInitialChatState);
  const [isAddingSource, setIsAddingSource] = useState(false);
  const [isSendingMessage, setIsSendingMessage] = useState(false);
  const [requestError, setRequestError] = useState<string | null>(null);
  const [availableModels, setAvailableModels] = useState<string[]>([DEFAULT_MODEL]);
  const [modelTokenLimits, setModelTokenLimits] = useState<Record<string, number>>({});
  const [selectedModel, setSelectedModel] = useState(DEFAULT_MODEL);

  useEffect(() => {
    let isMounted = true;
    const hydrateModels = async () => {
      try {
        const models = await listModels();
        if (!isMounted) return;
        const ids = models.map((item) => item.id);
        const limits: Record<string, number> = {};
        models.forEach((model) => {
          if (typeof model.max_context_tokens === "number" && model.max_context_tokens > 0) {
            limits[model.id] = model.max_context_tokens;
          }
        });
        setModelTokenLimits(limits);
        if (ids.length > 0) {
          setAvailableModels(ids);
          if (ids.includes(DEFAULT_MODEL)) {
            setSelectedModel(DEFAULT_MODEL);
          } else {
            setSelectedModel(ids[0]);
          }
        }
      } catch {
        // Fallback to default model in UI when listing fails.
      }
    };
    hydrateModels();
    return () => {
      isMounted = false;
    };
  }, []);

  useEffect(() => {
    let isMounted = true;

    const hydrateSources = async () => {
      try {
        const catalogSources = await listSources(DEFAULT_USER_ID);
        if (!isMounted) return;
        dispatch({
          type: "SET_SOURCES",
          sources: catalogSources.map((source) => ({
            id: createId(),
            sourceId: source.source_id,
            url: source.source_url ?? source.title,
            title: source.title,
            status: "ready",
            chunks: source.expected_chunk_count,
            sourceType: source.source_type,
            videoId: source.video_id ?? undefined,
            fileId: source.file_id ?? undefined,
            syncStatus: source.sync_status,
          })),
        });
      } catch {
        // Source hydration should not block chat app startup.
      }
    };

    hydrateSources();
    return () => {
      isMounted = false;
    };
  }, []);

  useEffect(() => {
    const handleResize = () => {
      dispatch({
        type: "SET_SCREEN_SIZE",
        isLargeScreen: window.innerWidth >= 1024,
      });
    };

    window.addEventListener("resize", handleResize);
    return () => {
      window.removeEventListener("resize", handleResize);
    };
  }, []);

  const loadSessionMessages = useCallback(async (sessionId: string) => {
    try {
      const sessionDetail = await getSessionApi(sessionId);
      const messages = sessionDetail.messages.map((message) => ({
        id: message.id,
        role: message.role,
        text: message.content,
        chips: (message.sources ?? []).map((source) => ({
          ts: source.timestamp,
          title: source.title || "Source",
          videoId: source.video_id,
          url: source.url,
          pageNumber: source.page_number,
        })),
        usage: message.usage
          ? {
              promptTokens: message.usage.prompt_tokens,
              completionTokens: message.usage.completion_tokens,
              totalTokens: message.usage.total_tokens,
            }
          : undefined,
      }));
      dispatch({
        type: "SET_SESSION_MESSAGES",
        sessionId,
        messages,
      });
      dispatch({
        type: "UPDATE_SESSION_TITLE",
        sessionId,
        title: sessionDetail.session.title,
      });
      dispatch({
        type: "UPDATE_SESSION_MODEL",
        sessionId,
        model: sessionDetail.session.model,
      });
      dispatch({
        type: "UPDATE_SESSION_USAGE",
        sessionId,
        promptTokens: sessionDetail.session.prompt_tokens_total,
        completionTokens: sessionDetail.session.completion_tokens_total,
        totalTokens: sessionDetail.session.total_tokens_total,
      });
    } catch (error) {
      const message = toUserFacingError(error, "Failed to load chat history.");
      setRequestError(message);
    }
  }, []);

  useEffect(() => {
    let isMounted = true;

    const hydrateSessions = async () => {
      try {
        const remoteSessions = await listSessionsApi(DEFAULT_USER_ID);
        if (!isMounted) return;
        const mappedSessions: ChatSession[] = remoteSessions.map((session) => ({
          id: session.session_id,
          title: session.title,
          model: session.model,
          createdAtLabel: toCreatedAtLabel(session.created_at),
          tokenUsage: {
            promptTokens: session.prompt_tokens_total,
            completionTokens: session.completion_tokens_total,
            totalTokens: session.total_tokens_total,
          },
          messages: [],
        }));
        const firstSessionId = mappedSessions[0]?.id ?? null;
        dispatch({
          type: "SET_SESSIONS",
          sessions: mappedSessions,
          currentSessionId: firstSessionId,
        });
        if (firstSessionId) {
          await loadSessionMessages(firstSessionId);
        }
      } catch (error) {
        const message = toUserFacingError(error, "Failed to load chat sessions.");
        setRequestError(message);
      }
    };

    hydrateSessions();
    return () => {
      isMounted = false;
    };
  }, [loadSessionMessages]);

  const hasReadySource = useMemo(
    () => state.sources.some((source) => source.status === "ready" && source.syncStatus !== "missing"),
    [state.sources],
  );

  const currentSession = useMemo(
    () => state.sessions.find((session) => session.id === state.currentSessionId) ?? null,
    [state.sessions, state.currentSessionId],
  );

  const chatTitle = currentSession?.title ?? DEFAULT_SESSION_TITLE;
  const chatMessages = currentSession?.messages ?? [];
  const threadTokenUsage = currentSession?.tokenUsage ?? ZERO_USAGE;
  const threadTokenLimit = modelTokenLimits[selectedModel] ?? null;
  const showEmptyState = chatMessages.length === 0;

  const toggleNav = useCallback(() => {
    dispatch({ type: "TOGGLE_NAV" });
  }, []);

  const toggleDrawer = useCallback(() => {
    dispatch({ type: "TOGGLE_DRAWER" });
  }, []);

  const openDrawer = useCallback(() => {
    dispatch({ type: "OPEN_DRAWER" });
  }, []);

  const closeDrawer = useCallback(() => {
    dispatch({ type: "CLOSE_DRAWER" });
  }, []);

  const closePanels = useCallback(() => {
    dispatch({ type: "CLOSE_PANELS" });
  }, []);

  const setUrlInput = useCallback((value: string) => {
    dispatch({ type: "SET_URL_INPUT", value });
  }, []);

  const setChatInput = useCallback((value: string) => {
    dispatch({ type: "SET_CHAT_INPUT", value });
  }, []);

  const uploadFile = useCallback(
    async (file: File) => {
      if (isAddingSource) return;

      setRequestError(null);
      setIsAddingSource(true);

      const sourceId = createId();
      dispatch({
        type: "ADD_SOURCE",
        source: {
          id: sourceId,
          url: file.name,
          title: file.name,
          status: "uploading",
          chunks: 0,
          sourceType: detectFileSourceType(file.name),
          syncStatus: "unknown",
          uploadPercent: 0,
        },
      });

      try {
        const result = await ingestFile(DEFAULT_USER_ID, file, (uploadPercent) => {
          dispatch({
            type: "UPDATE_SOURCE_UPLOAD",
            sourceId,
            uploadPercent,
          });
        });

        dispatch({
          type: "MARK_SOURCE_QUEUED",
          sourceId,
          jobId: result.job_id,
          sourceType: result.source_type as SourceType,
        });

        while (true) {
          const job = await getIngestJob(result.job_id);

          if (job.status === "queued") {
            dispatch({
              type: "MARK_SOURCE_QUEUED",
              sourceId,
              jobId: job.job_id,
              sourceType: job.source_type as SourceType,
            });
          } else if (job.status === "processing") {
            dispatch({
              type: "MARK_SOURCE_PROCESSING",
              sourceId,
              jobId: job.job_id,
              sourceType: job.source_type as SourceType,
            });
          } else if (job.status === "ready") {
            dispatch({
              type: "MARK_SOURCE_READY",
              sourceId,
              chunks: job.chunks_ingested ?? 0,
              videoId: "",
              title: job.file_name,
              fileId: job.file_id ?? undefined,
              sourceType: job.source_type as SourceType,
            });
            break;
          } else {
            throw new Error(job.error_message ?? "File ingestion failed.");
          }

          await sleep(INGEST_POLL_INTERVAL_MS);
        }
      } catch (error) {
        const message = toUserFacingError(error, "Failed to upload file.");
        dispatch({ type: "MARK_SOURCE_ERROR", sourceId, errorMessage: message });
        setRequestError(message);
      } finally {
        setIsAddingSource(false);
      }
    },
    [isAddingSource],
  );

  const addSource = useCallback(async () => {
    const url = state.urlInput.trim();
    if (!url || isAddingSource) {
      return;
    }

    setRequestError(null);
    setIsAddingSource(true);

    const sourceId = createId();
    dispatch({
      type: "ADD_SOURCE",
      source: {
        id: sourceId,
        url,
        title: detectSourceTitle(url),
        status: "processing",
        chunks: 0,
        sourceType: "youtube",
        syncStatus: "unknown",
      },
    });

    try {
      const result = await ingestYoutube({
        userId: DEFAULT_USER_ID,
        url,
      });

      dispatch({
        type: "MARK_SOURCE_READY",
        sourceId,
        chunks: result.chunks_ingested,
        videoId: result.video_id,
        title: result.video_title,
        sourceType: "youtube",
      });
    } catch (error) {
      const message = toUserFacingError(error, "Failed to add source.");
      dispatch({
        type: "MARK_SOURCE_ERROR",
        sourceId,
        errorMessage: message,
      });
      setRequestError(message);
    } finally {
      setIsAddingSource(false);
    }
  }, [isAddingSource, state.urlInput]);

  const createLocalSession = useCallback((
    sessionId: string,
    title: string,
    model: string,
    createdAt: string | null = null,
  ) => {
    const session: ChatSession = {
      id: sessionId,
      title: truncateSessionTitle(title),
      model,
      createdAtLabel: createdAt ? toCreatedAtLabel(createdAt) : "Today",
      tokenUsage: ZERO_USAGE,
      messages: [],
    };

    dispatch({ type: "CREATE_SESSION", session });
    return sessionId;
  }, []);

  const sendMessage = useCallback(async () => {
    const userText = state.chatInput.trim();
    if (!userText || !hasReadySource || isSendingMessage) {
      return;
    }

    setRequestError(null);
    setIsSendingMessage(true);
    dispatch({ type: "SET_CHAT_INPUT", value: "" });

    let activeSessionId = state.currentSessionId;
    const isNewSession = !activeSessionId;
    const useStreamingChat = ENABLE_STREAMING_CHAT;
    let assistantMessageId = 0;
    let assistantText = "";
    let streamingAssistantVisible = false;
    let sessionId = "";

    try {
      if (!activeSessionId) {
        const createdSession = await createSessionApi({
          userId: DEFAULT_USER_ID,
          model: selectedModel,
        });
        activeSessionId = createLocalSession(
          createdSession.session_id,
          createdSession.title || userText,
          createdSession.model,
          createdSession.created_at ?? null,
        );
      }

      sessionId = activeSessionId;
      if (!sessionId) {
        throw new Error("Missing session id.");
      }

      const userMessageId = createId();
      dispatch({
        type: "APPEND_MESSAGE",
        sessionId,
        message: {
          id: userMessageId,
          role: "user",
          text: userText,
        },
      });

      if (isNewSession) {
        dispatch({
          type: "UPDATE_SESSION_TITLE",
          sessionId,
          title: truncateSessionTitle(userText),
        });
      }

      if (!useStreamingChat) {
        const response = await sendMessageApi({
          sessionId,
          message: userText,
        });

        const chips: SourceChip[] = response.sources.map((source) => ({
          ts: source.timestamp,
          title: source.title || "Source",
          videoId: source.video_id,
          url: source.url,
          pageNumber: source.page_number,
        }));

        dispatch({
          type: "APPEND_MESSAGE",
          sessionId,
          message: {
            id: createId(),
            role: "assistant",
            text: response.reply,
            chips,
            usage: response.usage
              ? {
                  promptTokens: response.usage.prompt_tokens,
                  completionTokens: response.usage.completion_tokens,
                  totalTokens: response.usage.total_tokens,
                }
              : undefined,
          },
        });
        if (response.thread_usage) {
          dispatch({
            type: "UPDATE_SESSION_USAGE",
            sessionId,
            promptTokens: response.thread_usage.prompt_tokens,
            completionTokens: response.thread_usage.completion_tokens,
            totalTokens: response.thread_usage.total_tokens,
          });
        }
        return;
      }

      assistantMessageId = createId();
      streamingAssistantVisible = true;
      dispatch({
        type: "APPEND_MESSAGE",
        sessionId,
        message: {
          id: assistantMessageId,
          role: "assistant",
          text: "",
          isStreaming: true,
        },
      });

      await sendMessageStream(
        {
          sessionId,
          message: userText,
        },
        {
          onDelta: (delta) => {
            assistantText += delta;
            dispatch({
              type: "UPDATE_MESSAGE",
              sessionId,
              messageId: assistantMessageId,
              patch: {
                text: assistantText,
                isStreaming: true,
              },
            });
          },
          onCompletion: (result) => {
            const chips: SourceChip[] = result.sources.map((source) => ({
              ts: source.timestamp,
              title: source.title || "Source",
              videoId: source.video_id,
              url: source.url,
              pageNumber: source.page_number,
            }));

            assistantText = result.reply;
            streamingAssistantVisible = false;
            dispatch({
              type: "UPDATE_MESSAGE",
              sessionId,
              messageId: assistantMessageId,
              patch: {
                id: result.assistant_message_id || assistantMessageId,
                text: result.reply,
                chips,
                usage: result.usage
                  ? {
                      promptTokens: result.usage.prompt_tokens,
                      completionTokens: result.usage.completion_tokens,
                      totalTokens: result.usage.total_tokens,
                    }
                  : undefined,
                isStreaming: false,
              },
            });

            if (result.thread_usage) {
              dispatch({
                type: "UPDATE_SESSION_USAGE",
                sessionId,
                promptTokens: result.thread_usage.prompt_tokens,
                completionTokens: result.thread_usage.completion_tokens,
                totalTokens: result.thread_usage.total_tokens,
              });
            }
          },
        },
      );
    } catch (error) {
      const message = toUserFacingError(error, "Failed to send message.");
      setRequestError(message);

      if (sessionId && streamingAssistantVisible && assistantMessageId !== 0) {
        dispatch({
          type: "UPDATE_MESSAGE",
          sessionId,
          messageId: assistantMessageId,
          patch: {
            text: `I hit an error while contacting the backend: ${message}`,
            isStreaming: false,
          },
        });
      } else if (sessionId) {
        dispatch({
          type: "APPEND_MESSAGE",
          sessionId,
          message: {
            id: createId(),
            role: "assistant",
            text: `I hit an error while contacting the backend: ${message}`,
          },
        });
      }
    } finally {
      setIsSendingMessage(false);
    }
  }, [
    createLocalSession,
    hasReadySource,
    isSendingMessage,
    state.chatInput,
    state.currentSessionId,
    selectedModel,
  ]);

  const startNewChat = useCallback(async () => {
    try {
      const createdSession = await createSessionApi({
        userId: DEFAULT_USER_ID,
        model: selectedModel,
      });
      createLocalSession(
        createdSession.session_id,
        createdSession.title || "New chat",
        createdSession.model,
        createdSession.created_at ?? null,
      );
      dispatch({ type: "SET_CHAT_INPUT", value: "" });
      setRequestError(null);
      if (!state.isLargeScreen) {
        dispatch({ type: "CLOSE_PANELS" });
      }
    } catch (error) {
      const message = toUserFacingError(error, "Failed to create chat thread.");
      setRequestError(message);
    }
  }, [createLocalSession, selectedModel, state.isLargeScreen]);

  const selectSession = useCallback(
    async (sessionId: string) => {
      dispatch({ type: "SET_CURRENT_SESSION", sessionId });
      await loadSessionMessages(sessionId);
      if (!state.isLargeScreen) {
        dispatch({ type: "CLOSE_NAV" });
      }
    },
    [loadSessionMessages, state.isLargeScreen],
  );

  return {
    isLargeScreen: state.isLargeScreen,
    isNavOpen: state.isNavOpen,
    isDrawerOpen: state.isDrawerOpen,
    hasReadySource,
    sessions: state.sessions,
    currentSessionId: state.currentSessionId,
    chatTitle,
    chatMessages,
    showEmptyState,
    chatInput: state.chatInput,
    sources: state.sources,
    urlInput: state.urlInput,
    isAddingSource,
    isSendingMessage,
    requestError,
    availableModels,
    selectedModel,
    setSelectedModel,
    threadTokenUsage,
    threadTokenLimit,
    toggleNav,
    toggleDrawer,
    openDrawer,
    closeDrawer,
    closePanels,
    setUrlInput,
    setChatInput,
    addSource,
    uploadFile,
    sendMessage,
    startNewChat,
    selectSession,
  };
}
