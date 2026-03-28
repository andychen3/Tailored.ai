import type { ChatMessage, ChatSession, SourceItem } from "../types/chat";

export interface ChatAppState {
  isLargeScreen: boolean;
  isNavOpen: boolean;
  isDrawerOpen: boolean;
  sources: SourceItem[];
  sessions: ChatSession[];
  currentSessionId: number | null;
  urlInput: string;
  chatInput: string;
}

export type ChatAction =
  | { type: "SET_SCREEN_SIZE"; isLargeScreen: boolean }
  | { type: "TOGGLE_NAV" }
  | { type: "CLOSE_NAV" }
  | { type: "TOGGLE_DRAWER" }
  | { type: "OPEN_DRAWER" }
  | { type: "CLOSE_DRAWER" }
  | { type: "CLOSE_PANELS" }
  | { type: "SET_URL_INPUT"; value: string }
  | { type: "SET_CHAT_INPUT"; value: string }
  | { type: "ADD_SOURCE"; source: SourceItem }
  | { type: "MARK_SOURCE_READY"; sourceId: number; chunks: number }
  | { type: "CREATE_SESSION"; session: ChatSession }
  | { type: "SET_CURRENT_SESSION"; sessionId: number | null }
  | { type: "APPEND_MESSAGE"; sessionId: number; message: ChatMessage };

export function createInitialChatState(isLargeScreen: boolean): ChatAppState {
  return {
    isLargeScreen,
    isNavOpen: isLargeScreen,
    isDrawerOpen: isLargeScreen,
    sources: [],
    sessions: [],
    currentSessionId: null,
    urlInput: "",
    chatInput: "",
  };
}

export function chatReducer(state: ChatAppState, action: ChatAction): ChatAppState {
  switch (action.type) {
    case "SET_SCREEN_SIZE":
      return {
        ...state,
        isLargeScreen: action.isLargeScreen,
      };

    case "TOGGLE_NAV":
      return {
        ...state,
        isNavOpen: !state.isNavOpen,
      };

    case "CLOSE_NAV":
      return {
        ...state,
        isNavOpen: false,
      };

    case "TOGGLE_DRAWER":
      return {
        ...state,
        isDrawerOpen: !state.isDrawerOpen,
      };

    case "OPEN_DRAWER":
      return {
        ...state,
        isDrawerOpen: true,
      };

    case "CLOSE_DRAWER":
      return {
        ...state,
        isDrawerOpen: false,
      };

    case "CLOSE_PANELS":
      return {
        ...state,
        isNavOpen: false,
        isDrawerOpen: false,
      };

    case "SET_URL_INPUT":
      return {
        ...state,
        urlInput: action.value,
      };

    case "SET_CHAT_INPUT":
      return {
        ...state,
        chatInput: action.value,
      };

    case "ADD_SOURCE":
      return {
        ...state,
        sources: [action.source, ...state.sources],
        urlInput: "",
      };

    case "MARK_SOURCE_READY":
      return {
        ...state,
        sources: state.sources.map((source) =>
          source.id === action.sourceId
            ? {
                ...source,
                status: "ready",
                chunks: action.chunks,
              }
            : source,
        ),
      };

    case "CREATE_SESSION":
      return {
        ...state,
        sessions: [action.session, ...state.sessions],
        currentSessionId: action.session.id,
      };

    case "SET_CURRENT_SESSION":
      return {
        ...state,
        currentSessionId: action.sessionId,
      };

    case "APPEND_MESSAGE":
      return {
        ...state,
        sessions: state.sessions.map((session) =>
          session.id === action.sessionId
            ? {
                ...session,
                messages: [...session.messages, action.message],
              }
            : session,
        ),
      };

    default:
      return state;
  }
}
