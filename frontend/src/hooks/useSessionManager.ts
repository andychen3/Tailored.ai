import type { Dispatch } from "react";

import type { ChatSession, SourceItem } from "../types/chat";
import type { ChatAction } from "../state/chatReducer";
import { useChatHydration } from "./chat/useChatHydration";
import { useSessionActions } from "./chat/useSessionActions";
import { useSourceActions } from "./chat/useSourceActions";

export function useSessionManager(
  dispatch: Dispatch<ChatAction>,
  userId: string,
  sessions: ChatSession[],
  currentSessionId: string | null,
  sources: SourceItem[],
  isLargeScreen: boolean,
  setRequestError: (error: string | null) => void,
) {
  const { loadSessionMessages } = useChatHydration(dispatch, userId, setRequestError);
  const { deletingSessionId, selectSession, deleteSession } = useSessionActions(
    dispatch,
    sessions,
    currentSessionId,
    isLargeScreen,
    setRequestError,
    loadSessionMessages,
  );
  const { deletingSourceId, deleteSource } = useSourceActions(
    dispatch,
    sources,
    setRequestError,
  );

  return {
    deletingSourceId,
    deletingSessionId,
    selectSession,
    deleteSession,
    deleteSource,
    loadSessionMessages,
  };
}
