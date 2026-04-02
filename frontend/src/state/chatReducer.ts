import type { ChatMessage, ChatSession, SourceItem, SourceType } from "../types/chat";

export interface ChatAppState {
  isLargeScreen: boolean;
  isNavOpen: boolean;
  isDrawerOpen: boolean;
  sources: SourceItem[];
  sessions: ChatSession[];
  currentSessionId: string | null;
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
  | { type: "SET_SOURCES"; sources: SourceItem[] }
  | { type: "UPDATE_SOURCE_UPLOAD"; sourceId: number; uploadPercent: number }
  | {
      type: "MARK_SOURCE_QUEUED";
      sourceId: number;
      jobId: string;
      sourceType?: SourceType;
    }
  | {
      type: "MARK_SOURCE_PROCESSING";
      sourceId: number;
      jobId?: string;
      sourceType?: SourceType;
    }
  | {
      type: "MARK_SOURCE_READY";
      sourceId: number;
      chunks: number;
      videoId?: string;
      title: string;
      fileId?: string;
      sourceType?: SourceType;
    }
  | { type: "MARK_SOURCE_ERROR"; sourceId: number; errorMessage: string }
  | { type: "SET_SESSIONS"; sessions: ChatSession[]; currentSessionId: string | null }
  | { type: "CREATE_SESSION"; session: ChatSession }
  | { type: "UPDATE_SESSION_MODEL"; sessionId: string; model: string }
  | { type: "UPDATE_SESSION_TITLE"; sessionId: string; title: string }
  | { type: "UPDATE_SESSION_USAGE"; sessionId: string; promptTokens: number; completionTokens: number; totalTokens: number }
  | { type: "SET_CURRENT_SESSION"; sessionId: string | null }
  | { type: "SET_SESSION_MESSAGES"; sessionId: string; messages: ChatMessage[] }
  | { type: "APPEND_MESSAGE"; sessionId: string; message: ChatMessage }
  | {
      type: "UPDATE_MESSAGE";
      sessionId: string;
      messageId: ChatMessage["id"];
      patch: Partial<ChatMessage>;
    }
  | {
      type: "REMOVE_MESSAGE";
      sessionId: string;
      messageId: ChatMessage["id"];
    };

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

    case "SET_SOURCES":
      return {
        ...state,
        sources: action.sources,
      };

    case "UPDATE_SOURCE_UPLOAD":
      return {
        ...state,
        sources: state.sources.map((source) =>
          source.id === action.sourceId
            ? {
                ...source,
                status: "uploading",
                uploadPercent: action.uploadPercent,
                errorMessage: undefined,
              }
            : source,
        ),
      };

    case "MARK_SOURCE_QUEUED":
      return {
        ...state,
        sources: state.sources.map((source) =>
          source.id === action.sourceId
            ? {
                ...source,
                status: "queued",
                jobId: action.jobId,
                sourceType: action.sourceType ?? source.sourceType,
                uploadPercent: 100,
                errorMessage: undefined,
              }
            : source,
        ),
      };

    case "MARK_SOURCE_PROCESSING":
      return {
        ...state,
        sources: state.sources.map((source) =>
          source.id === action.sourceId
            ? {
                ...source,
                status: "processing",
                jobId: action.jobId ?? source.jobId,
                sourceType: action.sourceType ?? source.sourceType,
                uploadPercent: undefined,
                errorMessage: undefined,
              }
            : source,
        ),
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
                videoId: action.videoId,
                title: action.title,
                fileId: action.fileId,
                sourceType: action.sourceType,
                syncStatus: "in_sync",
                uploadPercent: undefined,
                errorMessage: undefined,
              }
            : source,
        ),
      };

    case "MARK_SOURCE_ERROR":
      return {
        ...state,
        sources: state.sources.map((source) =>
          source.id === action.sourceId
            ? {
                ...source,
                status: "error",
                uploadPercent: undefined,
                errorMessage: action.errorMessage,
              }
            : source,
        ),
      };

    case "CREATE_SESSION":
      return {
        ...state,
        sessions: [
          action.session,
          ...state.sessions.filter((session) => session.id !== action.session.id),
        ],
        currentSessionId: action.session.id,
      };

    case "SET_SESSIONS":
      return {
        ...state,
        sessions: action.sessions,
        currentSessionId: action.currentSessionId,
      };

    case "UPDATE_SESSION_TITLE":
      return {
        ...state,
        sessions: state.sessions.map((session) =>
          session.id === action.sessionId
            ? {
                ...session,
                title: action.title,
              }
            : session,
        ),
      };

    case "UPDATE_SESSION_MODEL":
      return {
        ...state,
        sessions: state.sessions.map((session) =>
          session.id === action.sessionId
            ? {
                ...session,
                model: action.model,
              }
            : session,
        ),
      };

    case "UPDATE_SESSION_USAGE":
      return {
        ...state,
        sessions: state.sessions.map((session) =>
          session.id === action.sessionId
            ? {
                ...session,
                tokenUsage: {
                  promptTokens: action.promptTokens,
                  completionTokens: action.completionTokens,
                  totalTokens: action.totalTokens,
                },
              }
            : session,
        ),
      };

    case "SET_CURRENT_SESSION":
      return {
        ...state,
        currentSessionId: action.sessionId,
      };

    case "SET_SESSION_MESSAGES":
      return {
        ...state,
        sessions: state.sessions.map((session) =>
          session.id === action.sessionId
            ? {
                ...session,
                messages: action.messages,
              }
            : session,
        ),
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

    case "UPDATE_MESSAGE":
      return {
        ...state,
        sessions: state.sessions.map((session) =>
          session.id === action.sessionId
            ? {
                ...session,
                messages: session.messages.map((message) =>
                  message.id === action.messageId
                    ? {
                        ...message,
                        ...action.patch,
                      }
                    : message,
                ),
              }
            : session,
        ),
      };

    case "REMOVE_MESSAGE":
      return {
        ...state,
        sessions: state.sessions.map((session) =>
          session.id === action.sessionId
            ? {
                ...session,
                messages: session.messages.filter((message) => message.id !== action.messageId),
              }
            : session,
        ),
      };

    default:
      return state;
  }
}
