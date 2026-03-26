from openai import OpenAI
from dotenv import load_dotenv
import os
from chat.message import Message, ChatHistory

load_dotenv()


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
