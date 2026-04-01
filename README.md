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
