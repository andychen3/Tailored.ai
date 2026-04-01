export type SourceStatus = "processing" | "ready" | "error";

export interface SourceItem {
  id: number;
  url: string;
  title: string;
  status: SourceStatus;
  chunks: number;
  errorMessage?: string;
  videoId?: string;
}

export interface SourceChip {
  ts: string;
  title: string;
  videoId?: string;
  url?: string;
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
