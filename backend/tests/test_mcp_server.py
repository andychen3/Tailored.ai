from app.services.chat_store import ChatStore
from mcp_server.serializers import serialize_thread
from mcp_server.server import (
    get_thread_messages_tool,
    get_thread_sources_tool,
    get_thread_tool,
    list_threads_tool,
)


def _seed_store(tmp_path) -> tuple[ChatStore, str, str]:
    store = ChatStore(str(tmp_path / "chat.sqlite3"))
    first = store.create_session(user_id="user_1", model="gpt-4o-mini", title="First thread")
    second = store.create_session(user_id="user_1", model="gpt-4.1-mini", title="Second thread")

    store.add_message(
        session_id=first.session_id,
        role="user",
        content="first prompt",
    )
    store.add_message(
        session_id=first.session_id,
        role="assistant",
        content="first reply",
        sources=[
            {
                "title": "Video A",
                "timestamp": "0:12",
                "url": "https://example.com/a",
                "video_id": "vid_a",
            }
        ],
        prompt_tokens=11,
        completion_tokens=7,
        total_tokens=18,
    )
    store.add_message(
        session_id=first.session_id,
        role="user",
        content="follow-up prompt",
    )
    store.add_message(
        session_id=second.session_id,
        role="user",
        content="second prompt",
    )
    store.add_message(
        session_id=second.session_id,
        role="assistant",
        content="second reply",
        sources=[
            {
                "title": "Doc B",
                "timestamp": "2:10",
                "url": "https://example.com/b",
                "page_number": 4,
            },
            {
                "title": "Doc C",
                "timestamp": "3:21",
                "url": "https://example.com/c",
            },
        ],
        prompt_tokens=13,
        completion_tokens=9,
        total_tokens=22,
    )
    return store, first.session_id, second.session_id


def test_list_threads_matches_store_ordering_and_totals(tmp_path) -> None:
    store, _, _ = _seed_store(tmp_path)

    payload = list_threads_tool(store, user_id="user_1", limit=50)
    expected_threads = [serialize_thread(thread) for thread in store.list_sessions("user_1")]

    assert payload == {"threads": expected_threads}
    assert payload["threads"][0]["title"] == expected_threads[0]["title"]


def test_get_thread_returns_exact_metadata(tmp_path) -> None:
    store, first_session_id, _ = _seed_store(tmp_path)

    payload = get_thread_tool(store, session_id=first_session_id)

    assert payload["thread"]["session_id"] == first_session_id
    assert payload["thread"]["title"] == "First thread"
    assert payload["thread"]["model"] == "gpt-4o-mini"
    assert payload["thread"]["message_count"] == 3
    assert payload["thread"]["total_tokens_total"] == 18


def test_get_thread_returns_not_found_error(tmp_path) -> None:
    store = ChatStore(str(tmp_path / "chat.sqlite3"))

    payload = get_thread_tool(store, session_id="missing")

    assert payload == {
        "error": {
            "code": "session_not_found",
            "message": "Session 'missing' was not found.",
        }
    }


def test_get_thread_messages_preserves_chronological_order_and_limit(tmp_path) -> None:
    store, first_session_id, _ = _seed_store(tmp_path)

    payload = get_thread_messages_tool(store, session_id=first_session_id, limit=2)

    assert payload["session_id"] == first_session_id
    assert [message["content"] for message in payload["messages"]] == [
        "first reply",
        "follow-up prompt",
    ]
    assert all("created_at" in message for message in payload["messages"])
    assert payload["messages"][0]["usage"] == {
        "prompt_tokens": 11,
        "completion_tokens": 7,
        "total_tokens": 18,
    }
    assert payload["messages"][1]["usage"] is None


def test_get_thread_sources_flattens_sources_from_multiple_messages(tmp_path) -> None:
    store, _, second_session_id = _seed_store(tmp_path)

    payload = get_thread_sources_tool(store, session_id=second_session_id)

    assert payload["session_id"] == second_session_id
    assert payload["sources"] == [
        {
            "message_id": payload["sources"][0]["message_id"],
            "role": "assistant",
            "created_at": payload["sources"][0]["created_at"],
            "title": "Doc B",
            "timestamp": "2:10",
            "url": "https://example.com/b",
            "video_id": None,
            "page_number": 4,
        },
        {
            "message_id": payload["sources"][1]["message_id"],
            "role": "assistant",
            "created_at": payload["sources"][1]["created_at"],
            "title": "Doc C",
            "timestamp": "3:21",
            "url": "https://example.com/c",
            "video_id": None,
            "page_number": None,
        },
    ]


def test_get_thread_sources_returns_empty_list_when_no_sources(tmp_path) -> None:
    store = ChatStore(str(tmp_path / "chat.sqlite3"))
    thread = store.create_session(user_id="user_1", model="gpt-4o-mini", title="No sources")
    store.add_message(session_id=thread.session_id, role="user", content="hello")

    payload = get_thread_sources_tool(store, session_id=thread.session_id)

    assert payload == {
        "session_id": thread.session_id,
        "sources": [],
    }


def test_invalid_inputs_surface_clear_errors(tmp_path) -> None:
    store = ChatStore(str(tmp_path / "chat.sqlite3"))

    assert list_threads_tool(store, user_id=" ", limit=50) == {
        "error": {
            "code": "missing_user_id",
            "message": "Missing user_id.",
        }
    }
    assert get_thread_messages_tool(store, session_id="session", limit=0) == {
        "error": {
            "code": "invalid_limit",
            "message": "limit must be an integer greater than 0.",
        }
    }
    assert get_thread_sources_tool(store, session_id=" ") == {
        "error": {
            "code": "missing_session_id",
            "message": "Missing session_id.",
        }
    }
