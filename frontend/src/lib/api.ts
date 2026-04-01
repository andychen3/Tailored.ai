const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";
const BACKEND_URL = import.meta.env.VITE_BACKEND_URL ?? "http://127.0.0.1:8000";

const CHUNK_SIZE_BYTES = 10 * 1024 * 1024; // 10 MB per chunk
const CHUNKED_UPLOAD_THRESHOLD_BYTES = 50 * 1024 * 1024; // use chunked for files > 50 MB

if (import.meta.env.DEV) {
  console.info("[api] API_BASE_URL:", API_BASE_URL || "(same-origin via Vite proxy)");
}

class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

function parseJson(text: string): unknown {
  if (!text) {
    return null;
  }

  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

async function request<T>(path: string, init: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init.headers ?? {}),
    },
  });

  const text = await response.text();
  const data = parseJson(text);

  if (!response.ok) {
    const detail = data && typeof data === "object" && "detail" in data ? data.detail : null;
    throw new ApiError(
      typeof detail === "string" ? detail : `Request failed with status ${response.status}`,
      response.status,
    );
  }

  return data as T;
}

export type IngestYoutubePayload = {
  userId: string;
  url: string;
};

export type IngestYoutubeResult = {
  success: boolean;
  video_id: string;
  video_title: string;
  chunks_ingested: number;
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

export type CreateSessionPayload = {
  userId: string;
  model: string;
};

export type CreateSessionResult = {
  session_id: string;
  user_id: string;
};

export async function createSession(payload: CreateSessionPayload): Promise<CreateSessionResult> {
  return request<CreateSessionResult>("/chat/sessions", {
    method: "POST",
    body: JSON.stringify({
      user_id: payload.userId,
      model: payload.model,
    }),
  });
}

export type SendMessagePayload = {
  sessionId: string;
  message: string;
};

export type SendMessageResult = {
  reply: string;
  has_context: boolean;
  sources: Array<{
    title: string;
    timestamp: string;
    video_id?: string;
    url?: string;
    page_number?: number;
  }>;
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
  file_id: string | null;
  file_name: string;
  source_type: string;
  status: "queued" | "processing" | "ready" | "error";
  chunks_ingested: number | null;
  error_message: string | null;
};

export async function sendMessage(payload: SendMessagePayload): Promise<SendMessageResult> {
  return request<SendMessageResult>("/chat/message", {
    method: "POST",
    body: JSON.stringify({
      session_id: payload.sessionId,
      message: payload.message,
    }),
  });
}

function xhrPost(url: string, form: FormData, onProgress?: (loaded: number, total: number) => void): Promise<unknown> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", url);

    if (onProgress) {
      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable) onProgress(event.loaded, event.total);
      };
    }

    xhr.onload = () => {
      const data = parseJson(xhr.responseText);
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(data);
        return;
      }
      const detail = data && typeof data === "object" && "detail" in data ? data.detail : null;
      reject(
        new ApiError(
          typeof detail === "string" ? detail : `Request failed with status ${xhr.status}`,
          xhr.status,
        ),
      );
    };

    xhr.onerror = () => reject(new ApiError("Network error while uploading file.", 0));
    xhr.onabort = () => reject(new ApiError("Upload was canceled.", 0));

    xhr.send(form);
  });
}

export async function ingestFile(
  userId: string,
  file: File,
  onProgress?: (percent: number) => void,
): Promise<IngestFileResult> {
  // Small files: single request
  if (file.size <= CHUNKED_UPLOAD_THRESHOLD_BYTES) {
    const form = new FormData();
    form.append("user_id", userId);
    form.append("file", file);
    return xhrPost(
      `${API_BASE_URL}/ingest/file`,
      form,
      onProgress ? (loaded, total) => onProgress(Math.min(100, Math.round((loaded / total) * 100))) : undefined,
    ) as Promise<IngestFileResult>;
  }

  // Large files: split into chunks and upload sequentially
  const uploadId = crypto.randomUUID();
  const totalChunks = Math.ceil(file.size / CHUNK_SIZE_BYTES);
  let bytesUploaded = 0;

  for (let i = 0; i < totalChunks; i++) {
    const start = i * CHUNK_SIZE_BYTES;
    const blob = file.slice(start, start + CHUNK_SIZE_BYTES);

    const form = new FormData();
    form.append("upload_id", uploadId);
    form.append("chunk_index", String(i));
    form.append("chunk", blob, file.name);

    await xhrPost(`${BACKEND_URL}/ingest/upload-chunk`, form, (loaded) => {
      if (!onProgress) return;
      const percent = Math.min(
        99, // reserve the last 1% for the complete request
        Math.round(((bytesUploaded + loaded) / file.size) * 100),
      );
      onProgress(percent);
    });

    bytesUploaded += blob.size;
    if (onProgress) onProgress(Math.min(99, Math.round((bytesUploaded / file.size) * 100)));
  }

  // All chunks received — tell the backend to assemble and queue
  const completeForm = new FormData();
  completeForm.append("upload_id", uploadId);
  completeForm.append("file_name", file.name);
  completeForm.append("total_chunks", String(totalChunks));
  completeForm.append("user_id", userId);

  const result = (await xhrPost(`${BACKEND_URL}/ingest/upload-complete`, completeForm)) as {
    success: boolean;
    job_id: string;
    file_name: string;
    source_type: string;
    status: "queued";
  };

  if (onProgress) onProgress(100);

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

export function toUserFacingError(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return fallback;
}
