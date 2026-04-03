import { API_BASE_URL, ApiError, parseJson } from "./client";
import type { SendMessagePayload, SendMessageStreamResult } from "./chat";

export type SendMessageStreamHandlers = {
  onDelta?: (delta: string) => void;
  onCompletion?: (result: SendMessageStreamResult) => void;
};

export function parseSseEventBlock(block: string): { event: string; data: string } | null {
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
          sources?: SendMessageStreamResult["sources"];
          action?: SendMessageStreamResult["action"];
          usage?: SendMessageStreamResult["usage"];
          thread_usage?: SendMessageStreamResult["thread_usage"];
          assistant_message_id?: string;
        };
        completion = {
          reply: completionData.reply ?? "",
          sources: completionData.sources ?? [],
          action: completionData.action ?? null,
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
