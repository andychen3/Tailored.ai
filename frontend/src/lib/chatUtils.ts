import type { SourceItem, SourceType } from "../types/chat";

export function createId(): number {
  return Date.now() + Math.floor(Math.random() * 100000);
}

export function detectSourceTitle(url: string): string {
  return /youtube\.com|youtu\.be/i.test(url) ? "YouTube video" : "Uploaded source";
}

export function truncateSessionTitle(text: string, maxLength = 28): string {
  return text.length > maxLength ? `${text.slice(0, maxLength)}...` : text;
}

export function detectFileSourceType(fileName: string): SourceType | undefined {
  const extension = fileName.split(".").pop()?.toLowerCase();
  if (extension === "mp4" || extension === "mov" || extension === "avi") {
    return "video_file";
  }
  if (extension === "pdf") {
    return "pdf";
  }
  if (extension === "txt") {
    return "text";
  }
  return undefined;
}

export function toCreatedAtLabel(isoDate: string): string {
  const createdAt = new Date(isoDate);
  const now = new Date();
  if (
    createdAt.getFullYear() === now.getFullYear() &&
    createdAt.getMonth() === now.getMonth() &&
    createdAt.getDate() === now.getDate()
  ) {
    return "Today";
  }
  return createdAt.toLocaleDateString();
}

export function canDeleteSource(source: Pick<SourceItem, "sourceId" | "status" | "syncStatus">): boolean {
  if (!source.sourceId) {
    return false;
  }

  if (source.status === "uploading" || source.status === "queued" || source.status === "processing") {
    return false;
  }

  return source.status === "ready" || source.status === "error" || source.syncStatus === "missing";
}
