import io
import json
import os
import unittest
from contextlib import redirect_stderr, redirect_stdout

import freeimagetovideo as fitv
from freeimagetovideo.__main__ import main


def env(code=0, message="ok", data=None):
    return json.dumps({"code": code, "message": message, "data": data}).encode()


def fake(calls, polls, submit_reply=(200, env(data={"id": "t1", "status": "pending"}))):
    polls = list(polls)

    def t(url, payload, headers):
        calls.append((url, payload, headers))
        if url.endswith("/api/ai/generate"):
            return submit_reply
        if url.endswith("/api/ai/query"):
            return 200, env(data=polls.pop(0))
        return 200, env(data={"remainingCredits": 42, "hasPurchasedCredits": False})

    return t


class BodyTests(unittest.TestCase):
    def test_text_to_video(self):
        self.assertEqual(
            fitv.body("a boat", duration=6),
            {"provider": "auto", "mediaType": "video", "model": "minimax-h3", "scene": "text-to-video",
             "prompt": "a boat", "options": {"duration": 6, "sound": True}},
        )

    def test_image_to_video(self):
        b = fitv.body("orbit", "https://example.com/s.jpg", aspect_ratio="9:16")
        self.assertEqual(b["scene"], "image-to-video")
        self.assertEqual(b["options"], {"aspect_ratio": "9:16", "sound": True, "image_input": ["https://example.com/s.jpg"]})


class FlowTests(unittest.TestCase):
    def setUp(self):
        os.environ.pop("FREEIMAGETOVIDEO_API_KEY", None)
        os.environ.pop("FREEIMAGETOVIDEO_BASE_URL", None)

    def test_needs_a_key(self):
        with self.assertRaises(fitv.AuthError) as cm:
            fitv.generate_video("x")
        self.assertIn("settings/apikeys", str(cm.exception))

    def test_empty_prompt(self):
        with self.assertRaises(fitv.APIError):
            fitv.submit("  ", api_key="sk-x")

    def test_polls_until_success(self):
        calls = []
        polls = [
            {"id": "t1", "status": "pending", "queued": True, "queueEta": 120},
            {"id": "t1", "status": "processing"},
            {"id": "t1", "status": "success", "videos": ["https://cdn.example/v.mp4"]},
        ]
        url = fitv.generate_video("a boat", "https://example.com/p.jpg", api_key="sk-abc", resolution="768p",
                                  poll_every=0, base_url="https://t/", transport=fake(calls, polls))
        self.assertEqual(url, "https://cdn.example/v.mp4")
        self.assertEqual(calls[0][0], "https://t/api/ai/generate")
        self.assertEqual(calls[0][1]["scene"], "image-to-video")
        self.assertEqual(calls[0][2]["Authorization"], "Bearer sk-abc")
        self.assertEqual(calls[1][1], {"taskId": "t1"})
        self.assertEqual(len(calls), 4)

    def test_env_key_and_base(self):
        os.environ["FREEIMAGETOVIDEO_API_KEY"] = " sk-env "
        os.environ["FREEIMAGETOVIDEO_BASE_URL"] = "https://staging.example"
        calls = []
        self.assertEqual(fitv.credits(transport=fake(calls, [])), 42)
        self.assertEqual(calls[0][0], "https://staging.example/api/user/get-user-credits")
        self.assertIsNone(calls[0][1])
        self.assertEqual(calls[0][2]["Authorization"], "Bearer sk-env")

    def test_failed_run(self):
        polls = [{"id": "t1", "status": "failed", "errorMessage": "provider error", "failureKind": "provider"}]
        with self.assertRaises(fitv.GenerationFailed) as cm:
            fitv.generate_video("x", api_key="sk", poll_every=0, transport=fake([], polls))
        self.assertEqual(cm.exception.task_id, "t1")
        self.assertEqual(cm.exception.failure_kind, "provider")
        self.assertIn("provider error", str(cm.exception))

    def test_canceled_and_empty_success(self):
        with self.assertRaises(fitv.GenerationFailed):
            fitv.wait("t1", api_key="sk", poll_every=0, transport=fake([], [{"status": "canceled"}]))
        with self.assertRaises(fitv.GenerationFailed):
            fitv.wait("t1", api_key="sk", poll_every=0, transport=fake([], [{"status": "success", "videos": []}]))

    def test_timeout(self):
        with self.assertRaises(fitv.GenerationTimeout) as cm:
            fitv.wait("t1", api_key="sk", timeout=0, poll_every=1, transport=fake([], [{"status": "processing"}]))
        self.assertEqual(cm.exception.task_id, "t1")

    def test_no_id(self):
        with self.assertRaises(fitv.APIError):
            fitv.submit("x", api_key="sk", transport=fake([], [], (200, env(data={}))))


class ErrorTests(unittest.TestCase):
    def test_mapping(self):
        cases = [
            ((401, env(-1, "Invalid API key. Create one at https://freeimagetovideo.ai/settings/apikeys", {"reason": "invalid_api_key"})), fitv.AuthError),
            ((401, b"<html>nope</html>"), fitv.AuthError),
            ((200, env(-2, "blocked by the content filter")), fitv.RejectedError),
            ((200, env(-3, "cooldown active")), fitv.RejectedError),
            ((200, env(-1, "not enough credits", {"reason": "insufficient_credits"})), fitv.QuotaError),
            ((200, env(-1, "API runs need a paid plan", {"reason": "plan_required"})), fitv.PlanError),
            ((200, env(-1, "too many runs", {"reason": "concurrency"})), fitv.BusyError),
            ((200, env(-1, "no auth, please sign in")), fitv.AuthError),
            ((500, b"<html>oops</html>"), fitv.APIError),
            ((200, env(-1, "duration must be one of 4, 5, 6, 8, 10, 15")), fitv.APIError),
        ]
        for reply, exc in cases:
            with self.assertRaises(exc, msg=str(reply)) as cm:
                fitv.submit("x", api_key="sk", transport=fake([], [], reply))
            self.assertIs(type(cm.exception), exc)

    def test_http_200_refusal_is_not_success(self):
        with self.assertRaises(fitv.PlanError) as cm:
            fitv.parse_envelope(200, env(-1, "paid plan", {"reason": "plan_required"}))
        self.assertEqual(cm.exception.reason, "plan_required")
        self.assertEqual(cm.exception.code, -1)


class CLITests(unittest.TestCase):
    def setUp(self):
        os.environ.pop("FREEIMAGETOVIDEO_API_KEY", None)

    def test_usage(self):
        with redirect_stderr(io.StringIO()):
            self.assertEqual(main([]), 2)

    def test_missing_key_exits_1(self):
        err = io.StringIO()
        with redirect_stderr(err):
            self.assertEqual(main(["--credits"]), 1)
        self.assertIn("FREEIMAGETOVIDEO_API_KEY", err.getvalue())

    def test_version(self):
        out = io.StringIO()
        with redirect_stdout(out), self.assertRaises(SystemExit):
            main(["--version"])
        self.assertIn(fitv.__version__, out.getvalue())


@unittest.skipUnless(os.environ.get("FITV_LIVE") == "1", "live smoke: FITV_LIVE=1")
class LiveSmoke(unittest.TestCase):
    """A wrong key against the live API must land on AuthError (no run is started)."""

    def test_wrong_key_is_auth(self):
        with self.assertRaises(fitv.AuthError) as cm:
            fitv.submit("a paper lantern drifting over a night river", api_key="sk-wrong-key-for-test")
        self.assertEqual(cm.exception.http_status, 401)


if __name__ == "__main__":
    unittest.main()
