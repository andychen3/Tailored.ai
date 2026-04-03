import type { ChatAction, ChatAppState } from "./chatReducer";

export function reduceChatSessions(state: ChatAppState, action: ChatAction): ChatAppState | null {
  switch (action.type) {
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
    case "DELETE_SESSION":
      return {
        ...state,
        sessions: state.sessions.filter((session) => session.id !== action.sessionId),
        currentSessionId: action.nextSessionId,
      };
    case "UPDATE_SESSION_MODEL":
      return {
        ...state,
        sessions: state.sessions.map((session) =>
          session.id === action.sessionId ? { ...session, model: action.model } : session,
        ),
      };
    case "UPDATE_SESSION_TITLE":
      return {
        ...state,
        sessions: state.sessions.map((session) =>
          session.id === action.sessionId ? { ...session, title: action.title } : session,
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
      return { ...state, currentSessionId: action.sessionId };
    case "SET_SESSION_MESSAGES":
      return {
        ...state,
        sessions: state.sessions.map((session) =>
          session.id === action.sessionId ? { ...session, messages: action.messages } : session,
        ),
      };
    case "APPEND_MESSAGE":
      return {
        ...state,
        sessions: state.sessions.map((session) =>
          session.id === action.sessionId
            ? { ...session, messages: [...session.messages, action.message] }
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
                  message.id === action.messageId ? { ...message, ...action.patch } : message,
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
      return null;
  }
}
