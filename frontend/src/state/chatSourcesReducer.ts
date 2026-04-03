import type { ChatAction, ChatAppState } from "./chatReducer";

export function reduceChatSources(state: ChatAppState, action: ChatAction): ChatAppState | null {
  switch (action.type) {
    case "ADD_SOURCE":
      return {
        ...state,
        sources: [action.source, ...state.sources],
        urlInput: "",
      };
    case "SET_SOURCES":
      return { ...state, sources: action.sources };
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
                sourceId: action.persistentSourceId ?? source.sourceId,
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
    case "REMOVE_SOURCE":
      return {
        ...state,
        sources: state.sources.filter((source) => source.id !== action.sourceId),
      };
    default:
      return null;
  }
}
