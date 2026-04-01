export type SourceStatus = "uploading" | "queued" | "processing" | "ready" | "error";
export type SourceType = "youtube" | "video_file" | "pdf" | "text";

export interface SourceItem {
  id: number;
  url: string;
  title: string;
  status: SourceStatus;
  chunks: number;
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

export type MessageRole = "user" | "assistant";

export interface ChatMessage {
  id: number;
  role: MessageRole;
  text: string;
  chips?: SourceChip[];
}

export interface ChatSession {
  id: string;
  title: string;
  createdAtLabel: string;
  messages: ChatMessage[];
}
