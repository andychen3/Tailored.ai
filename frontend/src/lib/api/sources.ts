import { request } from "./client";

export type CatalogSourceResult = {
  source_id: string;
  source_type: "youtube" | "video_file" | "pdf" | "text";
  title: string;
  source_url: string | null;
  video_id: string | null;
  file_id: string | null;
  expected_chunk_count: number;
  sync_status: "in_sync" | "missing" | "unknown";
};

export async function listSources(userId: string): Promise<CatalogSourceResult[]> {
  const query = new URLSearchParams({ user_id: userId }).toString();
  const payload = await request<{ sources: CatalogSourceResult[] }>(`/sources?${query}`, {
    method: "GET",
  });
  return payload.sources;
}

export async function deleteSource(sourceId: string): Promise<void> {
  await request<{ success: boolean }>(`/sources/${sourceId}`, {
    method: "DELETE",
  });
}
