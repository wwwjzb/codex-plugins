#!/usr/bin/env python3
"""Describe images with a Zhipu GLM vision model using API-key rotation.

Optimizations:
  * Local images are downscaled/re-encoded (Pillow, when available) before
    upload so large screenshots cost fewer image tiles and less bandwidth.
  * Batch mode (--image A.png --image B.png ...) sends several images in ONE
    API request, which avoids Zhipu per-minute rate limits on multi-image jobs.
  * HTTP 429 / rate-limit responses are retried with Retry-After backoff
    instead of failing immediately, and calls are paced per API key across
    processes so consecutive invocations don't trip the limits.
  * Successful results are cached on disk keyed by (image bytes + prompt +
    model), so repeating the same request returns instantly.
  * State/cache writes are best-effort so the script still works in
    read-only environments.

Usage:
  vision.py <image_path_or_url> [prompt] [options]
  vision.py --image <img1> [--image <img2> ...] [prompt] [options]

Options:
  --config PATH        Config JSON path
  --state PATH         Key-rotation/rate-limit state JSON path
  --max-tokens N       Override config max_tokens
  --max-image-size N   Longest edge in px after downscaling local images
  --model NAME         Override config model (e.g. glm-4.6v-flash)
  --no-cache           Bypass the on-disk response cache
  --no-wait            Disable cross-process pacing between calls
  --verbose            Print pacing/retry diagnostics to stderr

Exit codes:
  0  success (model text is printed to stdout)
  1  usage / input error (missing file, unsupported format, bad config)
  2  all API keys failed
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import mimetypes
import os
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}
DEFAULT_PROMPT = "请详细描述这张图片的内容。"
DEFAULT_PROMPT_BATCH = "请依次详细描述这些图片的内容，并为每张图片标注序号。"
DEFAULT_MAX_TOKENS = 2048
DEFAULT_MAX_IMAGE_SIZE = 1568
DEFAULT_JPEG_QUALITY = 88
DEFAULT_MIN_INTERVAL = 5.0
DEFAULT_RATE_LIMIT_RETRIES = 3
RATE_LIMIT_DEFAULT_WAIT = 10.0
MAX_RETRY_WAIT = 60.0
LOCK_TIMEOUT = 10.0
CACHE_MAX_ENTRIES = 200
CACHE_TRIM_TO = 100
CONFIG_FILENAME = "config.json"
STATE_FILENAME = "state.json"


def script_dir() -> Path:
    return Path(__file__).resolve().parent


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_config(config_path: Path) -> dict:
    if not config_path.is_file():
        raise ValueError(f"config file not found: {config_path}")
    config = load_json(config_path)
    keys = config.get("api_keys")
    if not isinstance(keys, list) or not keys or not all(
        isinstance(k, str) and k.strip() for k in keys
    ):
        raise ValueError("config.api_keys must be a non-empty array of strings")
    endpoint = config.get("endpoint")
    if not isinstance(endpoint, str) or not endpoint.strip():
        raise ValueError("config.endpoint must be a non-empty string")
    model = config.get("model")
    if not isinstance(model, str) or not model.strip():
        raise ValueError("config.model must be a non-empty string")
    return config


def load_state_full(state_path: Path) -> dict:
    try:
        state = load_json(state_path)
        if not isinstance(state, dict):
            return {"last_success_index": 0, "last_calls": {}}
    except Exception:
        return {"last_success_index": 0, "last_calls": {}}
    state.setdefault("last_calls", {})
    if not isinstance(state["last_calls"], dict):
        state["last_calls"] = {}
    return state


def load_state(state_path: Path) -> int:
    state = load_state_full(state_path)
    try:
        return max(0, int(state.get("last_success_index", 0)))
    except Exception:
        return 0


def _write_state(state_path: Path, state: dict) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(state_path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(state, handle)
        os.replace(tmp_name, state_path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


class FileLock:
    """Cross-process advisory lock based on an exclusive lock file."""

    def __init__(self, lock_path: Path, timeout: float = LOCK_TIMEOUT) -> None:
        self.lock_path = Path(lock_path)
        self.timeout = timeout

    def __enter__(self) -> "FileLock":
        try:
            self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        deadline = time.time() + self.timeout
        while True:
            try:
                fd = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(fd)
                return self
            except FileExistsError:
                if time.time() >= deadline:
                    return self  # Proceed unlocked (best effort).
                time.sleep(0.05)
            except OSError:
                return self

    def __exit__(self, *exc) -> None:
        try:
            self.lock_path.unlink()
        except OSError:
            pass


def save_state(state_path: Path, index: int) -> None:
    """Persist key-rotation state; failures are intentionally non-fatal."""
    try:
        with FileLock(state_path.with_suffix(".lock")):
            state = load_state_full(state_path)
            state["last_success_index"] = index
            state.setdefault("last_calls", {})
            _write_state(state_path, state)
    except Exception:
        pass


def record_call(state_path: Path, index: int, after_seconds: float = 0.0) -> None:
    """Remember when a key was used so the next invocation can pace itself."""
    try:
        with FileLock(state_path.with_suffix(".lock")):
            state = load_state_full(state_path)
            last_calls = state.setdefault("last_calls", {})
            last_calls[str(index)] = time.time() + max(0.0, float(after_seconds))
            _write_state(state_path, state)
    except Exception:
        pass


def pace_call(state_path: Path, index: int, min_interval: float) -> None:
    """Wait so the chosen key is not used more often than ``min_interval``."""
    if min_interval <= 0:
        return
    try:
        with FileLock(state_path.with_suffix(".lock")):
            state = load_state_full(state_path)
            last_calls = state.get("last_calls") or {}
            last = float(last_calls.get(str(index), 0) or 0)
        wait = last + min_interval - time.time()
        if wait > 0:
            time.sleep(wait)
    except Exception:
        pass


def is_remote_url(value: str) -> bool:
    lowered = value.lower()
    return lowered.startswith("http://") or lowered.startswith("https://")


def _pillow_available() -> bool:
    try:
        from PIL import Image  # noqa: F401

        return True
    except Exception:
        return False


def optimize_image_bytes(path: Path, max_size: int) -> tuple[bytes, str]:
    """Return (image bytes, mime) best suited for upload.

    Uses Pillow when available: downscales images whose longest edge exceeds
    ``max_size`` and re-encodes very large files as JPEG. Falls back to the
    original bytes when Pillow is missing or the image is already compact.
    """
    if not path.is_file():
        raise ValueError(f"image file not found: {path}")
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise ValueError(
            f"unsupported image format '{suffix or '(none)'}' for {path}; "
            f"supported: {supported}"
        )

    raw_bytes = path.read_bytes()
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"

    if not _pillow_available():
        return raw_bytes, mime

    try:
        from PIL import Image

        with Image.open(io.BytesIO(raw_bytes)) as im:
            width, height = im.size
            longest = max(width, height)
            needs_resize = longest > max_size
            needs_reencode = not needs_resize and len(raw_bytes) > 1_500_000
            if not needs_resize and not needs_reencode:
                return raw_bytes, mime

            # Flatten transparency onto a white background (JPEG has no alpha).
            if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
                rgba = im.convert("RGBA")
                background = Image.new("RGB", rgba.size, (255, 255, 255))
                background.paste(rgba, mask=rgba.split()[-1])
                rgb = background
            else:
                rgb = im.convert("RGB")

            if needs_resize:
                scale = max_size / float(longest)
                rgb = rgb.resize(
                    (max(1, round(width * scale)), max(1, round(height * scale))),
                    Image.LANCZOS,
                )

            buffer = io.BytesIO()
            rgb.save(
                buffer,
                format="JPEG",
                quality=DEFAULT_JPEG_QUALITY,
                optimize=True,
            )
            return buffer.getvalue(), "image/jpeg"
    except Exception:
        # Any preprocessing failure must never block the API path.
        return raw_bytes, mime


def image_to_data_url(path: Path, max_size: int) -> str:
    data, mime = optimize_image_bytes(path, max_size)
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def cache_dir(config: dict) -> Path:
    configured = config.get("cache_dir")
    if isinstance(configured, str) and configured.strip():
        return Path(configured).expanduser()
    return script_dir() / "cache"


def cache_key(data: bytes, prompt: str, model: str) -> str:
    digest = hashlib.sha256()
    digest.update(data)
    digest.update(b"\x00")
    digest.update(prompt.encode("utf-8"))
    digest.update(b"\x00")
    digest.update(model.encode("utf-8"))
    return digest.hexdigest()


def cache_lookup(cache_root: Path, key: str, prompt: str, model: str) -> str | None:
    try:
        entry_path = cache_root / f"{key}.json"
        if not entry_path.is_file():
            return None
        entry = load_json(entry_path)
        if entry.get("prompt") == prompt and entry.get("model") == model:
            result = entry.get("result")
            if isinstance(result, str) and result:
                return result
    except Exception:
        pass
    return None


def cache_save(cache_root: Path, key: str, prompt: str, model: str, result: str) -> None:
    """Best-effort cache write; never fail the API path because of it."""
    try:
        cache_root.mkdir(parents=True, exist_ok=True)
        entry_path = cache_root / f"{key}.json"
        fd, tmp_name = tempfile.mkstemp(dir=str(cache_root), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "prompt": prompt,
                        "model": model,
                        "result": result,
                        "created_at": int(time.time()),
                    },
                    handle,
                    ensure_ascii=False,
                )
            os.replace(tmp_name, entry_path)
        except Exception:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
        _trim_cache(cache_root)
    except Exception:
        pass


def _trim_cache(
    cache_root: Path,
    max_entries: int = CACHE_MAX_ENTRIES,
    trim_to: int = CACHE_TRIM_TO,
) -> None:
    try:
        entries = [p for p in cache_root.glob("*.json") if p.is_file()]
        if len(entries) <= max_entries:
            return
        entries.sort(key=lambda p: p.stat().st_mtime)
        for stale in entries[: len(entries) - trim_to]:
            try:
                stale.unlink()
            except OSError:
                pass
    except Exception:
        pass


def build_request_body(
    config: dict,
    image_urls: list[str],
    prompt: str,
    max_tokens: int,
) -> dict:
    content = [{"type": "image_url", "image_url": {"url": url}} for url in image_urls]
    content.append({"type": "text", "text": prompt})
    return {
        "model": config["model"],
        "messages": [{"role": "user", "content": content}],
        "max_tokens": max_tokens,
        "temperature": float(config.get("temperature", 0.2)),
    }


class RateLimitedError(RuntimeError):
    def __init__(self, wait_seconds: float, detail: str) -> None:
        super().__init__(f"rate limited: {detail}")
        self.wait_seconds = max(0.0, float(wait_seconds or 0))


def _retry_seconds_from_headers(error: urllib.error.HTTPError) -> float:
    try:
        raw = error.headers.get("Retry-After")
        if raw:
            value = float(raw)
            if value >= 0:
                return value
    except Exception:
        pass
    return 0.0


def _retry_seconds_from_body(detail: str) -> float:
    try:
        payload = json.loads(detail)
        err = payload.get("error") if isinstance(payload, dict) else None
        if not isinstance(err, dict):
            err = payload if isinstance(payload, dict) else {}
        for key in ("retry_after_ms", "retry_after", "Retry-After"):
            if key in err:
                value = float(err[key])
                if key == "retry_after_ms":
                    value /= 1000.0
                if value >= 0:
                    return value
    except Exception:
        pass
    return 0.0


def call_api(
    config: dict,
    image_urls: list[str],
    prompt: str,
    api_key: str,
    timeout: int,
    max_tokens: int,
) -> str:
    body = json.dumps(
        build_request_body(config, image_urls, prompt, max_tokens)
    ).encode("utf-8")
    request = urllib.request.Request(
        config["endpoint"],
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:500]
        if error.code == 429:
            wait = _retry_seconds_from_headers(error) or _retry_seconds_from_body(detail)
            raise RateLimitedError(wait, f"HTTP 429: {detail}") from error
        raise RuntimeError(f"HTTP {error.code}: {detail}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"network error: {error.reason}") from error
    except TimeoutError as error:
        raise RuntimeError("request timed out") from error
    except json.JSONDecodeError as error:
        raise RuntimeError("invalid JSON response") from error
    except Exception as error:
        raise RuntimeError(f"request failed: {error}") from error

    if "error" in payload:
        err = payload["error"]
        msg = json.dumps(err, ensure_ascii=False)
        code = str(err.get("code", "")) if isinstance(err, dict) else ""
        lowered = msg.lower()
        if (
            code in ("429", "rate_limit", "ratelimit", "ratelimiterror")
            or "限流" in msg
            or "rate limit" in lowered
        ):
            wait = _retry_seconds_from_body(json.dumps(payload, ensure_ascii=False)[:500])
            raise RateLimitedError(wait, msg) from None
        raise RuntimeError(f"API error: {msg}") from None
    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as error:
        preview = json.dumps(payload, ensure_ascii=False)[:500]
        raise RuntimeError(f"unexpected response shape: {preview}") from error

    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
        if parts:
            return "\n".join(parts)
    raise RuntimeError(f"unsupported content type: {type(content).__name__}")


def masked_key(api_key: str) -> str:
    return api_key[:8] + "..." if len(api_key) > 8 else "***"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Describe images with a Zhipu GLM vision model (API-key rotation)."
    )
    parser.add_argument("image", nargs="?", default=None, help="Local image path or http(s) URL")
    parser.add_argument("prompt", nargs="?", default=None, help="Instruction for the model")
    parser.add_argument(
        "--image",
        action="append",
        dest="images",
        default=None,
        metavar="IMG",
        help="Image to include; repeat --image for multiple images sent in one API request (avoids rate limits)",
    )
    parser.add_argument(
        "--config",
        default=str(script_dir() / CONFIG_FILENAME),
        help=f"Config JSON path (default: <script_dir>/{CONFIG_FILENAME})",
    )
    parser.add_argument(
        "--state",
        default=str(script_dir() / STATE_FILENAME),
        help=f"State JSON path (default: <script_dir>/{STATE_FILENAME})",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=None,
        help="Override the config max_tokens (default from config, else 2048)",
    )
    parser.add_argument(
        "--max-image-size",
        type=int,
        default=None,
        help="Longest edge in px after downscaling local images (default 1568)",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Override the config model, e.g. glm-4.6v-flash for faster responses",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Bypass the on-disk response cache",
    )
    parser.add_argument(
        "--no-wait",
        action="store_true",
        help="Disable cross-process pacing between API calls",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print pacing/retry diagnostics to stderr",
    )
    args = parser.parse_args(argv)

    try:
        config = load_config(Path(args.config))
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    images = list(args.images) if args.images else ([args.image] if args.image else [])
    if not images:
        print("error: provide <image> or --image <img> (repeatable)", file=sys.stderr)
        return 1

    prompt = args.prompt.strip() if args.prompt and args.prompt.strip() else None
    if prompt is None:
        prompt = DEFAULT_PROMPT_BATCH if len(images) > 1 else DEFAULT_PROMPT
    max_tokens = args.max_tokens or int(config.get("max_tokens", DEFAULT_MAX_TOKENS))
    max_image_size = args.max_image_size or int(config.get("max_image_size", DEFAULT_MAX_IMAGE_SIZE))

    try:
        image_urls = []
        sent_parts = []
        for item in images:
            if is_remote_url(item):
                image_urls.append(item)
                sent_parts.append(item.encode("utf-8"))
            else:
                url = image_to_data_url(Path(item), max_image_size)
                image_urls.append(url)
                sent_parts.append(url.encode("ascii"))
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    sent_bytes = b"\x1f".join(sent_parts)
    any_remote = any(is_remote_url(item) for item in images)

    keys = config["api_keys"]
    timeout = int(config.get("timeout", 60))
    model = args.model or config["model"]
    min_interval = 0.0 if args.no_wait else float(config.get("rate_limit_interval", DEFAULT_MIN_INTERVAL))
    max_retries = int(config.get("rate_limit_retries", DEFAULT_RATE_LIMIT_RETRIES))

    cache_root = cache_dir(config)
    use_cache = not args.no_cache and not any_remote
    if use_cache:
        cached = cache_lookup(cache_root, cache_key(sent_bytes, prompt, model), prompt, model)
        if cached is not None:
            print(cached)
            return 0

    last_success = load_state(Path(args.state))
    start = (last_success + 1) % len(keys)

    failures = []
    for offset in range(len(keys)):
        index = (start + offset) % len(keys)
        api_key = keys[index]
        attempts = 0
        while True:
            attempts += 1
            pace_call(Path(args.state), index, min_interval)
            try:
                result = call_api(config, image_urls, prompt, api_key, timeout, max_tokens)
            except RateLimitedError as error:
                wait = error.wait_seconds or RATE_LIMIT_DEFAULT_WAIT
                wait = min(wait, MAX_RETRY_WAIT)
                record_call(Path(args.state), index, wait)
                if attempts <= max_retries:
                    if args.verbose:
                        print(
                            f"[glm-vision] key[{index}] rate limited; "
                            f"retrying in {wait:.0f}s (attempt {attempts}/{max_retries})",
                            file=sys.stderr,
                        )
                    time.sleep(wait)
                    continue
                failures.append(f"key[{index}] ({masked_key(api_key)}): {error}")
                break
            except RuntimeError as error:
                record_call(Path(args.state), index)
                failures.append(f"key[{index}] ({masked_key(api_key)}): {error}")
                break
            record_call(Path(args.state), index)
            save_state(Path(args.state), index)
            if use_cache:
                cache_save(
                    cache_root,
                    cache_key(sent_bytes, prompt, model),
                    prompt,
                    model,
                    result,
                )
            print(result)
            return 0

    print("all API keys failed:", file=sys.stderr)
    for failure in failures:
        print(f"  {failure}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
