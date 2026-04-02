from app.chat.prompts import RAG_SYSTEM_PROMPT


def format_context_for_prompt(
    context: str,
    *,
    max_blocks: int,
    max_chars_per_block: int,
    max_total_chars: int,
) -> tuple[str, set[str]]:
    if not context:
        return "", set()

    blocks = [block.strip() for block in context.split("\n\n---\n\n") if block.strip()]
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
        if not body or body in seen_bodies:
            continue

        seen_bodies.add(body)
        if len(body) > max_chars_per_block:
            body = f"{body[: max_chars_per_block - 3].rstrip()}..."

        cleaned_block = f"{source_tag}\n{body}"
        if total_chars + len(cleaned_block) > max_total_chars:
            break

        cleaned_blocks.append(cleaned_block)
        surviving_tags.add(source_tag)
        total_chars += len(cleaned_block)

        if len(cleaned_blocks) >= max_blocks:
            break

    return "\n\n---\n\n".join(cleaned_blocks), surviving_tags


def build_prompt_messages(
    *,
    formatted_context: str,
    history: list[dict[str, str]],
    assistant_content_formatter,
) -> list[dict[str, str]]:
    messages = [{"role": "system", "content": RAG_SYSTEM_PROMPT}]
    messages.append(
        {
            "role": "system",
            "content": f"Relevant context from your knowledge base:\n\n{formatted_context}",
        }
    )
    messages.extend(
        {
            "role": message["role"],
            "content": (
                assistant_content_formatter(message["content"])
                if message["role"] == "assistant"
                else message["content"]
            ),
        }
        for message in history
    )
    return messages
