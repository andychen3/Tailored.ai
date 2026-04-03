import { beforeEach, describe, expect, it, vi } from "vitest";

const requestMock = vi.hoisted(() => vi.fn());
const shouldUseChunkedUploadMock = vi.hoisted(() => vi.fn());
const uploadInChunksMock = vi.hoisted(() => vi.fn());
const uploadInSingleRequestMock = vi.hoisted(() => vi.fn());

vi.mock("./client", () => ({
  request: requestMock,
}));

vi.mock("./upload", () => ({
  shouldUseChunkedUpload: shouldUseChunkedUploadMock,
  uploadInChunks: uploadInChunksMock,
  uploadInSingleRequest: uploadInSingleRequestMock,
}));

import { getIngestJob, ingestFile } from "./ingest";

describe("ingestFile", () => {
  const file = new File(["hello"], "notes.txt", { type: "text/plain" });

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("uses the small-file upload path when chunking is not needed", async () => {
    shouldUseChunkedUploadMock.mockReturnValue(false);
    uploadInSingleRequestMock.mockResolvedValue({
      success: true,
      job_id: "job_small",
      file_name: "notes.txt",
      source_type: "text",
      status: "queued",
    });

    await expect(ingestFile("user_1", file)).resolves.toMatchObject({
      job_id: "job_small",
      source_type: "text",
    });
    expect(uploadInSingleRequestMock).toHaveBeenCalledWith("user_1", file, undefined);
    expect(uploadInChunksMock).not.toHaveBeenCalled();
  });

  it("uses the chunked upload path when required", async () => {
    shouldUseChunkedUploadMock.mockReturnValue(true);
    uploadInChunksMock.mockResolvedValue({
      success: true,
      job_id: "job_large",
      file_name: "notes.txt",
      source_type: "text",
      status: "queued",
    });

    await expect(ingestFile("user_1", file)).resolves.toMatchObject({
      job_id: "job_large",
      source_type: "text",
    });
    expect(uploadInChunksMock).toHaveBeenCalledWith("user_1", file, undefined);
    expect(uploadInSingleRequestMock).not.toHaveBeenCalled();
  });
});

describe("getIngestJob", () => {
  it("requests the job status endpoint", async () => {
    requestMock.mockResolvedValue({ job_id: "job_1", status: "ready" });

    await expect(getIngestJob("job_1")).resolves.toMatchObject({ status: "ready" });
    expect(requestMock).toHaveBeenCalledWith("/ingest/jobs/job_1", { method: "GET" });
  });
});
