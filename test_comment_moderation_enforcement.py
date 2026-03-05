import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(SCRIPT_DIR, 'src')
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from agent_user import AgentUser


class CommentModerationEnforcementTest(unittest.TestCase):
    class _ImmediateFuture:
        def __init__(self, value):
            self._value = value

        def result(self):
            return self._value

    class _ImmediateExecutor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def submit(self, fn, *args, **kwargs):
            return CommentModerationEnforcementTest._ImmediateFuture(fn(*args, **kwargs))

    def _make_user(self, user_id="u1"):
        user = object.__new__(AgentUser)
        user.user_id = user_id
        user.selected_model = "test-model"
        user.is_news_agent = False
        user.last_comment_moderation_message = None
        user._validate_comment_diversity = AsyncMock(return_value="cleaned comment")
        user._update_memory_after_action = AsyncMock(return_value=None)
        return user

    def _safe_create_task(self, coro):
        # Avoid un-awaited coroutine warnings in unit tests.
        try:
            coro.close()
        except Exception:
            pass
        return None

    def test_clean_comment_should_publish_and_return_comment_id(self):
        user = self._make_user()

        # user_state -> post lookup
        fetch_one_side_effect = [
            {"status": "active", "comment_violation_count": 0},
            {"author_id": "post-author", "content": "post content"},
        ]

        with patch("agent_user.fetch_one", side_effect=fetch_one_side_effect), \
             patch("agent_user.execute_query", return_value=True) as mock_exec, \
             patch("agent_user.Utils.generate_formatted_id", return_value="comment-001"), \
             patch("agent_user.fetch_all", return_value=[]), \
             patch("moderation.providers.keyword_provider.KeywordProvider.check", return_value=None), \
             patch("concurrent.futures.ThreadPoolExecutor", return_value=self._ImmediateExecutor()), \
             patch("asyncio.create_task", side_effect=self._safe_create_task):
            result = user.create_comment("post-1", "hello")

        self.assertEqual("comment-001", result)
        self.assertIsNone(user.last_comment_moderation_message)

        sql_text = "\n".join(call.args[0] for call in mock_exec.call_args_list if call.args)
        self.assertIn("INSERT INTO comments", sql_text)
        self.assertNotIn("moderation_warning", sql_text)

    def test_flagged_comment_should_be_revoked_and_warned(self):
        user = self._make_user()

        # user_state -> post lookup -> updated_user(after violation increment)
        fetch_one_side_effect = [
            {"status": "active", "comment_violation_count": 0},
            {"author_id": "post-author", "content": "post content"},
            {"comment_violation_count": 1},
        ]
        verdict = SimpleNamespace(detected_keywords=["kill yourself"])

        with patch("agent_user.fetch_one", side_effect=fetch_one_side_effect), \
             patch("agent_user.execute_query", return_value=True) as mock_exec, \
             patch("agent_user.Utils.generate_formatted_id", return_value="comment-002"), \
             patch("agent_user.fetch_all", return_value=[]), \
             patch("moderation.providers.keyword_provider.KeywordProvider.check", return_value=verdict), \
             patch("concurrent.futures.ThreadPoolExecutor", return_value=self._ImmediateExecutor()), \
             patch("asyncio.create_task", side_effect=self._safe_create_task):
            result = user.create_comment("post-1", "bad words")

        self.assertIsNone(result)
        self.assertIn("1/3", user.last_comment_moderation_message)

        sql_text = "\n".join(call.args[0] for call in mock_exec.call_args_list if call.args)
        self.assertIn("DELETE FROM comments", sql_text)
        self.assertIn("comment_violation_count", sql_text)
        warning_rows = [
            call for call in mock_exec.call_args_list
            if len(call.args) > 1 and isinstance(call.args[1], tuple)
            and len(call.args[1]) > 1 and call.args[1][1] == "moderation_warning"
        ]
        self.assertTrue(warning_rows, "Expected moderation_warning action to be written")

    def test_third_violation_should_ban_user(self):
        user = self._make_user()

        fetch_one_side_effect = [
            {"status": "active", "comment_violation_count": 2},
            {"author_id": "post-author", "content": "post content"},
            {"comment_violation_count": 3},
        ]
        verdict = SimpleNamespace(detected_keywords=["nazi"])

        with patch("agent_user.fetch_one", side_effect=fetch_one_side_effect), \
             patch("agent_user.execute_query", return_value=True) as mock_exec, \
             patch("agent_user.Utils.generate_formatted_id", return_value="comment-003"), \
             patch("agent_user.fetch_all", return_value=[]), \
             patch("moderation.providers.keyword_provider.KeywordProvider.check", return_value=verdict), \
             patch("concurrent.futures.ThreadPoolExecutor", return_value=self._ImmediateExecutor()), \
             patch("asyncio.create_task", side_effect=self._safe_create_task):
            result = user.create_comment("post-1", "bad words again")

        self.assertIsNone(result)
        self.assertIn("已封禁", user.last_comment_moderation_message)

        sql_text = "\n".join(call.args[0] for call in mock_exec.call_args_list if call.args)
        self.assertIn("SET status = 'banned'", sql_text)

    def test_banned_user_should_be_blocked_before_insert(self):
        user = self._make_user()

        with patch("agent_user.fetch_one", return_value={"status": "banned", "comment_violation_count": 5}), \
             patch("agent_user.execute_query", return_value=True) as mock_exec:
            result = user.create_comment("post-1", "whatever")

        self.assertIsNone(result)
        self.assertIn("账号已封禁", user.last_comment_moderation_message)
        self.assertEqual(0, mock_exec.call_count)


if __name__ == "__main__":
    unittest.main()
