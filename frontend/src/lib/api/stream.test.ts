import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "./client";
import { parseSseEventBlock, sendMessageStream } from "./stream";

describe("parseSseEventBlock", () => {
  it("parses event names and multi-line data", () => {
    expect(parseSseEventBlock("event: delta\ndata: hello\ndata: world")).toEqual({
      event: "delta",
      data: "hello\nworld",
    });
  });

  it("returns null when no data line is present", () => {
    expect(parseSseEventBlock("event: delta")).toBeNull();
  });
});

describe("sendMessageStream", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("throws on malformed completion payloads", async () => {
    const encoder = new TextEncoder();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "text/event-stream" }),
      body: {
        getReader: () => {
          let done = false;
          return {
            read: async () => {
              if (done) {
                return { value: undefined, done: true };
              }
              done = true;
              return {
                value: encoder.encode("event: completion\ndata: {bad json}\n\n"),
                done: false,
              };
            },
          };
        },
      },
    }));

    await expect(sendMessageStream({ sessionId: "s1", message: "hello" })).rejects.toBeInstanceOf(ApiError);
    await expect(sendMessageStream({ sessionId: "s1", message: "hello" })).rejects.toMatchObject({
      message: "Received malformed streaming data.",
    });
  });
});
