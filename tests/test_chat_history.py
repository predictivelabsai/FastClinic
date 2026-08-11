from __future__ import annotations

import os
import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from graph import clinic_assistant
from web import chat_history
from web.i18n import current_lang


class _Message:
    def __init__(self, content):
        self.content = content


class _CapturingAgent:
    def __init__(self):
        self.calls = []
        self.locales = []

    def invoke(self, payload):
        self.calls.append(payload)
        self.locales.append(current_lang())
        return {"messages": [*payload["messages"], _Message(f"reply-{len(self.calls)}")]}


class _StreamingAgent:
    def __init__(self):
        self.locale = None
        self.payload = None

    async def astream_events(self, payload, version):
        self.payload = payload
        self.locale = current_lang()
        chunk = _Message("streamed reply")
        chunk.tool_call_chunks = None
        yield {"event": "on_chat_model_stream", "data": {"chunk": chunk}}


class ChatHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path_patch = patch.object(
            chat_history, "CHAT_DB_PATH", Path(self.temp.name) / "operations.sqlite"
        )
        self.path_patch.start()

    def tearDown(self):
        self.path_patch.stop()
        self.temp.cleanup()

    def test_history_is_persistent_and_isolated_by_owner_and_thread(self):
        chat_history.append_turn("alice@example.com", "thread-a", "hello", "hi", "en")
        chat_history.append_turn("alice@example.com", "thread-b", "other", "answer", "en")
        chat_history.append_turn("bob@example.com", "thread-a", "secret", "private", "en")

        self.assertEqual(
            chat_history.history("alice@example.com", "thread-a"),
            [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "hi"}],
        )
        self.assertNotIn("secret", str(chat_history.history("alice@example.com", "thread-a")))
        self.assertEqual(len(chat_history.history("alice@example.com", "thread-b")), 2)

    def test_history_replay_is_bounded_and_starts_with_a_user(self):
        with patch.dict(os.environ, {
            "FASTCLINIC_CHAT_HISTORY_MESSAGES": "3",
            "FASTCLINIC_CHAT_HISTORY_CHARS": "1000",
        }):
            chat_history.append_turn("alice", "bounded", "one", "first")
            chat_history.append_turn("alice", "bounded", "two", "second")
            replay = chat_history.history("alice", "bounded")
        # The three-message SQL window starts on an assistant message, which is
        # deliberately removed instead of replaying an orphaned model response.
        self.assertEqual(
            replay,
            [{"role": "user", "content": "two"}, {"role": "assistant", "content": "second"}],
        )

    def test_invalid_thread_ids_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "thread id"):
            chat_history.history("alice", "../../another-users-thread")

    def test_agent_replays_prior_turn_and_keeps_locale_active(self):
        agent = _CapturingAgent()
        with patch.object(clinic_assistant, "_get_agent", return_value=agent):
            first = clinic_assistant.answer(
                "Patient 1206", "thread-memory", "de", "alice@example.com"
            )
            second = clinic_assistant.answer(
                "Und die Stadt?", "thread-memory", "de", "alice@example.com"
            )

        self.assertEqual((first, second), ("reply-1", "reply-2"))
        self.assertEqual(agent.locales, ["de", "de"])
        second_messages = agent.calls[1]["messages"]
        self.assertEqual(second_messages[0], {"role": "user", "content": "Patient 1206"})
        self.assertEqual(second_messages[1], {"role": "assistant", "content": "reply-1"})
        self.assertIn("Response language: German (de)", second_messages[2]["content"])

    def test_streaming_agent_persists_turn_with_locale_context(self):
        agent = _StreamingAgent()

        async def collect():
            events = []
            with patch.object(clinic_assistant, "_get_agent", return_value=agent):
                async for event in clinic_assistant.answer_stream(
                    "Näytä tulot", "stream-thread", "fi", "alice@example.com"
                ):
                    events.append(event)
            return events

        events = asyncio.run(collect())
        self.assertEqual(events, [("token", "streamed reply")])
        self.assertEqual(agent.locale, "fi")
        self.assertIn("Response language: Finnish (fi)", agent.payload["messages"][-1]["content"])
        self.assertEqual(
            chat_history.history("alice@example.com", "stream-thread"),
            [
                {"role": "user", "content": "Näytä tulot"},
                {"role": "assistant", "content": "streamed reply"},
            ],
        )


if __name__ == "__main__":
    unittest.main()
