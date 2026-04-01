const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
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
  const data = text ? JSON.parse(text) : null;

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
  }>;
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

export function toUserFacingError(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return fallback;
}
