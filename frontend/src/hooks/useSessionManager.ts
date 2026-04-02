import { useCallback, useEffect, useState } from "react";
import type { Dispatch } from "react";

import { createId, toCreatedAtLabel } from "../lib/chatUtils";
import {
  deleteSource as deleteSourceApi,
  deleteSession as deleteSessionApi,
  getSession as getSessionApi,
  listSources,
  listSessions as listSessionsApi,
  toUserFacingError,
} from "../lib/api";
import { canDeleteSource } from "../lib/chatUtils";
import type { ChatSession, SourceItem } from "../types/chat";
import type { ChatAction } from "../state/chatReducer";

export function useSessionManager(
  dispatch: Dispatch<ChatAction>,
  userId: string,
  sessions: ChatSession[],
  currentSessionId: string | null,
  sources: SourceItem[],
  isLargeScreen: boolean,
  setRequestError: (error: string | null) => void,
) {
  const [deletingSourceId, setDeletingSourceId] = useState<string | null>(null);
  const [deletingSessionId, setDeletingSessionId] = useState<string | null>(null);

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
  }, [dispatch, setRequestError]);

  useEffect(() => {
    let isMounted = true;

    const hydrateSources = async () => {
      try {
        const catalogSources = await listSources(userId);
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
  }, [dispatch, userId]);

  useEffect(() => {
    let isMounted = true;

    const hydrateSessions = async () => {
      try {
        const remoteSessions = await listSessionsApi(userId);
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
  }, [dispatch, userId, loadSessionMessages, setRequestError]);

  const selectSession = useCallback(
    async (sessionId: string) => {
      dispatch({ type: "SET_CURRENT_SESSION", sessionId });
      await loadSessionMessages(sessionId);
      if (!isLargeScreen) {
        dispatch({ type: "CLOSE_NAV" });
      }
    },
    [dispatch, loadSessionMessages, isLargeScreen],
  );

  const deleteSession = useCallback(
    async (sessionId: string) => {
      const targetIndex = sessions.findIndex((session) => session.id === sessionId);
      if (targetIndex === -1 || deletingSessionId) {
        return;
      }

      const confirmed = window.confirm("Delete this conversation? This cannot be undone.");
      if (!confirmed) {
        return;
      }

      setRequestError(null);
      setDeletingSessionId(sessionId);

      const nextCandidate =
        sessions[targetIndex + 1]?.id ??
        sessions[targetIndex - 1]?.id ??
        null;
      const isActiveSession = currentSessionId === sessionId;

      try {
        await deleteSessionApi(sessionId);
        dispatch({
          type: "DELETE_SESSION",
          sessionId,
          nextSessionId: isActiveSession ? nextCandidate : currentSessionId,
        });

        if (isActiveSession && nextCandidate) {
          await loadSessionMessages(nextCandidate);
        }

        if (!isLargeScreen && sessions.length === 1) {
          dispatch({ type: "CLOSE_NAV" });
        }
      } catch (error) {
        const message = toUserFacingError(error, "Failed to delete chat thread.");
        setRequestError(message);
      } finally {
        setDeletingSessionId(null);
      }
    },
    [
      deletingSessionId,
      loadSessionMessages,
      currentSessionId,
      isLargeScreen,
      sessions,
      dispatch,
      setRequestError,
    ],
  );

  const deleteSource = useCallback(
    async (localSourceId: number) => {
      const source = sources.find((item) => item.id === localSourceId);
      if (!source || deletingSourceId || !canDeleteSource(source)) {
        return;
      }

      const confirmed = window.confirm("Delete this source? This cannot be undone.");
      if (!confirmed) {
        return;
      }

      setRequestError(null);
      setDeletingSourceId(source.sourceId ?? null);

      try {
        await deleteSourceApi(source.sourceId!);
        dispatch({ type: "REMOVE_SOURCE", sourceId: localSourceId });
      } catch (error) {
        const message = toUserFacingError(error, "Failed to delete source.");
        setRequestError(message);
      } finally {
        setDeletingSourceId(null);
      }
    },
    [deletingSourceId, sources, dispatch, setRequestError],
  );

  return {
    deletingSourceId,
    deletingSessionId,
    selectSession,
    deleteSession,
    deleteSource,
  };
}
