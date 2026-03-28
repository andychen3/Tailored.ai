import { ChatArea } from "./components/ChatArea";
import { Sidebar } from "./components/Sidebar";
import { SourcesDrawer } from "./components/SourcesDrawer";
import { useChatController } from "./hooks/useChatController";

function App() {
  const {
    isLargeScreen,
    isNavOpen,
    isDrawerOpen,
    hasReadySource,
    sessions,
    currentSessionId,
    chatTitle,
    chatMessages,
    showEmptyState,
    chatInput,
    sources,
    urlInput,
    toggleNav,
    toggleDrawer,
    openDrawer,
    closeDrawer,
    closePanels,
    setUrlInput,
    setChatInput,
    addSource,
    sendMessage,
    startNewChat,
    selectSession,
  } = useChatController();

  return (
    <div className="relative flex h-dvh animate-fadeUp overflow-hidden bg-bg">
      {!isLargeScreen && (isNavOpen || isDrawerOpen) ? (
        <button
          type="button"
          className="absolute inset-0 z-20 bg-black/50"
          onClick={closePanels}
          aria-label="Close panels"
        />
      ) : null}

      <Sidebar
        isOpen={isNavOpen}
        canStartChat={hasReadySource}
        sessions={sessions}
        currentSessionId={currentSessionId}
        onToggle={toggleNav}
        onNewChat={startNewChat}
        onSelectSession={selectSession}
      />

      <ChatArea
        title={chatTitle}
        isDrawerOpen={isDrawerOpen}
        hasReadySource={hasReadySource}
        showEmptyState={showEmptyState}
        messages={chatMessages}
        chatInput={chatInput}
        onChatInputChange={setChatInput}
        onSendMessage={sendMessage}
        onToggleDrawer={toggleDrawer}
        onOpenDrawer={openDrawer}
      />

      <SourcesDrawer
        isOpen={isDrawerOpen}
        sources={sources}
        urlInput={urlInput}
        onUrlInputChange={setUrlInput}
        onAddSource={addSource}
        onClose={closeDrawer}
      />
    </div>
  );
}

export default App;
