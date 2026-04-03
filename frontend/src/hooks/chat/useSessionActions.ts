import { useCallback, useState } from "react";
import type { Dispatch } from "react";

import { deleteSession as deleteSessionApi, toUserFacingError } from "../../lib/api";
import type { ChatSession } from "../../types/chat";
import type { ChatAction } from "../../state/chatReducer";

export function useSessionActions(
  dispatch: Dispatch<ChatAction>,
  sessions: ChatSession[],
  currentSessionId: string | null,
  isLargeScreen: boolean,
  setRequestError: (error: string | null) => void,
  loadSessionMessages: (sessionId: string) => Promise<void>,
) {
  const [deletingSessionId, setDeletingSessionId] = useState<string | null>(null);

  const selectSession = useCallback(async (sessionId: string) => {
    dispatch({ type: "SET_CURRENT_SESSION", sessionId });
    await loadSessionMessages(sessionId);
    if (!isLargeScreen) {
      dispatch({ type: "CLOSE_NAV" });
    }
  }, [dispatch, isLargeScreen, loadSessionMessages]);

  const deleteSession = useCallback(async (sessionId: string) => {
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

    const nextCandidate = sessions[targetIndex + 1]?.id ?? sessions[targetIndex - 1]?.id ?? null;
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
  }, [
    currentSessionId,
    deletingSessionId,
    dispatch,
    isLargeScreen,
    loadSessionMessages,
    sessions,
    setRequestError,
  ]);

  return { deletingSessionId, selectSession, deleteSession };
}
