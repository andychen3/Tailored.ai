EXPORT_INTENT_PATTERNS = (
    "save this to notion",
    "summarize this thread into notion",
    "export this conversation to notion",
)


def detect_chat_intent(message: str) -> str | None:
    normalized = " ".join(message.strip().lower().split())
    if not normalized:
        return None
    for pattern in EXPORT_INTENT_PATTERNS:
        if pattern in normalized:
            return "notion_export"
    return None
