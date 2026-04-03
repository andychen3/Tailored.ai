# Tailored.ai

## Project Layout

```text
backend/
  app/
    main.py
    core/
      config.py
    api/
      health.py
      ingest.py
      chat.py
    schemas/
      health.py
      ingest.py
      chat.py
    services/
      session_store.py
    chat/
      chat_manager.py
      message.py
    rag/
      retriever.py
      ingestion/
        chunker.py
        youtube_ingester.py
    pinecone_client.py
  tests/
    test_health.py
    test_ingest.py
    test_chat.py
  pyproject.toml
  poetry.lock
  .env.example
frontend/
```

## Run Backend

```bash
cd backend
cp .env.example .env
poetry install
poetry run uvicorn app.main:app --reload
```

Open docs at `http://127.0.0.1:8000/docs`.
If `poetry install` fails on `tiktoken` with Python 3.14, switch Poetry to Python 3.12 first.

## Run MCP Server

The repo now includes a read-only Tailored.ai MCP server for exposing chat threads to external MCP-capable clients.

```bash
cd backend
poetry install
poetry run python -m mcp_server.server
```

Use this server alongside Notion hosted MCP in your external AI client. For manual testing, save curated thread summaries under your existing Notion page `Conversation Notes`.

Available Tailored.ai MCP tools:

- `list_threads(user_id, limit=50)`
- `get_thread(session_id)`
- `get_thread_messages(session_id, limit=50)`
- `get_thread_sources(session_id)`

Example MCP tool outputs:

```json
{
  "threads": [
    {
      "session_id": "abc123",
      "user_id": "default_user",
      "title": "Portfolio tax loss harvesting",
      "model": "gpt-4o-mini",
      "created_at": "2026-04-02T15:10:00+00:00",
      "updated_at": "2026-04-02T15:12:00+00:00",
      "last_message_at": "2026-04-02T15:12:00+00:00",
      "message_count": 4,
      "prompt_tokens_total": 120,
      "completion_tokens_total": 210,
      "total_tokens_total": 330
    }
  ]
}
```

```json
{
  "session_id": "abc123",
  "messages": [
    {
      "id": "msg_1",
      "session_id": "abc123",
      "role": "assistant",
      "content": "Here are the key points...",
      "created_at": "2026-04-02T15:12:00+00:00",
      "usage": {
        "prompt_tokens": 11,
        "completion_tokens": 7,
        "total_tokens": 18
      }
    }
  ]
}
```

## Curl Examples

```bash
curl -s http://127.0.0.1:8000/health
```

```bash
curl -s -X POST http://127.0.0.1:8000/chat/sessions \
  -H "Content-Type: application/json" \
  -d '{"user_id":"default_user","model":"gpt-4o-mini"}'
```

```bash
curl -s -X POST http://127.0.0.1:8000/ingest/youtube \
  -H "Content-Type: application/json" \
  -d '{"user_id":"default_user","url":"https://www.youtube.com/watch?v=dQw4w9WgXcQ","video_title":"Example Video"}'
```

```bash
curl -s -X POST http://127.0.0.1:8000/chat/message \
  -H "Content-Type: application/json" \
  -d '{"session_id":"<session_id_from_chat_sessions>","message":"What does this video say about the main topic?"}'
```

## Run Tests

```bash
cd backend
poetry run pytest -q
```
curl -s -X POST http://127.0.0.1:8000/chat/message \
  -H "Content-Type: application/json" \
  -d '{"session_id":"ef472c4f303943a69ee1e6cbecb407d8","message":"What are the key points?"}'
