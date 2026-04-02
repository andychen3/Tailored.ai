import re


_CITATION_BRACKET_RE = re.compile(
    r"\[(?:"
    r"[^\[\]]{0,120}\s@\s\d{1,2}:\d{2}(?::\d{2})?"
    r"|[^\[\]]{0,120}\sp\.\d+"
    r"|Source:\s[^\[\]]{0,120}"
    r")\]"
)


def strip_markdown(text: str) -> str:
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    return text


def strip_model_sources_section(answer: str) -> str:
    lines = answer.splitlines()
    for index, line in enumerate(lines):
        if line.strip().lower().startswith("sources:"):
            return "\n".join(lines[:index]).rstrip()
    return answer.strip()


def strip_citations(text: str) -> str:
    return _CITATION_BRACKET_RE.sub(lambda match: match.group(0)[1:-1], text)


def canonical_source_tag(source: dict) -> str:
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


def canonical_bracketed_source_tag(source: dict) -> str:
    return f"[{canonical_source_tag(source)}]"


def normalize_match_key(value: str) -> str:
    cleaned = value.strip()
    if cleaned.startswith("[") and cleaned.endswith("]"):
        cleaned = cleaned[1:-1].strip()
    cleaned = re.sub(r"^Source:\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.casefold()


def match_structured_source(citation_text: str, sources: list[dict]) -> dict | None:
    cleaned = citation_text.strip()
    if not cleaned:
        return None

    normalized = normalize_match_key(cleaned)
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

    normalized_title = normalize_match_key(cleaned)
    normalized_timestamp = ""
    normalized_page_number: int | None = None
    if timestamp_match is not None:
        normalized_title = normalize_match_key(timestamp_match.group("title"))
        normalized_timestamp = timestamp_match.group("timestamp")
    elif page_match is not None:
        normalized_title = normalize_match_key(page_match.group("title"))
        normalized_page_number = int(page_match.group("page_number"))

    for source in sources:
        canonical = canonical_source_tag(source)
        if normalize_match_key(canonical) == normalized:
            exact_match = source
            break

        source_title = normalize_match_key(source.get("title", ""))
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

        if not normalized_title and normalized == normalize_match_key(source_timestamp):
            timestamp_only_matches.append(source)

    if exact_match is not None:
        return exact_match
    if len(title_only_matches) == 1:
        return title_only_matches[0]
    if len(timestamp_only_matches) == 1:
        return timestamp_only_matches[0]
    return None


def normalize_citations(text: str, sources: list[dict]) -> str:
    if not text or not sources:
        return text.strip()

    normalized = text
    unique_title_counts: dict[str, int] = {}
    for source in sources:
        source_title = normalize_match_key(source.get("title", ""))
        if source_title:
            unique_title_counts[source_title] = unique_title_counts.get(source_title, 0) + 1

    sorted_sources = sorted(
        sources,
        key=lambda source: len((source.get("title") or "").strip()),
        reverse=True,
    )

    for source in sorted_sources:
        title = (source.get("title") or "").strip()
        if not title:
            continue

        canonical = canonical_bracketed_source_tag(source)
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

        if unique_title_counts.get(normalize_match_key(title)) == 1:
            normalized = re.sub(
                rf"\[\s*{title_pattern}\s*\]",
                canonical,
                normalized,
                flags=re.IGNORECASE,
            )

    return normalized.strip()


def finalize_answer(raw_answer: str, sources: list[dict] | None = None) -> str:
    cleaned_answer = strip_markdown(strip_model_sources_section(raw_answer))
    return normalize_citations(cleaned_answer, sources or [])
