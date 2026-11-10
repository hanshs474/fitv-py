# Free Image to Video: Python SDK and CLI

Free image to video AI with no daily cap: start with no sign-up, keep going on a free account. Every video comes with sound and no watermark. This is the official Python SDK and command-line tool for [Free Image to Video](https://freeimagetovideo.ai/?utm_source=pypi&utm_medium=package): turn a prompt or a photo into a video clip from your terminal or your Python program.

```bash
pip install freeimagetovideo
```

```python
from freeimagetovideo import generate_video

clip = generate_video("a paper lantern drifting over a night river")

# image to video: the photo becomes the first frame
moved = generate_video("the camera slowly orbits the statue",
                       image_url="https://example.com/statue.jpg",
                       duration=6, aspect_ratio="9:16")
```

Each call submits the run, waits for it and returns the URL of the finished clip. Every clip comes with sound. Standard library only, no dependencies.

On the site the same model runs as [image to video AI with sound](https://freeimagetovideo.ai/video/image-to-video-ai-with-sound), or straight from a prompt as [free text to video AI](https://freeimagetovideo.ai/video/free-text-to-video-ai).

## CLI

```bash
export FREEIMAGETOVIDEO_API_KEY=sk-...
freeimagetovideo "a paper lantern drifting over a night river"
freeimagetovideo --image https://example.com/statue.jpg "the camera slowly orbits the statue"
freeimagetovideo -o duration=10 -o resolution=768p -o aspect_ratio=9:16 "a fox in fresh snow"
freeimagetovideo --no-wait "a lighthouse in a storm"   # print the task id and return
freeimagetovideo --credits
```

`python -m freeimagetovideo` works too.

## API key and plans

Create a key at [freeimagetovideo.ai/settings/apikeys](https://freeimagetovideo.ai/settings/apikeys), then pass it as `api_key=` or set `FREEIMAGETOVIDEO_API_KEY`. API runs need a paid plan: each run draws on the plan's full-speed allowance, then waits in the relaxed queue. See [pricing](https://freeimagetovideo.ai/pricing). To make clips without a key, use the generator on [freeimagetovideo.ai](https://freeimagetovideo.ai/?utm_source=pypi&utm_medium=package): start with no sign-up, keep going on a free account.

```python
from freeimagetovideo import credits
print(credits())  # credits left on the account
```

## Options

| option | values |
|---|---|
| `duration` | 4, 5, 6, 8, 10, 15 (seconds) |
| `resolution` | `480p` (default), `768p` |
| `aspect_ratio` | `16:9` (default), `9:16`, `1:1` |

Model: MiniMax H3 (`minimax-h3`).

## Submit now, collect later

```python
from freeimagetovideo import submit, status, wait

task_id = submit("a lighthouse in a storm, waves crashing", duration=5)
print(status(task_id)["status"])   # pending | processing | success | failed | canceled
url = wait(task_id)                # polls every 10 seconds, 30 minutes by default
```

## Errors worth catching

Each failure is its own subclass of `FreeImageToVideoError`:

- `AuthError`: no key, or the key is wrong or deleted
- `QuotaError`: not enough credits for this run
- `PlanError`: API runs need a paid plan
- `BusyError`: too many runs generating at once on this account
- `RejectedError`: the content filter refused the prompt, or a cooldown is active; reword it
- `GenerationFailed`: the run was accepted but failed; `.error_message` says why
- `GenerationTimeout`: still generating at the deadline; check it later with `status()`
- `APIError`: anything else, with the server's message

The service answers most refusals as HTTP 200 with a non-zero `code`, so the SDK reads the envelope, not just the status code.

Full docs: [freeimagetovideo.readthedocs.io](https://freeimagetovideo.readthedocs.io/). MIT licensed.
