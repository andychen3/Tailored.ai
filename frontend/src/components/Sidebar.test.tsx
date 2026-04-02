import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Sidebar } from "./Sidebar";
import type { ChatSession } from "../types/chat";

const session: ChatSession = {
  id: "session_1",
  title: "First chat",
  model: "gpt-4o-mini",
  createdAtLabel: "Today",
  tokenUsage: {
    promptTokens: 1,
    completionTokens: 2,
    totalTokens: 3,
  },
  messages: [],
};

describe("Sidebar", () => {
  it("deletes a conversation without selecting it", () => {
    const onSelectSession = vi.fn();
    const onDeleteSession = vi.fn();
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);

    render(
      <Sidebar
        isOpen
        canStartChat
        sessions={[session]}
        currentSessionId={session.id}
        deletingSessionId={null}
        onToggle={() => {}}
        onNewChat={() => {}}
        onSelectSession={onSelectSession}
        onDeleteSession={(sessionId) => {
          if (window.confirm("Delete this conversation? This cannot be undone.")) {
            onDeleteSession(sessionId);
          }
        }}
      />,
    );

    fireEvent.click(screen.getByLabelText("Delete First chat"));

    expect(confirmSpy).toHaveBeenCalledWith("Delete this conversation? This cannot be undone.");
    expect(onDeleteSession).toHaveBeenCalledWith("session_1");
    expect(onSelectSession).not.toHaveBeenCalled();
  });
});
