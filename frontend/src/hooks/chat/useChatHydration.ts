import { useCallback, useEffect } from "react";
import type { Dispatch } from "react";

import { createId, toCreatedAtLabel } from "../../lib/chatUtils";
import { getSession as getSessionApi, listSources, listSessions as listSessionsApi, toUserFacingError } from "../../lib/api";
import type { ChatSession, SourceItem } from "../../types/chat";
import type { ChatAction } from "../../state/chatReducer";
import { mapSessionDetailMessages } from "./messageMappers";

export function useChatHydration(
  dispatch: Dispatch<ChatAction>,
  userId: string,
  setRequestError: (error: string | null) => void,
) {
  const loadSessionMessages = useCallback(async (sessionId: string) => {
    try {
      const sessionDetail = await getSessionApi(sessionId);
      dispatch({
        type: "SET_SESSION_MESSAGES",
        sessionId,
        messages: mapSessionDetailMessages(sessionDetail),
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
        if (!isMounted) {
          return;
        }
        dispatch({
          type: "SET_SOURCES",
          sources: catalogSources.map((source): SourceItem => ({
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

    void hydrateSources();
    return () => {
      isMounted = false;
    };
  }, [dispatch, userId]);

  useEffect(() => {
    let isMounted = true;

    const hydrateSessions = async () => {
      try {
        const remoteSessions = await listSessionsApi(userId);
        if (!isMounted) {
          return;
        }
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

    void hydrateSessions();
    return () => {
      isMounted = false;
    };
  }, [dispatch, userId, loadSessionMessages, setRequestError]);

  return { loadSessionMessages };
}
