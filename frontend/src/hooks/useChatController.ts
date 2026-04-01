import { useCallback, useEffect, useMemo, useReducer, useState } from "react";

import { DEFAULT_SESSION_TITLE } from "../constants/chatUi";
import { createId, detectSourceTitle, truncateSessionTitle } from "../lib/chatUtils";
import {
  createSession as createSessionApi,
  ingestYoutube,
  sendMessage as sendMessageApi,
  toUserFacingError,
} from "../lib/api";
import { chatReducer, createInitialChatState } from "../state/chatReducer";
import type { ChatSession, SourceChip } from "../types/chat";

const DEFAULT_USER_ID = import.meta.env.VITE_DEFAULT_USER_ID ?? "default_user";
const DEFAULT_MODEL = import.meta.env.VITE_OPENAI_MODEL ?? "gpt-4o-mini";

export function useChatController() {
  const initialIsLarge = typeof window !== "undefined" ? window.innerWidth >= 1024 : true;

  const [state, dispatch] = useReducer(chatReducer, initialIsLarge, createInitialChatState);
  const [isAddingSource, setIsAddingSource] = useState(false);
  const [isSendingMessage, setIsSendingMessage] = useState(false);
  const [requestError, setRequestError] = useState<string | null>(null);

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

  const hasReadySource = useMemo(
    () => state.sources.some((source) => source.status === "ready"),
    [state.sources],
  );

  const currentSession = useMemo(
    () => state.sessions.find((session) => session.id === state.currentSessionId) ?? null,
    [state.sessions, state.currentSessionId],
  );

  const chatTitle = currentSession?.title ?? DEFAULT_SESSION_TITLE;
  const chatMessages = currentSession?.messages ?? [];
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

  const createLocalSession = useCallback((sessionId: string, seedText: string) => {
    const session: ChatSession = {
      id: sessionId,
      title: truncateSessionTitle(seedText),
      createdAtLabel: "Today",
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

    try {
      if (!activeSessionId) {
        const createdSession = await createSessionApi({
          userId: DEFAULT_USER_ID,
          model: DEFAULT_MODEL,
        });
        activeSessionId = createLocalSession(createdSession.session_id, userText);
      }

      dispatch({
        type: "APPEND_MESSAGE",
        sessionId: activeSessionId,
        message: {
          id: createId(),
          role: "user",
          text: userText,
        },
      });

      const response = await sendMessageApi({
        sessionId: activeSessionId,
        message: userText,
      });

      const chips: SourceChip[] = response.sources.map((source) => ({
        ts: source.timestamp,
        title: source.title || "Source",
        videoId: source.video_id,
        url: source.url,
      }));

      dispatch({
        type: "APPEND_MESSAGE",
        sessionId: activeSessionId,
        message: {
          id: createId(),
          role: "assistant",
          text: response.reply,
          chips,
        },
      });
    } catch (error) {
      const message = toUserFacingError(error, "Failed to send message.");
      setRequestError(message);

      if (activeSessionId) {
        dispatch({
          type: "APPEND_MESSAGE",
          sessionId: activeSessionId,
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
  ]);

  const startNewChat = useCallback(() => {
    dispatch({ type: "SET_CURRENT_SESSION", sessionId: null });
    dispatch({ type: "SET_CHAT_INPUT", value: "" });

    if (!state.isLargeScreen) {
      dispatch({ type: "CLOSE_PANELS" });
    }
  }, [state.isLargeScreen]);

  const selectSession = useCallback(
    (sessionId: string) => {
      dispatch({ type: "SET_CURRENT_SESSION", sessionId });
      if (!state.isLargeScreen) {
        dispatch({ type: "CLOSE_NAV" });
      }
    },
    [state.isLargeScreen],
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
    toggleNav,
    toggleDrawer,
    openDrawer,
    closeDrawer,
    closePanels,
    setUrlInput,
    setChatInput,
    addSource,
    sendMessage,
    startNewChat,
    selectSession,
  };
}
