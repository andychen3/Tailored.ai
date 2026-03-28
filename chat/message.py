class Message:
    def __init__(self, role: str, content: str) -> None:
        self.role = role
        self.content = content

    def to_dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}

    def get_content(self) -> str:
        return self.content


class ChatHistory:
    def __init__(self) -> None:
        self.messages = []

    def add_message(self, message: Message) -> None:
        self.messages.append(message.to_dict())

    def get_messages(self) -> list[dict[str, str]]:
        return self.messages
