export type SourceStatus = "uploading" | "queued" | "processing" | "ready" | "error";
export type SourceType = "youtube" | "video_file" | "pdf" | "text";
export type SourceSyncStatus = "in_sync" | "missing" | "unknown";

export interface SourceItem {
  id: number;
  sourceId?: string;
  url: string;
  title: string;
  status: SourceStatus;
  chunks: number;
  syncStatus?: SourceSyncStatus;
  errorMessage?: string;
  videoId?: string;
  fileId?: string;
  jobId?: string;
  sourceType?: SourceType;
  uploadPercent?: number;
}

export interface SourceChip {
  ts: string;
  title: string;
  videoId?: string;
  url?: string;
  pageNumber?: number;
}

export interface TokenUsage {
  promptTokens: number;
  completionTokens: number;
  totalTokens: number;
}

export interface AssistantAction {
  type: string;
  label: string;
  url: string;
  pendingActionId?: string;
}

export type MessageRole = "user" | "assistant";

export interface ChatMessage {
  id: number | string;
  role: MessageRole;
  text: string;
  chips?: SourceChip[];
  action?: AssistantAction;
  usage?: TokenUsage;
  isStreaming?: boolean;
}

export interface ChatSession {
  id: string;
  title: string;
  model: string;
  createdAtLabel: string;
  tokenUsage: TokenUsage;
  messages: ChatMessage[];
}
