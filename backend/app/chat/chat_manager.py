from openai import OpenAI
from dotenv import load_dotenv
import os
from app.chat.message import Message, ChatHistory
from app.rag.retriever import RAGRetriever

load_dotenv()

RAG_SYSTEM_PROMPT = """You are a helpful assistant that answers questions based on
video content the user has added to their knowledge base. When answering:
- Ground your answers in the provided context
- Apply the advice to the user's specific situation when they share it
- Cite the source video and timestamp when referencing specific points
- Quote timestamps exactly as shown in the context tags (e.g., [Video Title @ 12:34])
- If the context doesn't cover the question, say so honestly
- Do not tell the user to go elsewhere unless they explicitly ask for external resources"""

NO_CONTEXT_MESSAGE = (
    "I couldn't find anything relevant to that in your uploaded videos. "
    "Try rephrasing or ask something more specific to your content."
)


class ChatManager:
    def __init__(self, model: str = "gpt-4o-mini", user_id: str = "default_user") -> None:
        self.chat_history = ChatHistory()
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.model = model
        self.user_id = user_id
        self.retriever = RAGRetriever()

    def add_youtube_video(self, url: str, title: str) -> int:
        count = self.retriever.ingest_youtube_url(self.user_id, url, title)
        return count

    def _build_messages(self, context: str) -> list[dict[str, str]]:
        messages = [{"role": "system", "content": RAG_SYSTEM_PROMPT}]
        messages.append(
            {
                "role": "system",
                "content": f"Relevant context from your knowledge base:\n\n{context}",
            }
        )
        messages.extend(self.chat_history.get_messages())
        return messages

    def answer_question(self, user_input: str) -> tuple[str, list[dict], bool]:
        context, sources, use_rag = self.retriever.query(self.user_id, user_input)
        if not use_rag:
            return NO_CONTEXT_MESSAGE, [], False

        messages = self._build_messages(context or "")
        messages.append({"role": "user", "content": user_input})

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
        )

        answer = response.choices[0].message.content or ""
        self.chat_history.add_message(Message("user", user_input))
        self.chat_history.add_message(Message("assistant", answer))
        return answer, sources, True

    def chat(self) -> None:
        print(
            "Assistant: Hello! Add a YouTube URL to build your knowledge base, then ask questions about your uploaded content.\n"
        )
        print("Commands: 'add <url> | <title>'  or  'exit'\n")

        while True:
            user_input = input("User: ").strip()

            if user_input == "exit":
                break

            # handle the add command
            if user_input.startswith("add "):
                try:
                    _, rest = user_input.split(" ", 1)
                    url, title = rest.split("|")
                    cleaned_url = url.strip()
                    cleaned_title = title.strip()
                    print(f"Ingesting: {cleaned_title}...")
                    count = self.add_youtube_video(cleaned_url, cleaned_title)
                    print(f"Done - {count} chunks stored.\n")
                except ValueError:
                    print("Assistant: Use format - add <url> | <title>\n")
                continue

            try:
                answer, sources, use_rag = self.answer_question(user_input)
            except Exception as e:
                print(f"DEBUG - retriever query failed: {e}")
                continue

            if not use_rag:
                print(f"\nAssistant: {answer}\n")
                continue

            print(f"\nAssistant: {answer}")

            if sources:
                print("\nSources:")
                for s in sources:
                    print(f"  - {s['title']} @ {s['timestamp']}")
            print()
