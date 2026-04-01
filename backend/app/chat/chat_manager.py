import re

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
- Quote timestamps exactly as shown in the context tags (e.g. Source: [Video Title @ 12:34])
- If the context doesn't cover the question, say so honestly
- Do not tell the user to go elsewhere unless they explicitly ask for external resources

Response style (adaptive):
- Start with a natural direct answer in 1 sentence.
- Use concise bullets only when they help clarity (typically 2-5 bullets).
- If user is asking for advice include a sentence or two at the end with what they should do next.

Shape by user intent:
- Explanatory question -> concise definition and key concepts.
- Advice question -> practical guidance and clear next steps.
- Comparison question -> side-by-side pros/cons style bullets (no markdown tables).

Style and readability:
- Keep language clear and simple.
- Keep paragraphs short.
- Preserve helpful line breaks.
- Do not use markdown tables.
- Do not use markdown formatting.
- If context is missing, say so directly and do not invent details.

Citation handling:
- Do not put a list of Sources at the end of the response.
- Do not fabricate timestamps.
- Do not fabricate sources.
- When citing a source within a bullet point, place the citation on its own new line directly below the bullet text, like this:
  - Key concept explanation here.
    [Source: Video Title @ 12:34]"""

NO_CONTEXT_MESSAGE = (
    "I couldn't find anything relevant to that in your uploaded videos. "
    "Try rephrasing or ask something more specific to your content."
)


class ChatManager:
    MAX_CONTEXT_BLOCKS = 3
    MAX_CONTEXT_CHARS_PER_BLOCK = 900
    MAX_CONTEXT_TOTAL_CHARS = 2600

    def __init__(
        self, model: str = "gpt-4o-mini", user_id: str = "default_user"
    ) -> None:
        self.chat_history = ChatHistory()
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.model = model
        self.user_id = user_id
        self.retriever = RAGRetriever()

    def add_youtube_video(self, url: str, title: str) -> int:
        count = self.retriever.ingest_youtube_url(self.user_id, url, title)
        return count

    def _format_context_for_prompt(self, context: str) -> str:
        if not context:
            return ""

        blocks = [b.strip() for b in context.split("\n\n---\n\n") if b.strip()]
        cleaned_blocks: list[str] = []
        seen_bodies: set[str] = set()
        total_chars = 0

        for block in blocks:
            lines = [line.strip() for line in block.splitlines() if line.strip()]
            if not lines:
                continue

            source_tag = (
                lines[0]
                if lines[0].startswith("[") and lines[0].endswith("]")
                else "[Source]"
            )
            body_lines = lines[1:] if source_tag != "[Source]" else lines
            body = " ".join(body_lines)
            body = " ".join(body.split())
            if not body:
                continue

            if body in seen_bodies:
                continue
            seen_bodies.add(body)

            if len(body) > self.MAX_CONTEXT_CHARS_PER_BLOCK:
                body = f"{body[: self.MAX_CONTEXT_CHARS_PER_BLOCK - 3].rstrip()}..."

            cleaned_block = f"{source_tag}\n{body}"
            if total_chars + len(cleaned_block) > self.MAX_CONTEXT_TOTAL_CHARS:
                break

            cleaned_blocks.append(cleaned_block)
            total_chars += len(cleaned_block)

            if len(cleaned_blocks) >= self.MAX_CONTEXT_BLOCKS:
                break

        return "\n\n---\n\n".join(cleaned_blocks)

    def _build_messages(self, context: str) -> list[dict[str, str]]:
        formatted_context = self._format_context_for_prompt(context)
        messages = [{"role": "system", "content": RAG_SYSTEM_PROMPT}]
        messages.append(
            {
                "role": "system",
                "content": f"Relevant context from your knowledge base:\n\n{formatted_context}",
            }
        )
        messages.extend(self.chat_history.get_messages())
        return messages

    def _strip_markdown(self, text: str) -> str:
        text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
        text = re.sub(r"\*(.+?)\*", r"\1", text)
        return text

    def _strip_model_sources_section(self, answer: str) -> str:
        lines = answer.splitlines()
        for i, line in enumerate(lines):
            if line.strip().lower().startswith("sources:"):
                return "\n".join(lines[:i]).rstrip()
        return answer.strip()

    def _format_sources_section(self, sources: list[dict]) -> str:
        if not sources:
            return ""

        source_lines: list[str] = []
        seen_labels: set[str] = set()

        for source in sources:
            title = (source.get("title") or "").strip()
            timestamp = (source.get("timestamp") or "").strip()

            if title and timestamp:
                label = f"{title} @ {timestamp}"
            elif title:
                label = title
            elif timestamp:
                label = timestamp
            else:
                label = "Source"

            if label in seen_labels:
                continue
            seen_labels.add(label)
            source_lines.append(f"- {label}")

        if not source_lines:
            return ""

        return "Sources:\n" + "\n".join(source_lines)

    def _append_sources_to_answer(self, answer: str, sources: list[dict]) -> str:
        base_answer = self._strip_markdown(
            self._strip_model_sources_section(answer or "")
        )
        sources_section = self._format_sources_section(sources)
        if not sources_section:
            return base_answer
        if not base_answer:
            return sources_section
        return f"{base_answer}\n\n{sources_section}"

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

        raw_answer = response.choices[0].message.content or ""
        answer = self._append_sources_to_answer(raw_answer, sources)
        self.chat_history.add_message(Message("user", user_input))
        self.chat_history.add_message(Message("assistant", answer))
        return answer, sources, True

    def chat(self) -> None:

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

            print()
