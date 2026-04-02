import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useChatController } from "./useChatController";

type SendMessageStreamHandlers = {
  onDelta?: (delta: string) => void;
  onCompletion?: (result: {
    reply: string;
    has_context: boolean;
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
    thread_usage: {
      prompt_tokens: number;
      completion_tokens: number;
      total_tokens: number;
    } | null;
    assistant_message_id: string;
  }) => void;
};

function createDeferred() {
  let resolve!: () => void;
  const promise = new Promise<void>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

const apiMocks = vi.hoisted(() => ({
  createSession: vi.fn(),
  deleteSource: vi.fn(),
  deleteSession: vi.fn(),
  getSession: vi.fn(),
  getIngestJob: vi.fn(),
  ingestFile: vi.fn(),
  ingestYoutube: vi.fn(),
  listModels: vi.fn(),
  listSources: vi.fn(),
  listSessions: vi.fn(),
  sendMessage: vi.fn(),
  sendMessageStream: vi.fn(),
  toUserFacingError: vi.fn((error: unknown, fallback: string) => {
    if (error instanceof Error && error.message) {
      return error.message;
    }
    return fallback;
  }),
}));

vi.mock("../lib/api", () => apiMocks);

import * as api from "../lib/api";

const mockedApi = api as unknown as {
  createSession: typeof apiMocks.createSession;
  deleteSource: typeof apiMocks.deleteSource;
  deleteSession: typeof apiMocks.deleteSession;
  getSession: typeof apiMocks.getSession;
  getIngestJob: typeof apiMocks.getIngestJob;
  ingestFile: typeof apiMocks.ingestFile;
  ingestYoutube: typeof apiMocks.ingestYoutube;
  listModels: typeof apiMocks.listModels;
  listSources: typeof apiMocks.listSources;
  listSessions: typeof apiMocks.listSessions;
  sendMessage: typeof apiMocks.sendMessage;
  sendMessageStream: typeof apiMocks.sendMessageStream;
  toUserFacingError: typeof apiMocks.toUserFacingError;
};

describe("useChatController streaming lifecycle", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedApi.createSession.mockResolvedValue({
      session_id: "session_1",
      user_id: "default_user",
      title: "New chat",
      model: "gpt-4o-mini",
      created_at: "2026-04-01T12:00:00.000Z",
    });
    mockedApi.deleteSource.mockResolvedValue(undefined);
    mockedApi.deleteSession.mockResolvedValue(undefined);
    mockedApi.getSession.mockImplementation(async (sessionId: string) => {
      if (sessionId === "session_2") {
        return {
          session: {
            session_id: "session_2",
            user_id: "default_user",
            title: "Second thread",
            model: "gpt-4o-mini",
            created_at: "2026-04-01T13:00:00.000Z",
            updated_at: "2026-04-01T13:00:00.000Z",
            last_message_at: null,
            message_count: 2,
            prompt_tokens_total: 5,
            completion_tokens_total: 9,
            total_tokens_total: 14,
          },
          messages: [
            {
              id: "s2_user",
              role: "user",
              content: "tell me more",
              sources: [],
              usage: null,
              created_at: "2026-04-01T13:00:00.000Z",
            },
            {
              id: "s2_ai",
              role: "assistant",
              content: "Second thread answer",
              sources: [
                {
                  title: "Demo Video",
                  timestamp: "0:30",
                  video_id: "abc123",
                },
              ],
              usage: {
                prompt_tokens: 5,
                completion_tokens: 9,
                total_tokens: 14,
              },
              created_at: "2026-04-01T13:00:01.000Z",
            },
          ],
        };
      }

      return {
        session: {
          session_id: "session_1",
          user_id: "default_user",
          title: "Hello",
          model: "gpt-4o-mini",
          created_at: "2026-04-01T12:00:00.000Z",
          updated_at: "2026-04-01T12:00:00.000Z",
          last_message_at: null,
          message_count: 2,
          prompt_tokens_total: 11,
          completion_tokens_total: 7,
          total_tokens_total: 18,
        },
        messages: [
          {
            id: "s1_user",
            role: "user",
            content: "hello",
            sources: [],
            usage: null,
            created_at: "2026-04-01T12:00:00.000Z",
          },
          {
            id: "s1_ai",
            role: "assistant",
            content: "First thread answer",
            sources: [
              {
                title: "Demo Video",
                timestamp: "0:12",
                video_id: "abc123",
              },
            ],
            usage: {
              prompt_tokens: 11,
              completion_tokens: 7,
              total_tokens: 18,
            },
            created_at: "2026-04-01T12:00:01.000Z",
          },
        ],
      };
    });
    mockedApi.getIngestJob.mockResolvedValue({
      success: true,
      job_id: "job_1",
      source_id: "source_file_1",
      file_id: null,
      file_name: "notes.txt",
      source_type: "text",
      status: "ready",
      chunks_ingested: 1,
      error_message: null,
    });
    mockedApi.ingestFile.mockResolvedValue({
      success: true,
      job_id: "job_1",
      file_name: "notes.txt",
      source_type: "text",
      status: "queued",
    });
    mockedApi.ingestYoutube.mockResolvedValue({
      success: true,
      source_id: "source_yt_1",
      video_id: "abc123",
      video_title: "Video",
      chunks_ingested: 3,
    });
    mockedApi.listModels.mockResolvedValue([
      { id: "gpt-4o-mini", label: "gpt-4o-mini", max_context_tokens: 128000 },
    ]);
    mockedApi.listSources.mockResolvedValue([
      {
        source_id: "source_1",
        user_id: "default_user",
        source_type: "youtube",
        title: "Demo Video",
        source_url: "https://www.youtube.com/watch?v=abc123",
        video_id: "abc123",
        file_id: null,
        expected_chunk_count: 3,
        sync_status: "in_sync",
        last_verified_at: "2026-04-01T12:00:00.000Z",
        created_at: "2026-04-01T12:00:00.000Z",
        updated_at: "2026-04-01T12:00:00.000Z",
      },
    ]);
    mockedApi.listSessions.mockResolvedValue([]);
    mockedApi.sendMessage.mockResolvedValue({
      reply: "Echo: hello",
      has_context: true,
      sources: [],
      usage: null,
      thread_usage: null,
    });
    mockedApi.sendMessageStream.mockReset();
    mockedApi.toUserFacingError.mockImplementation((error: unknown, fallback: string) => {
      if (error instanceof Error && error.message) {
        return error.message;
      }
      return fallback;
    });
  });

  it("assembles streamed deltas into a finalized assistant message", async () => {
    const deferred = createDeferred();
    const completion = {
      reply: "Echo: hello",
      has_context: true,
      sources: [
        {
          title: "Demo Video",
          timestamp: "0:12",
          video_id: "abc123",
        },
      ],
      usage: {
        prompt_tokens: 11,
        completion_tokens: 7,
        total_tokens: 18,
      },
      thread_usage: {
        prompt_tokens: 11,
        completion_tokens: 7,
        total_tokens: 18,
      },
      assistant_message_id: "assistant_1",
    };

    mockedApi.sendMessageStream.mockImplementation(
      async (_payload: { sessionId: string; message: string }, handlers: SendMessageStreamHandlers) => {
        handlers.onDelta?.("Echo");
        await deferred.promise;
        handlers.onDelta?.(": hello");
        handlers.onCompletion?.(completion);
        return completion;
      },
    );

    const { result } = renderHook(() => useChatController());

    await waitFor(() => {
      expect(result.current.hasReadySource).toBe(true);
    });

    expect(result.current.sessions).toHaveLength(0);

    act(() => {
      result.current.setChatInput("hello");
    });

    act(() => {
      void result.current.sendMessage();
    });

    await waitFor(() => {
      expect(result.current.isSendingMessage).toBe(true);
      expect(result.current.currentSessionId).toBe("session_1");
      expect(result.current.chatMessages).toHaveLength(2);
    });

    expect(result.current.chatMessages[0]).toMatchObject({
      role: "user",
      text: "hello",
    });
    expect(result.current.chatMessages[1]).toMatchObject({
      role: "assistant",
      text: "Echo",
      isStreaming: true,
    });

    act(() => {
      deferred.resolve();
    });

    await waitFor(() => {
      expect(result.current.isSendingMessage).toBe(false);
      expect(result.current.chatMessages[1]).toMatchObject({
        role: "assistant",
        text: "Echo: hello",
        isStreaming: false,
      });
    });

    expect(result.current.chatMessages[1].chips).toEqual([
      {
        ts: "0:12",
        title: "Demo Video",
        videoId: "abc123",
        url: undefined,
        pageNumber: undefined,
      },
    ]);
    expect(result.current.chatMessages[1].usage).toEqual({
      promptTokens: 11,
      completionTokens: 7,
      totalTokens: 18,
    });
    expect(result.current.threadTokenUsage).toEqual({
      promptTokens: 11,
      completionTokens: 7,
      totalTokens: 18,
    });
  });

  it("replaces the streaming placeholder with an error message when the stream fails", async () => {
    mockedApi.sendMessageStream.mockImplementation(
      async (_payload: { sessionId: string; message: string }, handlers: SendMessageStreamHandlers) => {
        handlers.onDelta?.("Echo");
        throw new Error("stream exploded");
      },
    );

    const { result } = renderHook(() => useChatController());

    await waitFor(() => {
      expect(result.current.hasReadySource).toBe(true);
    });

    act(() => {
      result.current.setChatInput("hello");
    });

    act(() => {
      void result.current.sendMessage();
    });

    await waitFor(() => {
      expect(result.current.isSendingMessage).toBe(false);
      expect(result.current.chatMessages).toHaveLength(2);
    });

    expect(result.current.chatMessages[1]).toMatchObject({
      role: "assistant",
      text: "I hit an error while contacting the backend: stream exploded",
      isStreaming: false,
    });
  });

  it("switches threads and restores each thread's persisted history", async () => {
    mockedApi.listSessions.mockResolvedValue([
      {
        session_id: "session_1",
        user_id: "default_user",
        title: "Hello",
        model: "gpt-4o-mini",
        created_at: "2026-04-01T12:00:00.000Z",
        updated_at: "2026-04-01T12:00:00.000Z",
        last_message_at: "2026-04-01T12:00:01.000Z",
        message_count: 2,
        prompt_tokens_total: 11,
        completion_tokens_total: 7,
        total_tokens_total: 18,
      },
      {
        session_id: "session_2",
        user_id: "default_user",
        title: "Second thread",
        model: "gpt-4o-mini",
        created_at: "2026-04-01T13:00:00.000Z",
        updated_at: "2026-04-01T13:00:00.000Z",
        last_message_at: "2026-04-01T13:00:01.000Z",
        message_count: 2,
        prompt_tokens_total: 5,
        completion_tokens_total: 9,
        total_tokens_total: 14,
      },
    ]);

    const { result } = renderHook(() => useChatController());

    await waitFor(() => {
      expect(result.current.sessions).toHaveLength(2);
      expect(result.current.currentSessionId).toBe("session_1");
    });

    await waitFor(() => {
      expect(result.current.chatMessages).toHaveLength(2);
      expect(result.current.chatMessages[0]).toMatchObject({
        role: "user",
        text: "hello",
      });
      expect(result.current.chatMessages[1]).toMatchObject({
        role: "assistant",
        text: "First thread answer",
      });
    });

    act(() => {
      void result.current.selectSession("session_2");
    });

    await waitFor(() => {
      expect(result.current.currentSessionId).toBe("session_2");
      expect(result.current.chatMessages).toHaveLength(2);
    });

    expect(result.current.chatMessages[0]).toMatchObject({
      role: "user",
      text: "tell me more",
    });
    expect(result.current.chatMessages[1]).toMatchObject({
      role: "assistant",
      text: "Second thread answer",
      chips: [
        {
          ts: "0:30",
          title: "Demo Video",
          videoId: "abc123",
          url: undefined,
          pageNumber: undefined,
        },
      ],
    });

    act(() => {
      void result.current.selectSession("session_1");
    });

    await waitFor(() => {
      expect(result.current.currentSessionId).toBe("session_1");
      expect(result.current.chatMessages).toHaveLength(2);
    });

    expect(result.current.chatMessages[0]).toMatchObject({
      role: "user",
      text: "hello",
    });
    expect(result.current.chatMessages[1]).toMatchObject({
      role: "assistant",
      text: "First thread answer",
    });
  });

  it("uses the selected model for new threads and restores thread models on switch", async () => {
    mockedApi.listSessions.mockResolvedValue([
      {
        session_id: "session_2",
        user_id: "default_user",
        title: "Second thread",
        model: "gpt-4o",
        created_at: "2026-04-01T13:00:00.000Z",
        updated_at: "2026-04-01T13:00:00.000Z",
        last_message_at: "2026-04-01T13:00:01.000Z",
        message_count: 2,
        prompt_tokens_total: 5,
        completion_tokens_total: 9,
        total_tokens_total: 14,
      },
    ]);

    mockedApi.getSession.mockImplementation(async (sessionId: string) => {
      if (sessionId === "session_2") {
        return {
          session: {
            session_id: "session_2",
            user_id: "default_user",
            title: "Second thread",
            model: "gpt-4o",
            created_at: "2026-04-01T13:00:00.000Z",
            updated_at: "2026-04-01T13:00:00.000Z",
            last_message_at: null,
            message_count: 2,
            prompt_tokens_total: 5,
            completion_tokens_total: 9,
            total_tokens_total: 14,
          },
          messages: [
            {
              id: "s2_user",
              role: "user",
              content: "tell me more",
              sources: [],
              usage: null,
              created_at: "2026-04-01T13:00:00.000Z",
            },
            {
              id: "s2_ai",
              role: "assistant",
              content: "Second thread answer",
              sources: [],
              usage: null,
              created_at: "2026-04-01T13:00:01.000Z",
            },
          ],
        };
      }

      return {
        session: {
          session_id: "session_new",
          user_id: "default_user",
          title: "New chat",
          model: "gpt-4o",
          created_at: "2026-04-01T14:00:00.000Z",
          updated_at: "2026-04-01T14:00:00.000Z",
          last_message_at: null,
          message_count: 0,
          prompt_tokens_total: 0,
          completion_tokens_total: 0,
          total_tokens_total: 0,
        },
        messages: [],
      };
    });

    mockedApi.createSession.mockResolvedValue({
      session_id: "session_new",
      user_id: "default_user",
      title: "New chat",
      model: "gpt-4o",
      created_at: "2026-04-01T14:00:00.000Z",
    });

    const { result } = renderHook(() => useChatController());

    await waitFor(() => {
      expect(result.current.sessions).toHaveLength(1);
      expect(result.current.currentSessionId).toBe("session_2");
    });

    act(() => {
      result.current.setSelectedModel("gpt-4o");
    });

    act(() => {
      void result.current.startNewChat();
    });

    await waitFor(() => {
      expect(mockedApi.createSession).toHaveBeenCalledWith({
        userId: "default_user",
        model: "gpt-4o",
      });
      expect(result.current.currentSessionId).toBe("session_new");
      expect(result.current.sessions[0]?.model).toBe("gpt-4o");
    });

    act(() => {
      void result.current.selectSession("session_2");
    });

    await waitFor(() => {
      expect(result.current.currentSessionId).toBe("session_2");
      expect(result.current.sessions.find((session) => session.id === "session_2")?.model).toBe(
        "gpt-4o",
      );
    });
  });

  it("deletes a non-active session and keeps the current selection", async () => {
    mockedApi.listSessions.mockResolvedValue([
      {
        session_id: "session_1",
        user_id: "default_user",
        title: "Hello",
        model: "gpt-4o-mini",
        created_at: "2026-04-01T12:00:00.000Z",
        updated_at: "2026-04-01T12:00:00.000Z",
        last_message_at: "2026-04-01T12:00:01.000Z",
        message_count: 2,
        prompt_tokens_total: 11,
        completion_tokens_total: 7,
        total_tokens_total: 18,
      },
      {
        session_id: "session_2",
        user_id: "default_user",
        title: "Second thread",
        model: "gpt-4o-mini",
        created_at: "2026-04-01T13:00:00.000Z",
        updated_at: "2026-04-01T13:00:00.000Z",
        last_message_at: "2026-04-01T13:00:01.000Z",
        message_count: 2,
        prompt_tokens_total: 5,
        completion_tokens_total: 9,
        total_tokens_total: 14,
      },
    ]);

    vi.spyOn(window, "confirm").mockReturnValue(true);

    const { result } = renderHook(() => useChatController());

    await waitFor(() => {
      expect(result.current.currentSessionId).toBe("session_1");
      expect(result.current.sessions).toHaveLength(2);
    });

    act(() => {
      void result.current.deleteSession("session_2");
    });

    await waitFor(() => {
      expect(mockedApi.deleteSession).toHaveBeenCalledWith("session_2");
      expect(result.current.sessions.map((session) => session.id)).toEqual(["session_1"]);
    });

    expect(result.current.currentSessionId).toBe("session_1");
    expect(mockedApi.getSession).toHaveBeenCalledTimes(1);
  });

  it("deletes the active session and selects the next remaining session", async () => {
    mockedApi.listSessions.mockResolvedValue([
      {
        session_id: "session_1",
        user_id: "default_user",
        title: "Hello",
        model: "gpt-4o-mini",
        created_at: "2026-04-01T12:00:00.000Z",
        updated_at: "2026-04-01T12:00:00.000Z",
        last_message_at: "2026-04-01T12:00:01.000Z",
        message_count: 2,
        prompt_tokens_total: 11,
        completion_tokens_total: 7,
        total_tokens_total: 18,
      },
      {
        session_id: "session_2",
        user_id: "default_user",
        title: "Second thread",
        model: "gpt-4o-mini",
        created_at: "2026-04-01T13:00:00.000Z",
        updated_at: "2026-04-01T13:00:00.000Z",
        last_message_at: "2026-04-01T13:00:01.000Z",
        message_count: 2,
        prompt_tokens_total: 5,
        completion_tokens_total: 9,
        total_tokens_total: 14,
      },
    ]);

    vi.spyOn(window, "confirm").mockReturnValue(true);

    const { result } = renderHook(() => useChatController());

    await waitFor(() => {
      expect(result.current.currentSessionId).toBe("session_1");
      expect(result.current.chatMessages[1]?.text).toBe("First thread answer");
    });

    act(() => {
      void result.current.deleteSession("session_1");
    });

    await waitFor(() => {
      expect(result.current.currentSessionId).toBe("session_2");
      expect(result.current.sessions.map((session) => session.id)).toEqual(["session_2"]);
      expect(result.current.chatMessages[1]?.text).toBe("Second thread answer");
    });

    expect(mockedApi.getSession).toHaveBeenCalledWith("session_2");
  });

  it("deletes the last remaining session and falls back to the empty state", async () => {
    mockedApi.listSessions.mockResolvedValue([
      {
        session_id: "session_1",
        user_id: "default_user",
        title: "Hello",
        model: "gpt-4o-mini",
        created_at: "2026-04-01T12:00:00.000Z",
        updated_at: "2026-04-01T12:00:00.000Z",
        last_message_at: "2026-04-01T12:00:01.000Z",
        message_count: 2,
        prompt_tokens_total: 11,
        completion_tokens_total: 7,
        total_tokens_total: 18,
      },
    ]);

    vi.spyOn(window, "confirm").mockReturnValue(true);

    const { result } = renderHook(() => useChatController());

    await waitFor(() => {
      expect(result.current.currentSessionId).toBe("session_1");
      expect(result.current.sessions).toHaveLength(1);
    });

    act(() => {
      void result.current.deleteSession("session_1");
    });

    await waitFor(() => {
      expect(result.current.sessions).toHaveLength(0);
      expect(result.current.currentSessionId).toBeNull();
      expect(result.current.chatMessages).toEqual([]);
      expect(result.current.showEmptyState).toBe(true);
    });
  });

  it("deletes a ready source after confirmation", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);

    const { result } = renderHook(() => useChatController());

    await waitFor(() => {
      expect(result.current.sources).toHaveLength(1);
      expect(result.current.sources[0]?.sourceId).toBe("source_1");
    });

    act(() => {
      void result.current.deleteSource(result.current.sources[0]!.id);
    });

    await waitFor(() => {
      expect(mockedApi.deleteSource).toHaveBeenCalledWith("source_1");
      expect(result.current.sources).toHaveLength(0);
    });
  });

  it("keeps the source visible when deletion fails", async () => {
    mockedApi.deleteSource.mockRejectedValueOnce(new Error("delete failed"));
    vi.spyOn(window, "confirm").mockReturnValue(true);

    const { result } = renderHook(() => useChatController());

    await waitFor(() => {
      expect(result.current.sources).toHaveLength(1);
    });

    act(() => {
      void result.current.deleteSource(result.current.sources[0]!.id);
    });

    await waitFor(() => {
      expect(result.current.requestError).toBe("delete failed");
      expect(result.current.sources).toHaveLength(1);
    });
  });

  it("does not call the delete API when source deletion is canceled", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(false);

    const { result } = renderHook(() => useChatController());

    await waitFor(() => {
      expect(result.current.sources).toHaveLength(1);
    });

    act(() => {
      void result.current.deleteSource(result.current.sources[0]!.id);
    });

    await waitFor(() => {
      expect(mockedApi.deleteSource).not.toHaveBeenCalled();
      expect(result.current.sources).toHaveLength(1);
    });
  });
});
