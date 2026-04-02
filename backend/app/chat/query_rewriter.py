import logging

from app.chat.prompts import RETRIEVAL_REWRITE_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


def select_recent_history_for_rewrite(
    history: list[dict[str, str]],
    *,
    max_turns_per_role: int,
) -> list[dict[str, str]]:
    selected: list[dict[str, str]] = []
    role_counts = {"user": 0, "assistant": 0}

    for message in reversed(history):
        role = message.get("role")
        content = (message.get("content") or "").strip()
        if role not in role_counts or not content:
            continue
        if role_counts[role] >= max_turns_per_role:
            continue
        selected.append({"role": role, "content": content})
        role_counts[role] += 1
        if all(count >= max_turns_per_role for count in role_counts.values()):
            break

    selected.reverse()
    return selected


def build_rewrite_messages(
    user_input: str,
    history: list[dict[str, str]],
) -> list[dict[str, str]]:
    conversation_lines = [
        f"{message['role'].capitalize()}: {message['content']}"
        for message in history
    ]
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
    *,
    client,
    model: str,
    user_input: str,
    history: list[dict[str, str]] | None,
    max_turns_per_role: int,
    max_rewrite_chars: int,
) -> str:
    cleaned_input = user_input.strip()
    if not cleaned_input:
        return ""

    recent_history = select_recent_history_for_rewrite(
        history or [],
        max_turns_per_role=max_turns_per_role,
    )
    if not recent_history:
        return cleaned_input

    try:
        response = client.chat.completions.create(
            model=model,
            messages=build_rewrite_messages(cleaned_input, recent_history),
        )
    except Exception:
        logger.exception("Retrieval query rewrite failed; falling back to original input.")
        return cleaned_input

    rewritten = (getattr(response.choices[0].message, "content", "") or "").strip()
    if not rewritten:
        return cleaned_input

    return rewritten[:max_rewrite_chars].strip() or cleaned_input
