import { fireEvent, render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";

import { SourcesDrawer } from "./SourcesDrawer";
import type { SourceItem } from "../types/chat";

const missingSource: SourceItem = {
  id: 1,
  sourceId: "source_missing",
  url: "https://www.youtube.com/watch?v=missing",
  title: "Missing Video",
  status: "ready",
  chunks: 12,
  syncStatus: "missing",
  sourceType: "youtube",
};

describe("SourcesDrawer", () => {
  it("shows a stale badge for missing sources", () => {
    render(
      <SourcesDrawer
        isOpen
        sources={[missingSource]}
        urlInput=""
        isAddingSource={false}
        deletingSourceId={null}
        onUrlInputChange={() => {}}
        onAddSource={() => {}}
        onDeleteSource={() => {}}
        onUploadFile={() => {}}
        onClose={() => {}}
      />,
    );

    expect(screen.getByText("Needs reindex")).toBeInTheDocument();
    expect(screen.getByText("Missing Video")).toBeInTheDocument();
  });

  it("shows delete for a ready source and calls the handler", () => {
    const onDeleteSource = vi.fn();

    render(
      <SourcesDrawer
        isOpen
        sources={[missingSource]}
        urlInput=""
        isAddingSource={false}
        deletingSourceId={null}
        onUrlInputChange={() => {}}
        onAddSource={() => {}}
        onDeleteSource={onDeleteSource}
        onUploadFile={() => {}}
        onClose={() => {}}
      />,
    );

    fireEvent.click(screen.getByLabelText("Delete Missing Video"));

    expect(onDeleteSource).toHaveBeenCalledWith(1);
  });

  it("does not show delete for a processing source", () => {
    render(
      <SourcesDrawer
        isOpen
        sources={[
          {
            id: 2,
            url: "https://www.youtube.com/watch?v=processing",
            title: "Processing Video",
            status: "processing",
            chunks: 0,
            sourceType: "youtube",
            syncStatus: "unknown",
          },
        ]}
        urlInput=""
        isAddingSource={false}
        deletingSourceId={null}
        onUrlInputChange={() => {}}
        onAddSource={() => {}}
        onDeleteSource={() => {}}
        onUploadFile={() => {}}
        onClose={() => {}}
      />,
    );

    expect(screen.queryByLabelText("Delete Processing Video")).not.toBeInTheDocument();
  });
});
