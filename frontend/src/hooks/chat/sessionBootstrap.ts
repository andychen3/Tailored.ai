import { DEFAULT_USER_ID } from "../../constants/chatRuntime";
import { createSession as createSessionApi } from "../../lib/api";
import { mapCreatedSessionResult } from "./messageMappers";
import type { Dispatch } from "react";
import type { ChatAction } from "../../state/chatReducer";

export async function ensureSession(
  {
    currentSessionId,
    selectedModel,
    userText,
    dispatch,
  }: {
    currentSessionId: string | null;
    selectedModel: string;
    userText: string;
    dispatch: Dispatch<ChatAction>;
  },
): Promise<{ sessionId: string; isNewSession: boolean }> {
  if (currentSessionId) {
    return { sessionId: currentSessionId, isNewSession: false };
  }

  const createdSession = await createSessionApi({
    userId: DEFAULT_USER_ID,
    model: selectedModel,
  });
  const session = mapCreatedSessionResult(createdSession, userText);
  dispatch({ type: "CREATE_SESSION", session });
  return { sessionId: session.id, isNewSession: true };
}
