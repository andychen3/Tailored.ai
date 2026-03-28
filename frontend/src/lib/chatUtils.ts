import type { SourceItem } from "../types/chat";

export function createId(): number {
  return Date.now() + Math.floor(Math.random() * 100000);
}

export function detectSourceTitle(url: string): string {
  return /youtube\.com|youtu\.be/i.test(url) ? "YouTube video" : "Uploaded source";
}

export function truncateSessionTitle(text: string, maxLength = 28): string {
  return text.length > maxLength ? `${text.slice(0, maxLength)}...` : text;
}

export function pickPreferredSource(sources: SourceItem[]): SourceItem | undefined {
  return sources.find((source) => source.status === "ready") ?? sources[0];
}

export function buildMockAssistantReply(question: string): string {
  return `Based on your sources, here's what I found about "${question}". This is a mocked answer for Phase 2; once we connect FastAPI in Phase 3, this will use real retrieval and citations.`;
}
