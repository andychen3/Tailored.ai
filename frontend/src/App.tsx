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
    isAddingSource,
    deletingSourceId,
    isSendingMessage,
    isDisconnectingNotion,
    deletingSessionId,
    requestError,
    availableModels,
    selectedModel,
    threadTokenUsage,
    threadTokenLimit,
    toggleNav,
    toggleDrawer,
    closeDrawer,
    closePanels,
    setUrlInput,
    setChatInput,
    setSelectedModel,
    addSource,
    deleteSource,
    uploadFile,
    sendMessage,
    handleAssistantAction,
    handleDisconnectNotion,
    startNewChat,
    selectSession,
    deleteSession,
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
        isDisconnectingNotion={isDisconnectingNotion}
        sessions={sessions}
        currentSessionId={currentSessionId}
        deletingSessionId={deletingSessionId}
        onToggle={toggleNav}
        onNewChat={startNewChat}
        onDisconnectNotion={handleDisconnectNotion}
        onSelectSession={selectSession}
        onDeleteSession={deleteSession}
      />

      <ChatArea
        title={chatTitle}
        isDrawerOpen={isDrawerOpen}
        hasReadySource={hasReadySource}
        showEmptyState={showEmptyState}
        messages={chatMessages}
        chatInput={chatInput}
        isSendingMessage={isSendingMessage}
        requestError={requestError}
        availableModels={availableModels}
        selectedModel={selectedModel}
        canSelectModel
        threadTokenUsage={threadTokenUsage}
        threadTokenLimit={threadTokenLimit}
        onChatInputChange={setChatInput}
        onSelectModel={setSelectedModel}
        onSendMessage={sendMessage}
        onToggleDrawer={toggleDrawer}
        onAssistantAction={handleAssistantAction}
      />

      <SourcesDrawer
        isOpen={isDrawerOpen}
        sources={sources}
        urlInput={urlInput}
        isAddingSource={isAddingSource}
        deletingSourceId={deletingSourceId}
        onUrlInputChange={setUrlInput}
        onAddSource={addSource}
        onDeleteSource={deleteSource}
        onUploadFile={uploadFile}
        onClose={closeDrawer}
      />
    </div>
  );
}

export default App;
