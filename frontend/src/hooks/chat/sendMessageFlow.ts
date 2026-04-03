import type { Dispatch } from "react";

import { createId, truncateSessionTitle } from "../../lib/chatUtils";
import { sendMessage as sendMessageApi, sendMessageStream, toUserFacingError } from "../../lib/api";
import type { ChatAction } from "../../state/chatReducer";
import { ensureSession } from "./sessionBootstrap";
import { mapApiUsage, mapAssistantAction, mapSourceChip } from "./messageMappers";

const ENABLE_STREAMING_CHAT = import.meta.env.VITE_ENABLE_STREAMING_CHAT !== "false";

type SendMessageFlowParams = {
  dispatch: Dispatch<ChatAction>;
  chatInput: string;
  currentSessionId: string | null;
  hasReadySource: boolean;
  selectedModel: string;
  isSendingMessage: boolean;
  setRequestError: (error: string | null) => void;
};

export async function runSendMessageFlow({
  dispatch,
  chatInput,
  currentSessionId,
  hasReadySource,
  selectedModel,
  isSendingMessage,
  setRequestError,
}: SendMessageFlowParams): Promise<void> {
  const userText = chatInput.trim();
  if (!userText || !hasReadySource || isSendingMessage) {
    return;
  }

  setRequestError(null);
  dispatch({ type: "SET_CHAT_INPUT", value: "" });

  let assistantMessageId: number | string = 0;
  let assistantText = "";
  let streamingAssistantVisible = false;
  let sessionId = "";

  try {
    const sessionBootstrap = await ensureSession({
      currentSessionId,
      selectedModel,
      userText,
      dispatch,
    });
    sessionId = sessionBootstrap.sessionId;

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

    if (sessionBootstrap.isNewSession) {
      dispatch({
        type: "UPDATE_SESSION_TITLE",
        sessionId,
        title: truncateSessionTitle(userText),
      });
    }

    if (!ENABLE_STREAMING_CHAT) {
      const response = await sendMessageApi({
        sessionId,
        message: userText,
      });

      dispatch({
        type: "APPEND_MESSAGE",
        sessionId,
        message: {
          id: createId(),
          role: "assistant",
          text: response.reply,
          chips: response.sources.map(mapSourceChip),
          action: mapAssistantAction(response.action),
          usage: mapApiUsage(response.usage),
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
          assistantText = result.reply;
          streamingAssistantVisible = false;
          dispatch({
            type: "UPDATE_MESSAGE",
            sessionId,
            messageId: assistantMessageId,
            patch: {
              id: result.assistant_message_id || assistantMessageId,
              text: result.reply,
              chips: result.sources.map(mapSourceChip),
              action: mapAssistantAction(result.action),
              usage: mapApiUsage(result.usage),
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
      return;
    }

    if (sessionId) {
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
  }
}
