import logging
from dataclasses import dataclass

from dotenv import load_dotenv

from app.chat.constants import NO_CONTEXT_MESSAGE
from app.chat.context_formatter import build_prompt_messages, format_context_for_prompt
from app.chat.citation_normalizer import (
    canonical_bracketed_source_tag,
    canonical_source_tag,
    finalize_answer as finalize_answer_text,
    match_structured_source,
    normalize_citations,
    normalize_match_key,
    strip_citations,
    strip_markdown,
    strip_model_sources_section,
)
from app.chat.openai_client import build_openai_client, usage_to_dict
from app.chat.query_rewriter import (
    build_rewrite_messages,
    rewrite_retrieval_query as execute_retrieval_query_rewrite,
    select_recent_history_for_rewrite,
)
from app.rag.retriever import RAGRetriever

load_dotenv()

logger = logging.getLogger(__name__)


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
        self.client = build_openai_client()
        self.model = model
        self.user_id = user_id
        self.retriever = RAGRetriever()

    def _format_context_for_prompt(
        self,
        context: str,
    ) -> tuple[str, set[str]]:
        return format_context_for_prompt(
            context,
            max_blocks=self.MAX_CONTEXT_BLOCKS,
            max_chars_per_block=self.MAX_CONTEXT_CHARS_PER_BLOCK,
            max_total_chars=self.MAX_CONTEXT_TOTAL_CHARS,
        )

    def _build_messages(
        self,
        context: str,
        history: list[dict[str, str]],
    ) -> tuple[list[dict[str, str]], set[str]]:
        formatted_context, surviving_tags = self._format_context_for_prompt(context)
        return (
            build_prompt_messages(
                formatted_context=formatted_context,
                history=history,
                assistant_content_formatter=self._strip_citations,
            ),
            surviving_tags,
        )

    def _strip_markdown(self, text: str) -> str:
        return strip_markdown(text)

    def _strip_model_sources_section(self, answer: str) -> str:
        return strip_model_sources_section(answer)

    def _strip_citations(self, text: str) -> str:
        return strip_citations(text)

    @staticmethod
    def _canonical_source_tag(source: dict) -> str:
        return canonical_source_tag(source)

    @staticmethod
    def _canonical_bracketed_source_tag(source: dict) -> str:
        return canonical_bracketed_source_tag(source)

    @staticmethod
    def _normalize_match_key(value: str) -> str:
        return normalize_match_key(value)

    @classmethod
    def _match_structured_source(
        cls,
        citation_text: str,
        sources: list[dict],
    ) -> dict | None:
        return match_structured_source(citation_text, sources)

    @classmethod
    def _normalize_citations(
        cls,
        text: str,
        sources: list[dict],
    ) -> str:
        return normalize_citations(text, sources)

    @staticmethod
    def _match_source_to_tag(source: dict) -> str:
        return canonical_bracketed_source_tag(source)

    def _select_recent_history_for_rewrite(
        self,
        history: list[dict[str, str]],
    ) -> list[dict[str, str]]:
        return select_recent_history_for_rewrite(
            history,
            max_turns_per_role=self.MAX_REWRITE_TURNS_PER_ROLE,
        )

    def _build_rewrite_messages(
        self,
        user_input: str,
        history: list[dict[str, str]],
    ) -> list[dict[str, str]]:
        return build_rewrite_messages(user_input, history)

    def rewrite_retrieval_query(
        self,
        user_input: str,
        history: list[dict[str, str]] | None = None,
    ) -> str:
        return execute_retrieval_query_rewrite(
            client=self.client,
            model=self.model,
            user_input=user_input,
            history=history,
            max_turns_per_role=self.MAX_REWRITE_TURNS_PER_ROLE,
            max_rewrite_chars=self.MAX_REWRITE_CHARS,
        )

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
            return ChatCompletionRequest(messages=[], sources=[], has_context=False)

        messages, surviving_tags = self._build_messages(context or "", history or [])
        messages.append({"role": "user", "content": user_input})
        filtered_sources = [
            source for source in sources
            if self._match_source_to_tag(source) in surviving_tags
        ]
        return ChatCompletionRequest(
            messages=messages,
            sources=filtered_sources,
            has_context=True,
        )

    def build_base_messages(
        self,
        user_input: str,
        history: list[dict[str, str]] | None = None,
    ) -> list[dict[str, str]]:
        """Build messages with just the system prompt and history (no RAG context).

        Used by the agent loop when RAG has no context but tools are available.
        """
        from app.chat.prompts import RAG_SYSTEM_PROMPT

        messages: list[dict[str, str]] = [{"role": "system", "content": RAG_SYSTEM_PROMPT}]
        for msg in (history or []):
            messages.append({
                "role": msg["role"],
                "content": (
                    self._strip_citations(msg["content"])
                    if msg["role"] == "assistant"
                    else msg["content"]
                ),
            })
        messages.append({"role": "user", "content": user_input})
        return messages

    def finalize_answer(self, raw_answer: str, sources: list[dict] | None = None) -> str:
        return finalize_answer_text(raw_answer, sources or [])

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
        raw_answer = (response.choices[0].message.content or "").strip()
        cleaned_answer = self.finalize_answer(raw_answer, request.sources)
        usage = usage_to_dict(getattr(response, "usage", None))
        return cleaned_answer, request.sources, True, usage
