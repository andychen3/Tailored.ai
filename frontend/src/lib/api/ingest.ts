import { request } from "./client";
import { shouldUseChunkedUpload, uploadInChunks, uploadInSingleRequest } from "./upload";

export type IngestYoutubePayload = {
  userId: string;
  url: string;
};

export type IngestYoutubeResult = {
  success: boolean;
  source_id: string;
  video_id: string;
  video_title: string;
  chunks_ingested: number;
};

export type IngestFileResult = {
  success: boolean;
  job_id: string;
  file_name: string;
  source_type: string;
  status: "queued";
};

export type IngestJobResult = {
  success: boolean;
  job_id: string;
  source_id: string | null;
  file_id: string | null;
  file_name: string;
  source_type: string;
  status: "queued" | "processing" | "ready" | "error";
  chunks_ingested: number | null;
  error_message: string | null;
};

export async function ingestYoutube(payload: IngestYoutubePayload): Promise<IngestYoutubeResult> {
  return request<IngestYoutubeResult>("/ingest/youtube", {
    method: "POST",
    body: JSON.stringify({
      user_id: payload.userId,
      url: payload.url,
    }),
  });
}

export async function ingestFile(
  userId: string,
  file: File,
  onProgress?: (percent: number) => void,
): Promise<IngestFileResult> {
  if (!shouldUseChunkedUpload(file)) {
    return uploadInSingleRequest(userId, file, onProgress) as Promise<IngestFileResult>;
  }

  const result = await uploadInChunks(userId, file, onProgress) as {
    success: boolean;
    job_id: string;
    file_name: string;
    source_type: string;
    status: "queued";
  };

  return {
    success: result.success,
    job_id: result.job_id,
    file_name: result.file_name,
    source_type: result.source_type,
    status: "queued",
  };
}

export async function getIngestJob(jobId: string): Promise<IngestJobResult> {
  return request<IngestJobResult>(`/ingest/jobs/${jobId}`, {
    method: "GET",
  });
}
