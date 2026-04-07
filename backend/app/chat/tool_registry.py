"""OpenAI function-calling tool definitions for the agent loop."""

from __future__ import annotations

TOOL_DEFINITIONS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "get_current_thread_messages",
            "description": (
                "Get the messages from the current chat thread. "
                "Use this when you need to read the conversation history, "
                "for example to export or summarize it."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of messages to return (default 200).",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_thread_sources",
            "description": (
                "Get the cited sources for the current chat thread. "
                "Use this when exporting a conversation to include source references."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "notion_search",
            "description": "Search for pages in the user's connected Notion workspace by title or keyword.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query text.",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "notion_create_page",
            "description": (
                "Create a new page in Notion under a parent page. "
                "Use this to save or export conversation threads to Notion."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "parent_page_id": {
                        "type": "string",
                        "description": "The ID of the parent Notion page.",
                    },
                    "title": {
                        "type": "string",
                        "description": "Title for the new page.",
                    },
                    "markdown": {
                        "type": "string",
                        "description": "Page content formatted as markdown.",
                    },
                },
                "required": ["parent_page_id", "title", "markdown"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "notion_fetch",
            "description": "Fetch a Notion page by its ID or URL to read its contents or verify it exists.",
            "parameters": {
                "type": "object",
                "properties": {
                    "page_id": {
                        "type": "string",
                        "description": "Page ID or URL.",
                    },
                },
                "required": ["page_id"],
            },
        },
    },
]


def get_tool_definitions() -> list[dict]:
    """Return all tool definitions in OpenAI function-calling format."""
    return TOOL_DEFINITIONS
