import { useCallback, useState } from "react";
import type { Dispatch } from "react";

import { createId, truncateSessionTitle } from "../lib/chatUtils";
import {
  createSession as createSessionApi,
  sendMessageStream,
  sendMessage as sendMessageApi,
  toUserFacingError,
} from "../lib/api";
import type { ChatSession, SourceChip } from "../types/chat";
import { toCreatedAtLabel } from "../lib/chatUtils";
import type { ChatAction } from "../state/chatReducer";

const DEFAULT_USER_ID = import.meta.env.VITE_DEFAULT_USER_ID ?? "default_user";
const ENABLE_STREAMING_CHAT = import.meta.env.VITE_ENABLE_STREAMING_CHAT !== "false";
const ZERO_USAGE = { promptTokens: 0, completionTokens: 0, totalTokens: 0 };

export function useSendMessage(
  dispatch: Dispatch<ChatAction>,
  chatInput: string,
  currentSessionId: string | null,
  hasReadySource: boolean,
  selectedModel: string,
  setRequestError: (error: string | null) => void,
) {
  const [isSendingMessage, setIsSendingMessage] = useState(false);

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
  }, [dispatch]);

  const sendMessage = useCallback(async () => {
    const userText = chatInput.trim();
    if (!userText || !hasReadySource || isSendingMessage) {
      return;
    }

    setRequestError(null);
    setIsSendingMessage(true);
    dispatch({ type: "SET_CHAT_INPUT", value: "" });

    let activeSessionId = currentSessionId;
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
    chatInput,
    currentSessionId,
    selectedModel,
    dispatch,
    setRequestError,
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
    } catch (error) {
      const message = toUserFacingError(error, "Failed to create chat thread.");
      setRequestError(message);
    }
  }, [createLocalSession, selectedModel, dispatch, setRequestError]);

  return { isSendingMessage, sendMessage, startNewChat };
}
