import { useCallback, useState } from "react";
import type { Dispatch } from "react";

import { DEFAULT_USER_ID } from "../constants/chatRuntime";
import { createSession as createSessionApi, toUserFacingError } from "../lib/api";
import { mapCreatedSessionResult } from "./chat/messageMappers";
import { runSendMessageFlow } from "./chat/sendMessageFlow";
import type { ChatAction } from "../state/chatReducer";

export function useSendMessage(
  dispatch: Dispatch<ChatAction>,
  chatInput: string,
  currentSessionId: string | null,
  hasReadySource: boolean,
  selectedModel: string,
  setRequestError: (error: string | null) => void,
) {
  const [isSendingMessage, setIsSendingMessage] = useState(false);

  const sendMessage = useCallback(async () => {
    setIsSendingMessage(true);
    try {
      await runSendMessageFlow({
        dispatch,
        chatInput,
        currentSessionId,
        hasReadySource,
        selectedModel,
        isSendingMessage,
        setRequestError,
      });
    } finally {
      setIsSendingMessage(false);
    }
  }, [
    dispatch,
    chatInput,
    currentSessionId,
    hasReadySource,
    selectedModel,
    isSendingMessage,
    setRequestError,
  ]);

  const startNewChat = useCallback(async () => {
    try {
      const createdSession = await createSessionApi({
        userId: DEFAULT_USER_ID,
        model: selectedModel,
      });
      dispatch({
        type: "CREATE_SESSION",
        session: mapCreatedSessionResult(createdSession, "New chat"),
      });
      dispatch({ type: "SET_CHAT_INPUT", value: "" });
      setRequestError(null);
    } catch (error) {
      const message = toUserFacingError(error, "Failed to create chat thread.");
      setRequestError(message);
    }
  }, [dispatch, selectedModel, setRequestError]);

  return { isSendingMessage, sendMessage, startNewChat };
}
