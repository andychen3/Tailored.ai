import { useCallback, useState } from "react";
import type { Dispatch } from "react";

import { deleteSource as deleteSourceApi, toUserFacingError } from "../../lib/api";
import { canDeleteSource } from "../../lib/chatUtils";
import type { SourceItem } from "../../types/chat";
import type { ChatAction } from "../../state/chatReducer";

export function useSourceActions(
  dispatch: Dispatch<ChatAction>,
  sources: SourceItem[],
  setRequestError: (error: string | null) => void,
) {
  const [deletingSourceId, setDeletingSourceId] = useState<string | null>(null);

  const deleteSource = useCallback(async (localSourceId: number) => {
    const source = sources.find((item) => item.id === localSourceId);
    if (!source || deletingSourceId || !canDeleteSource(source)) {
      return;
    }

    const confirmed = window.confirm("Delete this source? This cannot be undone.");
    if (!confirmed) {
      return;
    }

    setRequestError(null);
    setDeletingSourceId(source.sourceId ?? null);

    try {
      await deleteSourceApi(source.sourceId!);
      dispatch({ type: "REMOVE_SOURCE", sourceId: localSourceId });
    } catch (error) {
      const message = toUserFacingError(error, "Failed to delete source.");
      setRequestError(message);
    } finally {
      setDeletingSourceId(null);
    }
  }, [deletingSourceId, dispatch, setRequestError, sources]);

  return { deletingSourceId, deleteSource };
}
