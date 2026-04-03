import type { ChatMessage, ChatSession, SourceItem, SourceType } from "../types/chat";
import { reduceChatSessions } from "./chatSessionsReducer";
import { reduceChatSources } from "./chatSourcesReducer";
import { reduceChatUi } from "./chatUiReducer";

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
      persistentSourceId?: string;
      chunks: number;
      videoId?: string;
      title: string;
      fileId?: string;
      sourceType?: SourceType;
    }
  | { type: "MARK_SOURCE_ERROR"; sourceId: number; errorMessage: string }
  | { type: "REMOVE_SOURCE"; sourceId: number }
  | { type: "SET_SESSIONS"; sessions: ChatSession[]; currentSessionId: string | null }
  | { type: "CREATE_SESSION"; session: ChatSession }
  | { type: "DELETE_SESSION"; sessionId: string; nextSessionId: string | null }
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
  return reduceChatUi(state, action)
    ?? reduceChatSources(state, action)
    ?? reduceChatSessions(state, action)
    ?? state;
}
