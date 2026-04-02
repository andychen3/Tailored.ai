import { useCallback, useEffect, useMemo, useReducer, useState } from "react";

import { DEFAULT_SESSION_TITLE } from "../constants/chatUi";
import { listModels } from "../lib/api";
import { chatReducer, createInitialChatState } from "../state/chatReducer";
import { useSourceIngestion } from "./useSourceIngestion";
import { useSendMessage } from "./useSendMessage";
import { useSessionManager } from "./useSessionManager";

const DEFAULT_USER_ID = import.meta.env.VITE_DEFAULT_USER_ID ?? "default_user";
const DEFAULT_MODEL = import.meta.env.VITE_OPENAI_MODEL ?? "gpt-4o-mini";
const ZERO_USAGE = { promptTokens: 0, completionTokens: 0, totalTokens: 0 };

export function useChatController() {
  const initialIsLarge = typeof window !== "undefined" ? window.innerWidth >= 1024 : true;

  const [state, dispatch] = useReducer(chatReducer, initialIsLarge, createInitialChatState);
  const [requestError, setRequestError] = useState<string | null>(null);
  const [availableModels, setAvailableModels] = useState<string[]>([DEFAULT_MODEL]);
  const [modelTokenLimits, setModelTokenLimits] = useState<Record<string, number>>({});
  const [selectedModel, setSelectedModel] = useState(DEFAULT_MODEL);

  // --- Sub-hooks ---

  const { isAddingSource, uploadFile, addSource } = useSourceIngestion(
    dispatch,
    DEFAULT_USER_ID,
    state.urlInput,
    setRequestError,
  );

  const hasReadySource = useMemo(
    () => state.sources.some((source) => source.status === "ready" && source.syncStatus !== "missing"),
    [state.sources],
  );

  const { isSendingMessage, sendMessage, startNewChat: startNewChatBase } = useSendMessage(
    dispatch,
    state.chatInput,
    state.currentSessionId,
    hasReadySource,
    selectedModel,
    setRequestError,
  );

  const {
    deletingSourceId,
    deletingSessionId,
    selectSession,
    deleteSession,
    deleteSource,
  } = useSessionManager(
    dispatch,
    DEFAULT_USER_ID,
    state.sessions,
    state.currentSessionId,
    state.sources,
    state.isLargeScreen,
    setRequestError,
  );

  // --- Models hydration ---

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

  // --- Screen resize ---

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

  // --- Derived state ---

  const currentSession = useMemo(
    () => state.sessions.find((session) => session.id === state.currentSessionId) ?? null,
    [state.sessions, state.currentSessionId],
  );

  const chatTitle = currentSession?.title ?? DEFAULT_SESSION_TITLE;
  const chatMessages = currentSession?.messages ?? [];
  const threadTokenUsage = currentSession?.tokenUsage ?? ZERO_USAGE;
  const threadTokenLimit = modelTokenLimits[selectedModel] ?? null;
  const showEmptyState = chatMessages.length === 0;

  // --- UI dispatch wrappers ---

  const toggleNav = useCallback(() => {
    dispatch({ type: "TOGGLE_NAV" });
  }, []);

  const toggleDrawer = useCallback(() => {
    dispatch({ type: "TOGGLE_DRAWER" });
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

  const startNewChat = useCallback(async () => {
    await startNewChatBase();
    if (!state.isLargeScreen) {
      dispatch({ type: "CLOSE_PANELS" });
    }
  }, [startNewChatBase, state.isLargeScreen]);

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
    deletingSourceId,
    isSendingMessage,
    deletingSessionId,
    requestError,
    availableModels,
    selectedModel,
    setSelectedModel,
    threadTokenUsage,
    threadTokenLimit,
    toggleNav,
    toggleDrawer,
    closeDrawer,
    closePanels,
    setUrlInput,
    setChatInput,
    addSource,
    deleteSource,
    uploadFile,
    sendMessage,
    startNewChat,
    selectSession,
    deleteSession,
  };
}
