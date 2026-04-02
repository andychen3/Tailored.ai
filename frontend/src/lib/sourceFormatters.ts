import type { SourceItem } from "../types/chat";

export function getSourceStatusText(source: SourceItem): string {
  if (source.status === "uploading") {
    return source.uploadPercent != null
      ? `Uploading... ${source.uploadPercent}%`
      : "Uploading...";
  }

  if (source.status === "queued") {
    return "Queued...";
  }

  if (source.status === "processing") {
    if (source.sourceType === "video_file") {
      return "Transcribing...";
    }
    if (source.sourceType === "pdf" || source.sourceType === "text") {
      return "Indexing...";
    }
    return "Processing...";
  }

  if (source.status === "error") {
    return "Failed";
  }

  if (source.syncStatus === "missing") {
    return "Needs reindex";
  }

  if (source.syncStatus === "unknown") {
    return "Sync unknown";
  }

  return `Ready · ${source.chunks} chunks`;
}

export function getProgressWidth(source: SourceItem): string {
  if (source.status === "uploading" && source.uploadPercent != null) {
    return `${Math.max(source.uploadPercent, 8)}%`;
  }
  return "60%";
}
