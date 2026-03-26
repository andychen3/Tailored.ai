class Message:
    def __init__(self, role, content):
        self.role = role
        self.content = content

    def to_dict(self):
        return {"role": self.role, "content": self.content}

    def get_content(self):
        return self.content


class ChatHistory:
    def __init__(self):
        self.messages = []

    def add_message(self, message):
        self.messages.append(message.to_dict())

    def get_messages(self):
        return self.messages
