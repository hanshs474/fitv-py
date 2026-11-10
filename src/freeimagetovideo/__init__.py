"""Official Python SDK for Free Image to Video (https://freeimagetovideo.ai).

Free image to video AI with no daily cap: start with no sign-up, keep going on
a free account. Every video comes with sound and no watermark.

With an API key this package turns a prompt into a clip (text to video), or a
photo into a clip with the photo as the first frame (image to video), on
MiniMax H3::

    from freeimagetovideo import generate_video
    clip = generate_video("a paper lantern drifting over a night river")
    moved = generate_video("the camera slowly orbits the statue",
                           image_url="https://example.com/statue.jpg")

Create a key at https://freeimagetovideo.ai/settings/apikeys and pass it as
``api_key=`` or set ``FREEIMAGETOVIDEO_API_KEY``. API runs draw on your plan's
full-speed allowance, then wait in the relaxed queue
(https://freeimagetovideo.ai/pricing).

Standard library only.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any, Callable, Dict, List, Optional, Tuple

__version__ = "0.1.0"
__all__ = [
    "generate_video",
    "submit",
    "status",
    "wait",
    "credits",
    "body",
    "parse_envelope",
    "classify",
    "FreeImageToVideoError",
    "AuthError",
    "QuotaError",
    "PlanError",
    "BusyError",
    "RejectedError",
    "GenerationFailed",
    "GenerationTimeout",
    "APIError",
    "BASE_URL",
    "KEYS_URL",
    "DEFAULT_MODEL",
    "MODELS",
]

BASE_URL = "https://freeimagetovideo.ai"
KEYS_URL = BASE_URL + "/settings/apikeys"
DEFAULT_MODEL = "minimax-h3"
#: Every model id the API takes.
MODELS = ("minimax-h3",)


class FreeImageToVideoError(RuntimeError):
    """Base class. Catch a subclass to decide what to do next."""

    def __init__(
        self,
        message: str,
        *,
        http_status: Optional[int] = None,
        code: Optional[int] = None,
        reason: Optional[str] = None,
        task_id: Optional[str] = None,
        error_message: Optional[str] = None,
        failure_kind: Optional[str] = None,
    ):
        super().__init__(message)
        self.http_status = http_status
        self.code = code
        self.reason = reason
        self.task_id = task_id
        self.error_message = error_message
        self.failure_kind = failure_kind


class AuthError(FreeImageToVideoError):
    """API key missing or invalid (HTTP 401)."""


class QuotaError(FreeImageToVideoError):
    """Not enough credits for this run (data.reason = insufficient_credits)."""


class PlanError(FreeImageToVideoError):
    """API runs need a paid plan (data.reason = plan_required)."""


class BusyError(FreeImageToVideoError):
    """Too many runs generating at once on this account (data.reason = concurrency)."""


class RejectedError(FreeImageToVideoError):
    """The content filter refused the prompt, or a cooldown is active (code -2 / -3). Reword it."""


class GenerationFailed(FreeImageToVideoError):
    """The run was accepted but ended as failed or canceled; see ``error_message``."""


class GenerationTimeout(FreeImageToVideoError):
    """Still generating when the deadline passed; check the run later with ``status``."""


class APIError(FreeImageToVideoError):
    """Any other refusal or an unexpected answer."""


#: transport(url, payload, headers) -> (http_status, raw_body_bytes)
Transport = Callable[[str, Optional[dict], Dict[str, str]], Tuple[int, bytes]]


def _http(url: str, payload: Optional[dict], headers: Dict[str, str]) -> Tuple[int, bytes]:
    data = json.dumps(payload).encode() if payload is not None else b""
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read() or b""
    except (urllib.error.URLError, OSError) as e:
        raise APIError(f"could not reach freeimagetovideo.ai: {e}") from e


def classify(http_status: int, env: dict) -> FreeImageToVideoError:
    """Map an HTTP status and envelope to the error that says what to do next."""
    msg = str(env.get("message") or f"request failed (HTTP {http_status})")
    code = env.get("code") if isinstance(env.get("code"), int) else 0
    data = env.get("data") if isinstance(env.get("data"), dict) else {}
    reason = data.get("reason") if isinstance(data.get("reason"), str) else ""
    if http_status == 401:
        cls = AuthError
    elif code in (-2, -3):
        cls = RejectedError
    elif reason == "insufficient_credits":
        cls = QuotaError
    elif reason == "plan_required":
        cls = PlanError
    elif reason == "concurrency":
        cls = BusyError
    elif "no auth" in msg.lower():
        cls = AuthError
    else:
        cls = APIError
    return cls(msg, http_status=http_status, code=code, reason=reason or None)


def parse_envelope(http_status: int, raw: bytes) -> dict:
    """Return the envelope on code 0, else raise the matching error.

    freeimagetovideo.ai answers almost every refusal as HTTP 200 with a
    non-zero code and a data.reason, so the status code alone reads a refusal
    as success.
    """
    env: Any = {}
    if raw and raw.strip():
        try:
            env = json.loads(raw)
        except ValueError:
            if http_status == 401:
                raise classify(401, {})
            raise APIError(
                f"freeimagetovideo.ai returned a non-JSON response (HTTP {http_status})",
                http_status=http_status,
            )
    if not isinstance(env, dict):
        env = {}
    if http_status < 400 and env.get("code") == 0:
        return env
    raise classify(http_status, env)


def body(prompt: str, image_url: Optional[str] = None, model: str = DEFAULT_MODEL, **options: Any) -> dict:
    """The request body for ``POST /api/ai/generate``.

    ``options`` are sent as they are: ``duration`` (4/5/6/8/10/15),
    ``resolution`` (480p/768p), ``aspect_ratio`` (16:9/9:16/1:1).
    """
    opts: Dict[str, Any] = {k: v for k, v in options.items() if v is not None}
    opts["sound"] = True
    scene = "text-to-video"
    if image_url:
        opts["image_input"] = [image_url]
        scene = "image-to-video"
    # The server routes by model; provider only has to be non-empty.
    return {
        "provider": "auto",
        "mediaType": "video",
        "model": model or DEFAULT_MODEL,
        "scene": scene,
        "prompt": prompt,
        "options": opts,
    }


def _key(api_key: Optional[str]) -> str:
    key = (api_key or os.environ.get("FREEIMAGETOVIDEO_API_KEY") or "").strip()
    if not key:
        raise AuthError(f"set FREEIMAGETOVIDEO_API_KEY or pass api_key= (create a key at {KEYS_URL})")
    return key


def _base(base_url: Optional[str]) -> str:
    return (base_url or os.environ.get("FREEIMAGETOVIDEO_BASE_URL") or BASE_URL).strip().rstrip("/")


def _post(path: str, payload: Optional[dict], api_key: Optional[str], base_url: Optional[str], transport: Optional[Transport]) -> dict:
    headers = {
        "Authorization": f"Bearer {_key(api_key)}",
        "Content-Type": "application/json",
        "User-Agent": f"fitv-python/{__version__}",
    }
    st, raw = (transport or _http)(_base(base_url) + path, payload, headers)
    return parse_envelope(st, raw)


def submit(
    prompt: str,
    image_url: Optional[str] = None,
    *,
    model: str = DEFAULT_MODEL,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    transport: Optional[Transport] = None,
    **options: Any,
) -> str:
    """Start one run and return its task id without waiting."""
    if not str(prompt or "").strip():
        raise APIError("prompt is required")
    env = _post("/api/ai/generate", body(prompt, image_url, model, **options), api_key, base_url, transport)
    data = env.get("data") if isinstance(env.get("data"), dict) else {}
    tid = data.get("id")
    if tid in (None, ""):
        raise APIError("freeimagetovideo.ai accepted the run but returned no id")
    return str(tid)


def status(
    task_id: str,
    *,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    transport: Optional[Transport] = None,
) -> Dict[str, Any]:
    """Look up a run. ``status`` is pending, processing, success, failed or
    canceled; ``videos`` holds the result URLs; ``queued`` / ``queueEta``
    (seconds) describe the relaxed queue."""
    env = _post("/api/ai/query", {"taskId": task_id}, api_key, base_url, transport)
    data = env.get("data")
    if not isinstance(data, dict):
        raise APIError("unexpected status answer")
    return data


def wait(
    task_id: str,
    *,
    api_key: Optional[str] = None,
    timeout: float = 1800.0,
    poll_every: float = 10.0,
    base_url: Optional[str] = None,
    transport: Optional[Transport] = None,
) -> str:
    """Poll a submitted run until it finishes and return its video URL."""
    deadline = time.monotonic() + timeout
    while True:
        t = status(task_id, api_key=api_key, base_url=base_url, transport=transport)
        state = str(t.get("status") or "")
        if state == "success":
            videos: List[str] = t.get("videos") or []
            if not videos:
                raise GenerationFailed("generation failed: finished with no video", task_id=task_id, error_message="finished with no video")
            return str(videos[0])
        if state in ("failed", "canceled"):
            em = t.get("errorMessage") or state
            raise GenerationFailed(
                f"generation failed: run {task_id}: {em}",
                task_id=task_id,
                error_message=t.get("errorMessage"),
                failure_kind=t.get("failureKind"),
            )
        if time.monotonic() + poll_every > deadline:
            raise GenerationTimeout(f"run {task_id} is still generating; check it later with status()", task_id=task_id)
        time.sleep(poll_every)


def generate_video(
    prompt: str,
    image_url: Optional[str] = None,
    *,
    model: str = DEFAULT_MODEL,
    api_key: Optional[str] = None,
    timeout: float = 1800.0,
    poll_every: float = 10.0,
    base_url: Optional[str] = None,
    transport: Optional[Transport] = None,
    **options: Any,
) -> str:
    """Generate one clip with sound and return its URL.

    Pass ``image_url=`` (a public https image) for image to video: the photo
    becomes the first frame. Extra keyword arguments are video options.
    """
    tid = submit(prompt, image_url, model=model, api_key=api_key, base_url=base_url, transport=transport, **options)
    return wait(tid, api_key=api_key, timeout=timeout, poll_every=poll_every, base_url=base_url, transport=transport)


def credits(
    *,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    transport: Optional[Transport] = None,
) -> int:
    """Return the credits left on the account."""
    env = _post("/api/user/get-user-credits", None, api_key, base_url, transport)
    data = env.get("data") if isinstance(env.get("data"), dict) else {}
    return int(data.get("remainingCredits") or 0)
