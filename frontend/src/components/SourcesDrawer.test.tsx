import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";

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
        onUrlInputChange={() => {}}
        onAddSource={() => {}}
        onUploadFile={() => {}}
        onClose={() => {}}
      />,
    );

    expect(screen.getByText("Needs reindex")).toBeInTheDocument();
    expect(screen.getByText("Missing Video")).toBeInTheDocument();
  });
});
