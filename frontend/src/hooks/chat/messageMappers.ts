import type {
  ChatSourceChipResult,
  CreateSessionResult,
  SendMessageResult,
  SendMessageStreamResult,
  SessionDetailResult,
} from "../../lib/api";
import { ZERO_USAGE } from "../../constants/chatRuntime";
import { truncateSessionTitle, toCreatedAtLabel } from "../../lib/chatUtils";
import type { AssistantAction, ChatMessage, ChatSession, SourceChip } from "../../types/chat";

export function mapSourceChip(source: ChatSourceChipResult): SourceChip {
  return {
    ts: source.timestamp,
    title: source.title || "Source",
    videoId: source.video_id,
    url: source.url,
    pageNumber: source.page_number,
  };
}

export function mapApiUsage(
  usage:
    | SendMessageResult["usage"]
    | SendMessageStreamResult["usage"]
    | SessionDetailResult["messages"][number]["usage"],
): ChatMessage["usage"] | undefined {
  if (!usage) {
    return undefined;
  }
  return {
    promptTokens: usage.prompt_tokens,
    completionTokens: usage.completion_tokens,
    totalTokens: usage.total_tokens,
  };
}

export function mapAssistantAction(
  action:
    | SendMessageResult["action"]
    | SendMessageStreamResult["action"]
    | SessionDetailResult["messages"][number]["action"],
): AssistantAction | undefined {
  if (!action) {
    return undefined;
  }
  return {
    type: action.type,
    label: action.label,
    url: action.url,
    pendingActionId: action.pending_action_id ?? undefined,
  };
}

export function mapSessionDetailMessages(sessionDetail: SessionDetailResult): ChatMessage[] {
  return sessionDetail.messages.map((message) => ({
    id: message.id,
    role: message.role,
    text: message.content,
    chips: (message.sources ?? []).map(mapSourceChip),
    action: mapAssistantAction(message.action),
    usage: mapApiUsage(message.usage),
  }));
}

export function mapCreatedSession(
  sessionId: string,
  title: string,
  model: string,
  createdAt: string | null = null,
): ChatSession {
  return {
    id: sessionId,
    title: truncateSessionTitle(title),
    model,
    createdAtLabel: createdAt ? toCreatedAtLabel(createdAt) : "Today",
    tokenUsage: ZERO_USAGE,
    messages: [],
  };
}

export function mapCreatedSessionResult(
  createdSession: CreateSessionResult,
  fallbackTitle: string,
): ChatSession {
  return mapCreatedSession(
    createdSession.session_id,
    createdSession.title || fallbackTitle,
    createdSession.model,
    createdSession.created_at ?? null,
  );
}
