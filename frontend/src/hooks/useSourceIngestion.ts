import { useCallback, useState } from "react";
import type { Dispatch } from "react";

import { createId, detectSourceTitle, detectFileSourceType } from "../lib/chatUtils";
import {
  getIngestJob,
  ingestFile,
  ingestYoutube,
  toUserFacingError,
} from "../lib/api";
import type { SourceType } from "../types/chat";
import type { ChatAction } from "../state/chatReducer";

const INGEST_POLL_INTERVAL_MS = 1500;

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

export function useSourceIngestion(
  dispatch: Dispatch<ChatAction>,
  userId: string,
  urlInput: string,
  setRequestError: (error: string | null) => void,
) {
  const [isAddingSource, setIsAddingSource] = useState(false);

  const uploadFile = useCallback(
    async (file: File) => {
      if (isAddingSource) return;

      setRequestError(null);
      setIsAddingSource(true);

      const sourceId = createId();
      dispatch({
        type: "ADD_SOURCE",
        source: {
          id: sourceId,
          url: file.name,
          title: file.name,
          status: "uploading",
          chunks: 0,
          sourceType: detectFileSourceType(file.name),
          syncStatus: "unknown",
          uploadPercent: 0,
        },
      });

      try {
        const result = await ingestFile(userId, file, (uploadPercent) => {
          dispatch({
            type: "UPDATE_SOURCE_UPLOAD",
            sourceId,
            uploadPercent,
          });
        });

        dispatch({
          type: "MARK_SOURCE_QUEUED",
          sourceId,
          jobId: result.job_id,
          sourceType: result.source_type as SourceType,
        });

        while (true) {
          const job = await getIngestJob(result.job_id);

          if (job.status === "queued") {
            dispatch({
              type: "MARK_SOURCE_QUEUED",
              sourceId,
              jobId: job.job_id,
              sourceType: job.source_type as SourceType,
            });
          } else if (job.status === "processing") {
            dispatch({
              type: "MARK_SOURCE_PROCESSING",
              sourceId,
              jobId: job.job_id,
              sourceType: job.source_type as SourceType,
            });
          } else if (job.status === "ready") {
            dispatch({
              type: "MARK_SOURCE_READY",
              sourceId,
              persistentSourceId: job.source_id ?? undefined,
              chunks: job.chunks_ingested ?? 0,
              title: job.file_name,
              fileId: job.file_id ?? undefined,
              sourceType: job.source_type as SourceType,
            });
            break;
          } else {
            throw new Error(job.error_message ?? "File ingestion failed.");
          }

          await sleep(INGEST_POLL_INTERVAL_MS);
        }
      } catch (error) {
        const message = toUserFacingError(error, "Failed to upload file.");
        dispatch({ type: "MARK_SOURCE_ERROR", sourceId, errorMessage: message });
        setRequestError(message);
      } finally {
        setIsAddingSource(false);
      }
    },
    [isAddingSource, dispatch, userId, setRequestError],
  );

  const addSource = useCallback(async () => {
    const url = urlInput.trim();
    if (!url || isAddingSource) {
      return;
    }

    setRequestError(null);
    setIsAddingSource(true);

    const sourceId = createId();
    dispatch({
      type: "ADD_SOURCE",
      source: {
        id: sourceId,
        url,
        title: detectSourceTitle(url),
        status: "processing",
        chunks: 0,
        sourceType: "youtube",
        syncStatus: "unknown",
      },
    });

    try {
      const result = await ingestYoutube({
        userId,
        url,
      });

      dispatch({
        type: "MARK_SOURCE_READY",
        sourceId,
        persistentSourceId: result.source_id,
        chunks: result.chunks_ingested,
        videoId: result.video_id,
        title: result.video_title,
        sourceType: "youtube",
      });
    } catch (error) {
      const message = toUserFacingError(error, "Failed to add source.");
      dispatch({
        type: "MARK_SOURCE_ERROR",
        sourceId,
        errorMessage: message,
      });
      setRequestError(message);
    } finally {
      setIsAddingSource(false);
    }
  }, [isAddingSource, urlInput, dispatch, userId, setRequestError]);

  return { isAddingSource, uploadFile, addSource };
}
