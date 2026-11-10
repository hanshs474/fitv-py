"""Command line: generate a video clip with sound on Free Image to Video and print its URL.

    freeimagetovideo "a paper lantern drifting over a night river"
    freeimagetovideo --image https://example.com/statue.jpg "the camera slowly orbits the statue"
    freeimagetovideo -o duration=10 -o resolution=768p -o aspect_ratio=9:16 "a fox in fresh snow"
    freeimagetovideo --credits

Set FREEIMAGETOVIDEO_API_KEY (create a key at https://freeimagetovideo.ai/settings/apikeys).
"""

from __future__ import annotations

import argparse
import sys
from typing import Any, Dict, List, Optional

from . import KEYS_URL, FreeImageToVideoError, __version__, credits, generate_video, submit


def _value(v: str) -> Any:
    try:
        return int(v)
    except ValueError:
        pass
    if v.lower() in ("true", "false"):
        return v.lower() == "true"
    return v


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="freeimagetovideo",
        description="Generate a video clip with sound on Free Image to Video (https://freeimagetovideo.ai) and print its URL.",
        epilog=f"Set FREEIMAGETOVIDEO_API_KEY (create a key at {KEYS_URL}).",
    )
    p.add_argument("prompt", nargs="*", help="what the clip shows")
    p.add_argument("--image", metavar="URL", help="public https image to animate (image to video: it becomes the first frame)")
    p.add_argument("-o", "--option", action="append", default=[], metavar="KEY=VALUE",
                   help="duration=4|5|6|8|10|15, resolution=480p|768p, aspect_ratio=16:9|9:16|1:1 (repeatable)")
    p.add_argument("--no-wait", action="store_true", help="print the task id instead of waiting for the clip")
    p.add_argument("--credits", action="store_true", help="print the credits left on the account")
    p.add_argument("--version", action="version", version=f"freeimagetovideo {__version__}")
    a = p.parse_args(argv)

    opts: Dict[str, Any] = {}
    for kv in a.option:
        k, sep, v = kv.partition("=")
        if not sep:
            p.error(f"option {kv!r}: want key=value")
        opts[k] = _value(v)
    try:
        if a.credits:
            print(credits())
            return 0
        prompt = " ".join(a.prompt).strip()
        if not prompt:
            p.print_usage(sys.stderr)
            return 2
        if a.no_wait:
            print(submit(prompt, a.image, **opts))
        else:
            print(generate_video(prompt, a.image, **opts))
        return 0
    except FreeImageToVideoError as e:
        print(f"freeimagetovideo: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
