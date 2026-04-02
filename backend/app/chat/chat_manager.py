import logging
import os
import re
from dataclasses import dataclass

from dotenv import load_dotenv
from openai import OpenAI

from app.chat.constants import NO_CONTEXT_MESSAGE
from app.rag.retriever import RAGRetriever

load_dotenv()

logger = logging.getLogger(__name__)

RAG_SYSTEM_PROMPT = """You are a helpful assistant that answers questions based on
content the user has added to their knowledge base. When answering:
- Ground your answers in the provided context
- Apply the advice to the user's specific situation when they share it
- Cite the source exactly as shown in the context tags using square brackets (e.g. [Video Title @ 12:34] or [report.pdf p.5])
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
    [Video Title @ 12:34]"""

RETRIEVAL_REWRITE_SYSTEM_PROMPT = """Rewrite the user's latest message into a concise standalone search query for retrieval.

Rules:
- Return only the rewritten search query.
- If the latest message is already self-contained, return it unchanged.
- Resolve references like "that", "those", "them", "give me examples", or "what about pricing" using the recent conversation.
- Do not answer the question.
- Do not add facts or terms not supported by the conversation.
- Preserve important nouns, entities, file names, source names, and time qualifiers.
- Keep the rewrite concise and specific."""


@dataclass(slots=True)
class ChatCompletionRequest:
    messages: list[dict[str, str]]
    sources: list[dict]
    has_context: bool


class ChatManager:
    MAX_CONTEXT_BLOCKS = 3
    MAX_CONTEXT_CHARS_PER_BLOCK = 900
    MAX_CONTEXT_TOTAL_CHARS = 2600
    MAX_REWRITE_CHARS = 300
    MAX_REWRITE_TURNS_PER_ROLE = 2

    def __init__(
        self, model: str = "gpt-4o-mini", user_id: str = "default_user"
    ) -> None:
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.model = model
        self.user_id = user_id
        self.retriever = RAGRetriever()

    def _format_context_for_prompt(
        self, context: str,
    ) -> tuple[str, set[str]]:
        if not context:
            return "", set()

        blocks = [b.strip() for b in context.split("\n\n---\n\n") if b.strip()]
        cleaned_blocks: list[str] = []
        surviving_tags: set[str] = set()
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
            surviving_tags.add(source_tag)
            total_chars += len(cleaned_block)

            if len(cleaned_blocks) >= self.MAX_CONTEXT_BLOCKS:
                break

        return "\n\n---\n\n".join(cleaned_blocks), surviving_tags

    def _build_messages(
        self,
        context: str,
        history: list[dict[str, str]],
    ) -> tuple[list[dict[str, str]], set[str]]:
        formatted_context, surviving_tags = (
            self._format_context_for_prompt(context)
        )
        messages = [{"role": "system", "content": RAG_SYSTEM_PROMPT}]
        messages.append(
            {
                "role": "system",
                "content": f"Relevant context from your knowledge base:\n\n{formatted_context}",
            }
        )
        messages.extend(
            {
                "role": m["role"],
                "content": (
                    self._strip_citations(m["content"])
                    if m["role"] == "assistant"
                    else m["content"]
                ),
            }
            for m in history
        )
        return messages, surviving_tags

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

    _CITATION_BRACKET_RE = re.compile(
        r"\[(?:"
        r"[^\[\]]{0,120}\s@\s\d{1,2}:\d{2}(?::\d{2})?"
        r"|[^\[\]]{0,120}\sp\.\d+"
        r"|Source:\s[^\[\]]{0,120}"
        r")\]"
    )
    _SOURCE_PREFIX_RE = re.compile(
        r"(?<!\[)(?P<prefix>\bSource:\s*)(?P<body>[^\n\[\]]{1,120})(?!\])",
        re.IGNORECASE,
    )
    _BARE_CITATION_RE = re.compile(
        r"(?<!\[)(?P<body>"
        r"(?:[A-Za-z0-9][^\n\[\]]{0,100}\s@\s\d{1,2}:\d{2}(?::\d{2})?)"
        r"|(?:[A-Za-z0-9][^\n\[\]]{0,100}\sp\.\d+)"
        r")(?!\])"
    )

    def _strip_citations(self, text: str) -> str:
        return self._CITATION_BRACKET_RE.sub(
            lambda m: m.group(0)[1:-1], text,
        )

    @staticmethod
    def _canonical_source_tag(source: dict) -> str:
        title = (source.get("title") or "").strip()
        timestamp = (source.get("timestamp") or "").strip()
        page_number = source.get("page_number")
        if title and timestamp:
            return f"{title} @ {timestamp}"
        if title and page_number:
            return f"{title} p.{page_number}"
        if title:
            return title
        if timestamp:
            return timestamp
        return "Source"

    @staticmethod
    def _canonical_bracketed_source_tag(source: dict) -> str:
        return f"[{ChatManager._canonical_source_tag(source)}]"

    @staticmethod
    def _normalize_match_key(value: str) -> str:
        cleaned = value.strip()
        if cleaned.startswith("[") and cleaned.endswith("]"):
            cleaned = cleaned[1:-1].strip()
        cleaned = re.sub(r"^Source:\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned.casefold()

    @classmethod
    def _match_structured_source(
        cls,
        citation_text: str,
        sources: list[dict],
    ) -> dict | None:
        cleaned = citation_text.strip()
        if not cleaned:
            return None

        normalized = cls._normalize_match_key(cleaned)
        if not normalized:
            return None

        exact_match: dict | None = None
        title_only_matches: list[dict] = []
        timestamp_only_matches: list[dict] = []

        timestamp_match = re.fullmatch(
            r"(?P<title>.+?)\s@\s(?P<timestamp>\d{1,2}:\d{2}(?::\d{2})?)",
            cleaned,
        )
        page_match = re.fullmatch(
            r"(?P<title>.+?)\sp\.(?P<page_number>\d+)",
            cleaned,
        )

        normalized_title = cls._normalize_match_key(cleaned)
        normalized_timestamp = ""
        normalized_page_number: int | None = None
        if timestamp_match is not None:
            normalized_title = cls._normalize_match_key(timestamp_match.group("title"))
            normalized_timestamp = timestamp_match.group("timestamp")
        elif page_match is not None:
            normalized_title = cls._normalize_match_key(page_match.group("title"))
            normalized_page_number = int(page_match.group("page_number"))

        for source in sources:
            canonical = cls._canonical_source_tag(source)
            if cls._normalize_match_key(canonical) == normalized:
                exact_match = source
                break

            source_title = cls._normalize_match_key(source.get("title", ""))
            source_timestamp = (source.get("timestamp") or "").strip()
            source_page_number = source.get("page_number")

            if normalized_title and source_title == normalized_title:
                if normalized_timestamp and source_timestamp == normalized_timestamp:
                    exact_match = source
                    break
                if normalized_page_number and source_page_number == normalized_page_number:
                    exact_match = source
                    break
                title_only_matches.append(source)

            if not normalized_title and normalized == cls._normalize_match_key(source_timestamp):
                timestamp_only_matches.append(source)

        if exact_match is not None:
            return exact_match
        if len(title_only_matches) == 1:
            return title_only_matches[0]
        if len(timestamp_only_matches) == 1:
            return timestamp_only_matches[0]
        return None

    @classmethod
    def _normalize_citations(
        cls,
        text: str,
        sources: list[dict],
    ) -> str:
        if not text or not sources:
            return text.strip()

        normalized = text
        unique_title_counts: dict[str, int] = {}
        for source in sources:
            source_title = cls._normalize_match_key(source.get("title", ""))
            if source_title:
                unique_title_counts[source_title] = (
                    unique_title_counts.get(source_title, 0) + 1
                )

        sorted_sources = sorted(
            sources,
            key=lambda source: len((source.get("title") or "").strip()),
            reverse=True,
        )

        for source in sorted_sources:
            title = (source.get("title") or "").strip()
            if not title:
                continue

            canonical = cls._canonical_bracketed_source_tag(source)
            title_pattern = re.escape(title)
            timestamp = (source.get("timestamp") or "").strip()
            page_number = source.get("page_number")

            locator_pattern = ""
            if timestamp:
                locator_pattern = rf"(?:\s@\s{re.escape(timestamp)})?"
            elif page_number:
                locator_pattern = rf"(?:\sp\.{page_number})?"

            normalized = re.sub(
                rf"\[\s*Source:\s*{title_pattern}{locator_pattern}\s*\]",
                canonical,
                normalized,
                flags=re.IGNORECASE,
            )
            normalized = re.sub(
                rf"(?<!\[)\bSource:\s*{title_pattern}{locator_pattern}\b",
                canonical,
                normalized,
                flags=re.IGNORECASE,
            )

            if timestamp:
                normalized = re.sub(
                    rf"\[\s*{title_pattern}\s@\s{re.escape(timestamp)}\s*\]",
                    canonical,
                    normalized,
                    flags=re.IGNORECASE,
                )
                normalized = re.sub(
                    rf"(?<!\[)\b{title_pattern}\s@\s{re.escape(timestamp)}\b(?!\])",
                    canonical,
                    normalized,
                    flags=re.IGNORECASE,
                )
            elif page_number:
                normalized = re.sub(
                    rf"\[\s*{title_pattern}\sp\.{page_number}\s*\]",
                    canonical,
                    normalized,
                    flags=re.IGNORECASE,
                )
                normalized = re.sub(
                    rf"(?<!\[)\b{title_pattern}\sp\.{page_number}\b(?!\])",
                    canonical,
                    normalized,
                    flags=re.IGNORECASE,
                )

            if unique_title_counts.get(cls._normalize_match_key(title)) == 1:
                normalized = re.sub(
                    rf"\[\s*{title_pattern}\s*\]",
                    canonical,
                    normalized,
                    flags=re.IGNORECASE,
                )

        return normalized.strip()

    @staticmethod
    def _match_source_to_tag(source: dict) -> str:
        return ChatManager._canonical_bracketed_source_tag(source)

    def _select_recent_history_for_rewrite(
        self,
        history: list[dict[str, str]],
    ) -> list[dict[str, str]]:
        selected: list[dict[str, str]] = []
        role_counts = {"user": 0, "assistant": 0}

        for message in reversed(history):
            role = message.get("role")
            content = (message.get("content") or "").strip()
            if role not in role_counts or not content:
                continue
            if role_counts[role] >= self.MAX_REWRITE_TURNS_PER_ROLE:
                continue
            selected.append({"role": role, "content": content})
            role_counts[role] += 1
            if all(
                count >= self.MAX_REWRITE_TURNS_PER_ROLE
                for count in role_counts.values()
            ):
                break

        selected.reverse()
        return selected

    def _build_rewrite_messages(
        self,
        user_input: str,
        history: list[dict[str, str]],
    ) -> list[dict[str, str]]:
        conversation_lines: list[str] = []
        for message in history:
            role = message["role"].capitalize()
            conversation_lines.append(f"{role}: {message['content']}")

        conversation_block = "\n".join(conversation_lines) or "No prior conversation."
        rewrite_request = (
            "Recent conversation:\n"
            f"{conversation_block}\n\n"
            f"Latest user message:\nUser: {user_input}\n\n"
            "Standalone search query:"
        )
        return [
            {"role": "system", "content": RETRIEVAL_REWRITE_SYSTEM_PROMPT},
            {"role": "user", "content": rewrite_request},
        ]

    def rewrite_retrieval_query(
        self,
        user_input: str,
        history: list[dict[str, str]] | None = None,
    ) -> str:
        cleaned_input = user_input.strip()
        if not cleaned_input:
            return ""

        recent_history = self._select_recent_history_for_rewrite(history or [])
        if not recent_history:
            return cleaned_input

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=self._build_rewrite_messages(cleaned_input, recent_history),
            )
        except Exception:
            logger.exception("Retrieval query rewrite failed; falling back to original input.")
            return cleaned_input

        rewritten = (
            getattr(response.choices[0].message, "content", "") or ""
        ).strip()
        if not rewritten:
            return cleaned_input

        return rewritten[: self.MAX_REWRITE_CHARS].strip() or cleaned_input

    def build_completion_request(
        self,
        user_input: str,
        history: list[dict[str, str]] | None = None,
    ) -> ChatCompletionRequest:
        rewritten_query = self.rewrite_retrieval_query(user_input, history)
        normalization = self.retriever.normalize_query(rewritten_query)
        retrieval_query = normalization.query or rewritten_query
        context, sources, use_rag = self.retriever.query(self.user_id, retrieval_query)
        logger.debug(
            "RAG retrieval prepared",
            extra={
                "user_id": self.user_id,
                "original_query": user_input,
                "rewritten_query": rewritten_query,
                "retrieval_query": retrieval_query,
                "rewrite_used": rewritten_query != user_input.strip(),
                "normalization_used": normalization.applied,
                "source_count": len(sources),
                "has_context": use_rag,
            },
        )
        if not use_rag:
            return ChatCompletionRequest(
                messages=[],
                sources=[],
                has_context=False,
            )

        messages, surviving_tags = self._build_messages(
            context or "", history or [],
        )
        messages.append({"role": "user", "content": user_input})
        filtered_sources = [
            s for s in sources
            if self._match_source_to_tag(s) in surviving_tags
        ]
        return ChatCompletionRequest(
            messages=messages,
            sources=filtered_sources,
            has_context=True,
        )

    def finalize_answer(self, raw_answer: str, sources: list[dict] | None = None) -> str:
        cleaned_answer = self._strip_markdown(
            self._strip_model_sources_section(raw_answer)
        )
        return self._normalize_citations(cleaned_answer, sources or [])

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
        answer = self.finalize_answer(raw_answer, request.sources)
        usage = getattr(response, "usage", None)
        usage_payload = None
        if usage is not None:
            usage_payload = {
                "prompt_tokens": int(getattr(usage, "prompt_tokens", 0) or 0),
                "completion_tokens": int(getattr(usage, "completion_tokens", 0) or 0),
                "total_tokens": int(getattr(usage, "total_tokens", 0) or 0),
            }
        return answer, request.sources, True, usage_payload
