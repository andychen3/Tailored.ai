import { request } from "./client";

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

export type SessionSummaryResult = {
  session_id: string;
  title: string;
  model: string;
  created_at: string;
  prompt_tokens_total: number;
  completion_tokens_total: number;
  total_tokens_total: number;
};

export type ChatSourceChipResult = {
  title: string;
  timestamp: string;
  video_id?: string;
  url?: string;
  page_number?: number;
};

export type SessionMessageResult = {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources: ChatSourceChipResult[];
  action?: {
    type: string;
    label: string;
    url: string;
    pending_action_id?: string | null;
  } | null;
  usage: {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
  } | null;
};

export type SessionDetailResult = {
  session: SessionSummaryResult;
  messages: SessionMessageResult[];
};

export type SendMessagePayload = {
  sessionId: string;
  message: string;
};

export type SendMessageResult = {
  reply: string;
  sources: ChatSourceChipResult[];
  action?: {
    type: string;
    label: string;
    url: string;
    pending_action_id?: string | null;
  } | null;
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

export type SendMessageStreamResult = SendMessageResult & {
  assistant_message_id: string;
};

export type ChatModelResult = {
  id: string;
  max_context_tokens: number | null;
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

export async function deleteSession(sessionId: string): Promise<void> {
  await request<{ success: boolean }>(`/chat/sessions/${sessionId}`, {
    method: "DELETE",
  });
}

export async function sendMessage(payload: SendMessagePayload): Promise<SendMessageResult> {
  return request<SendMessageResult>("/chat/message", {
    method: "POST",
    body: JSON.stringify({
      session_id: payload.sessionId,
      message: payload.message,
    }),
  });
}

export async function listModels(): Promise<ChatModelResult[]> {
  const payload = await request<{ models: ChatModelResult[] }>("/chat/models", {
    method: "GET",
  });
  return payload.models;
}

export async function disconnectNotion(userId: string): Promise<void> {
  await request<{ success: boolean; disconnected: boolean }>("/integrations/notion/disconnect", {
    method: "POST",
    body: JSON.stringify({ user_id: userId }),
  });
}
