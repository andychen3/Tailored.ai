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

export type CatalogSourceResult = {
  source_id: string;
  user_id: string;
  source_type: "youtube" | "video_file" | "pdf" | "text";
  title: string;
  source_url: string | null;
  video_id: string | null;
  file_id: string | null;
  expected_chunk_count: number;
  sync_status: "in_sync" | "missing" | "unknown";
  last_verified_at: string | null;
  created_at: string;
  updated_at: string;
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

export async function listSources(userId: string): Promise<CatalogSourceResult[]> {
  const query = new URLSearchParams({ user_id: userId }).toString();
  const payload = await request<{ sources: CatalogSourceResult[] }>(`/sources?${query}`, {
    method: "GET",
  });
  return payload.sources;
}

export type CreateSessionPayload = {
  userId: string;
  model: string;
};

export type CreateSessionResult = {
  session_id: string;
  user_id: string;
  title: string;
  model: string;
  created_at: string;
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

export type SessionSummaryResult = {
  session_id: string;
  user_id: string;
  title: string;
  model: string;
  created_at: string;
  updated_at: string;
  last_message_at: string | null;
  message_count: number;
  prompt_tokens_total: number;
  completion_tokens_total: number;
  total_tokens_total: number;
};

export type SessionMessageResult = {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources: Array<{
    title: string;
    timestamp: string;
    video_id?: string;
    url?: string;
    page_number?: number;
  }>;
  usage: {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
  } | null;
  created_at: string;
};

export type SessionDetailResult = {
  session: SessionSummaryResult;
  messages: SessionMessageResult[];
};

export async function listSessions(userId: string): Promise<SessionSummaryResult[]> {
  const query = new URLSearchParams({ user_id: userId }).toString();
  const payload = await request<{ sessions: SessionSummaryResult[] }>(`/chat/sessions?${query}`, {
    method: "GET",
  });
  return payload.sessions;
}

export async function getSession(sessionId: string): Promise<SessionDetailResult> {
  return request<SessionDetailResult>(`/chat/sessions/${sessionId}`, {
    method: "GET",
  });
}

export type SendMessagePayload = {
  sessionId: string;
  message: string;
};

export type ChatSourceChipResult = {
  title: string;
  timestamp: string;
  video_id?: string;
  url?: string;
  page_number?: number;
};

export type SendMessageResult = {
  reply: string;
  has_context: boolean;
  sources: ChatSourceChipResult[];
  usage: {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
  } | null;
  thread_usage: {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
  } | null;
};

export type SendMessageStreamResult = {
  reply: string;
  has_context: boolean;
  sources: ChatSourceChipResult[];
  usage: {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
  } | null;
  thread_usage: {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
  } | null;
  assistant_message_id: string;
};

export type SendMessageStreamHandlers = {
  onDelta?: (delta: string) => void;
  onCompletion?: (result: SendMessageStreamResult) => void;
};

export type ChatModelResult = {
  id: string;
  label: string;
  max_context_tokens: number | null;
};

export async function listModels(): Promise<ChatModelResult[]> {
  const payload = await request<{ models: ChatModelResult[] }>("/chat/models", {
    method: "GET",
  });
  return payload.models;
}

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

function parseSseEventBlock(block: string): { event: string; data: string } | null {
  const lines = block.split(/\r?\n/);
  let event = "message";
  const dataLines: string[] = [];

  for (const line of lines) {
    if (line.startsWith("event:")) {
      event = line.slice("event:".length).trim();
      continue;
    }
    if (line.startsWith("data:")) {
      dataLines.push(line.slice("data:".length).trimStart());
    }
  }

  if (dataLines.length === 0) {
    return null;
  }

  return {
    event,
    data: dataLines.join("\n"),
  };
}

export async function sendMessageStream(
  payload: SendMessagePayload,
  handlers: SendMessageStreamHandlers = {},
): Promise<SendMessageStreamResult> {
  const response = await fetch(`${API_BASE_URL}/chat/message/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify({
      session_id: payload.sessionId,
      message: payload.message,
    }),
  });

  const contentType = response.headers.get("content-type") ?? "";
  if (!response.ok) {
    const text = await response.text();
    const data = parseJson(text);
    const detail = data && typeof data === "object" && "detail" in data ? data.detail : null;
    throw new ApiError(
      typeof detail === "string" ? detail : `Request failed with status ${response.status}`,
      response.status,
    );
  }

  if (!response.body || !contentType.includes("text/event-stream")) {
    throw new ApiError("Streaming response is not available.", 0);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let completion: SendMessageStreamResult | null = null;

  while (true) {
    const { value, done } = await reader.read();
    if (done) {
      break;
    }

    buffer += decoder.decode(value, { stream: true });

    while (true) {
      const eventBoundary = buffer.indexOf("\n\n");
      if (eventBoundary < 0) {
        break;
      }

      const block = buffer.slice(0, eventBoundary);
      buffer = buffer.slice(eventBoundary + 2);
      const parsed = parseSseEventBlock(block);
      if (!parsed) {
        continue;
      }

      let payloadData: unknown = null;
      try {
        payloadData = JSON.parse(parsed.data);
      } catch {
        throw new ApiError("Received malformed streaming data.", response.status);
      }

      if (parsed.event === "delta") {
        const delta = payloadData && typeof payloadData === "object" && "delta" in payloadData
          ? String((payloadData as { delta: unknown }).delta ?? "")
          : "";
        if (delta) {
          handlers.onDelta?.(delta);
        }
        continue;
      }

      if (parsed.event === "error") {
        const detail = payloadData && typeof payloadData === "object" && "detail" in payloadData
          ? String((payloadData as { detail: unknown }).detail ?? "Streaming request failed.")
          : "Streaming request failed.";
        throw new ApiError(detail, response.status);
      }

      if (parsed.event === "completion") {
        const completionData = payloadData as {
          reply?: string;
          has_context?: boolean;
          sources?: ChatSourceChipResult[];
          usage?: SendMessageStreamResult["usage"];
          thread_usage?: SendMessageStreamResult["thread_usage"];
          assistant_message_id?: string;
        };
        completion = {
          reply: completionData.reply ?? "",
          has_context: Boolean(completionData.has_context),
          sources: completionData.sources ?? [],
          usage: completionData.usage ?? null,
          thread_usage: completionData.thread_usage ?? null,
          assistant_message_id: completionData.assistant_message_id ?? "",
        };
        handlers.onCompletion?.(completion);
      }
    }
  }

  if (!completion) {
    throw new ApiError("Streaming response ended before completion.", response.status);
  }

  return completion;
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
