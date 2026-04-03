import { ApiError, parseJson } from "./client";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";
const BACKEND_URL = import.meta.env.VITE_BACKEND_URL ?? "http://127.0.0.1:8000";
const CHUNK_SIZE_BYTES = 10 * 1024 * 1024;
const CHUNKED_UPLOAD_THRESHOLD_BYTES = 50 * 1024 * 1024;

export function xhrPost(
  url: string,
  form: FormData,
  onProgress?: (loaded: number, total: number) => void,
): Promise<unknown> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", url);

    if (onProgress) {
      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable) {
          onProgress(event.loaded, event.total);
        }
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

export async function uploadInSingleRequest(
  userId: string,
  file: File,
  onProgress?: (percent: number) => void,
) {
  const form = new FormData();
  form.append("user_id", userId);
  form.append("file", file);
  return xhrPost(
    `${API_BASE_URL}/ingest/file`,
    form,
    onProgress ? (loaded, total) => onProgress(Math.min(100, Math.round((loaded / total) * 100))) : undefined,
  );
}

export async function uploadInChunks(
  userId: string,
  file: File,
  onProgress?: (percent: number) => void,
) {
  const uploadId = crypto.randomUUID();
  const totalChunks = Math.ceil(file.size / CHUNK_SIZE_BYTES);
  let bytesUploaded = 0;

  for (let index = 0; index < totalChunks; index += 1) {
    const start = index * CHUNK_SIZE_BYTES;
    const slice = file.slice(start, start + CHUNK_SIZE_BYTES);

    let blob: Blob;
    try {
      blob = new Blob([await slice.arrayBuffer()]);
    } catch (error) {
      if (error instanceof DOMException && error.name === "NotReadableError") {
        throw new ApiError(
          "This file could not be read. If it is stored in OneDrive or iCloud, download it locally first, then try again.",
          0,
        );
      }
      throw error;
    }

    const form = new FormData();
    form.append("upload_id", uploadId);
    form.append("chunk_index", String(index));
    form.append("chunk", blob, file.name);

    await xhrPost(`${BACKEND_URL}/ingest/upload-chunk`, form, (loaded) => {
      if (!onProgress) {
        return;
      }
      onProgress(
        Math.min(
          99,
          Math.round(((bytesUploaded + loaded) / file.size) * 100),
        ),
      );
    });

    bytesUploaded += blob.size;
    if (onProgress) {
      onProgress(Math.min(99, Math.round((bytesUploaded / file.size) * 100)));
    }
  }

  const completeForm = new FormData();
  completeForm.append("upload_id", uploadId);
  completeForm.append("file_name", file.name);
  completeForm.append("total_chunks", String(totalChunks));
  completeForm.append("user_id", userId);

  const result = await xhrPost(`${BACKEND_URL}/ingest/upload-complete`, completeForm);
  if (onProgress) {
    onProgress(100);
  }
  return result;
}

export function shouldUseChunkedUpload(file: File): boolean {
  return file.size > CHUNKED_UPLOAD_THRESHOLD_BYTES;
}
