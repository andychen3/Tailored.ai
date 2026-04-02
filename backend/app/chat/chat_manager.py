import re
from dataclasses import dataclass

from openai import OpenAI
from dotenv import load_dotenv
import os
from app.rag.retriever import RAGRetriever

load_dotenv()

RAG_SYSTEM_PROMPT = """You are a helpful assistant that answers questions based on
content the user has added to their knowledge base. When answering:
- Ground your answers in the provided context
- Apply the advice to the user's specific situation when they share it
- Cite the source exactly as shown in the context tags (e.g. [Video Title @ 12:34] or [report.pdf p.5])
- If no timestamp or page is available, cite just the source title
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
- Do not fabricate timestamps.
- Do not fabricate sources.
- When citing a source within a bullet point, place the citation on its own new line directly below the bullet text, like this:
  - Key concept explanation here.
    [Source: Video Title @ 12:34]"""

NO_CONTEXT_MESSAGE = (
    "I couldn't find anything relevant to that in your knowledge base. "
    "Try rephrasing or ask something more specific to your content."
)


@dataclass(slots=True)
class ChatCompletionRequest:
    messages: list[dict[str, str]]
    sources: list[dict]
    has_context: bool


class ChatManager:
    MAX_CONTEXT_BLOCKS = 3
    MAX_CONTEXT_CHARS_PER_BLOCK = 900
    MAX_CONTEXT_TOTAL_CHARS = 2600

    def __init__(
        self, model: str = "gpt-4o-mini", user_id: str = "default_user"
    ) -> None:
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.model = model
        self.user_id = user_id
        self.retriever = RAGRetriever()

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

    def _build_messages(
        self,
        context: str,
        history: list[dict[str, str]],
    ) -> list[dict[str, str]]:
        formatted_context = self._format_context_for_prompt(context)
        messages = [{"role": "system", "content": RAG_SYSTEM_PROMPT}]
        messages.append(
            {
                "role": "system",
                "content": f"Relevant context from your knowledge base:\n\n{formatted_context}",
            }
        )
        messages.extend(history)
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

    def build_completion_request(
        self,
        user_input: str,
        history: list[dict[str, str]] | None = None,
    ) -> ChatCompletionRequest:
        context, sources, use_rag = self.retriever.query(self.user_id, user_input)
        if not use_rag:
            return ChatCompletionRequest(messages=[], sources=[], has_context=False)

        messages = self._build_messages(context or "", history or [])
        messages.append({"role": "user", "content": user_input})
        return ChatCompletionRequest(messages=messages, sources=sources, has_context=True)

    def finalize_answer(self, raw_answer: str) -> str:
        return self._strip_markdown(self._strip_model_sources_section(raw_answer))

    def answer_question(
        self,
        user_input: str,
        history: list[dict[str, str]] | None = None,
    ) -> tuple[str, list[dict], bool, dict[str, int] | None]:
        request = self.build_completion_request(user_input, history)
        if not request.has_context:
            return NO_CONTEXT_MESSAGE, [], False, None

        response = self.client.chat.completions.create(
            model=self.model,
            messages=request.messages,
        )

        raw_answer = response.choices[0].message.content or ""
        answer = self.finalize_answer(raw_answer)
        usage = getattr(response, "usage", None)
        usage_payload = None
        if usage is not None:
            usage_payload = {
                "prompt_tokens": int(getattr(usage, "prompt_tokens", 0) or 0),
                "completion_tokens": int(getattr(usage, "completion_tokens", 0) or 0),
                "total_tokens": int(getattr(usage, "total_tokens", 0) or 0),
            }
        return answer, sources, True, usage_payload
