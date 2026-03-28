export type SourceStatus = "processing" | "ready";

export interface SourceItem {
  id: number;
  url: string;
  title: string;
  status: SourceStatus;
  chunks: number;
}

export interface SourceChip {
  ts: string;
  title: string;
}

export type MessageRole = "user" | "assistant";

export interface ChatMessage {
  id: number;
  role: MessageRole;
  text: string;
  chips?: SourceChip[];
}

export interface ChatSession {
  id: number;
  title: string;
  createdAtLabel: string;
  messages: ChatMessage[];
}
