import { useCallback, useEffect, useMemo, useReducer, useRef } from "react";

import { DEFAULT_SESSION_TITLE } from "../constants/chatUi";
import {
  buildMockAssistantReply,
  createId,
  detectSourceTitle,
  pickPreferredSource,
  truncateSessionTitle,
} from "../lib/chatUtils";
import { chatReducer, createInitialChatState } from "../state/chatReducer";
import type { ChatSession } from "../types/chat";

const PROCESSING_DELAY_MS = 2800;
const MOCK_REPLY_DELAY_MS = 800;

export function useChatController() {
  const initialIsLarge = typeof window !== "undefined" ? window.innerWidth >= 1024 : true;

  const [state, dispatch] = useReducer(chatReducer, initialIsLarge, createInitialChatState);

  const pendingTimeoutsRef = useRef<number[]>([]);

  const clearPendingTimeouts = useCallback(() => {
    pendingTimeoutsRef.current.forEach((timeout) => window.clearTimeout(timeout));
    pendingTimeoutsRef.current = [];
  }, []);

  const registerTimeout = useCallback((timeoutId: number) => {
    pendingTimeoutsRef.current.push(timeoutId);
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
      clearPendingTimeouts();
    };
  }, [clearPendingTimeouts]);

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

  const addSource = useCallback(() => {
    const url = state.urlInput.trim();
    if (!url) {
      return;
    }

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

    const timeoutId = window.setTimeout(() => {
      dispatch({
        type: "MARK_SOURCE_READY",
        sourceId,
        chunks: Math.floor(Math.random() * 60) + 20,
      });
    }, PROCESSING_DELAY_MS);

    registerTimeout(timeoutId);
  }, [registerTimeout, state.urlInput]);

  const createSession = useCallback((seedText: string) => {
    const sessionId = createId();

    const session: ChatSession = {
      id: sessionId,
      title: truncateSessionTitle(seedText),
      createdAtLabel: "Today",
      messages: [],
    };

    dispatch({ type: "CREATE_SESSION", session });
    return sessionId;
  }, []);

  const sendMessage = useCallback(() => {
    const userText = state.chatInput.trim();
    if (!userText || !hasReadySource) {
      return;
    }

    dispatch({ type: "SET_CHAT_INPUT", value: "" });

    const activeSessionId = state.currentSessionId ?? createSession(userText);

    dispatch({
      type: "APPEND_MESSAGE",
      sessionId: activeSessionId,
      message: {
        id: createId(),
        role: "user",
        text: userText,
      },
    });

    const preferredSource = pickPreferredSource(state.sources);

    const timeoutId = window.setTimeout(() => {
      dispatch({
        type: "APPEND_MESSAGE",
        sessionId: activeSessionId,
        message: {
          id: createId(),
          role: "assistant",
          text: buildMockAssistantReply(userText),
          chips: preferredSource
            ? [{ ts: "12:34", title: preferredSource.title }]
            : [{ ts: "0:00", title: "Source" }],
        },
      });
    }, MOCK_REPLY_DELAY_MS);

    registerTimeout(timeoutId);
  }, [createSession, hasReadySource, registerTimeout, state.chatInput, state.currentSessionId, state.sources]);

  const startNewChat = useCallback(() => {
    dispatch({ type: "SET_CURRENT_SESSION", sessionId: null });
    dispatch({ type: "SET_CHAT_INPUT", value: "" });

    if (!state.isLargeScreen) {
      dispatch({ type: "CLOSE_PANELS" });
    }
  }, [state.isLargeScreen]);

  const selectSession = useCallback(
    (sessionId: number) => {
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
