from openai import OpenAI
from dotenv import load_dotenv
import os

load_dotenv()


class ChatHistory:
    def __init__(self):
        self.messages = []

    def add_message(self, message):
        self.messages.append(message.to_dict())

    def get_messages(self):
        return self.messages


class Message:
    def __init__(self, role, content):
        self.role = role
        self.content = content

    def to_dict(self):
        return {"role": self.role, "content": self.content}

    def get_content(self):
        return self.content


class ChatManager:
    def __init__(self, model="gpt-4o-mini"):
        self.chat_history = ChatHistory()
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.model = model

    def chat(self):
        print("Assistant: Hello! How can I help you today?\n")
        user_input = Message("user", input("User: "))
        while user_input.get_content() != "exit":
            self.chat_history.add_message(user_input)
            response = self.client.responses.create(
                model=self.model,
                input=self.chat_history.get_messages(),
            )

            self.chat_history.add_message(Message("assistant", response.output_text))
            print("Assistant:", response.output_text)

            user_input = Message("user", input("User: "))


if __name__ == "__main__":
    chat_manager = ChatManager()
    chat_manager.chat()
