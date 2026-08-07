#!/usr/bin/env python3
"""Describe an image with a Zhipu GLM vision model using API-key rotation.

Optimizations over the original version:
  * Local images are downscaled/re-encoded (Pillow, when available) before
    upload so large screenshots cost fewer image tiles and less bandwidth.
  * Successful results are cached on disk keyed by (image bytes + prompt +
    model), so repeating the same request returns instantly.
  * The default max_tokens is lower (configurable) to keep responses fast.
  * State/cache writes are best-effort so the script still works in
    read-only environments.

Usage:
  vision.py <image_path_or_url> [prompt] [--config PATH] [--state PATH]
            [--max-tokens N] [--max-image-size N] [--no-cache]

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
DEFAULT_MAX_TOKENS = 2048
DEFAULT_MAX_IMAGE_SIZE = 1568
DEFAULT_JPEG_QUALITY = 88
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


def load_state(state_path: Path) -> int:
    try:
        state = load_json(state_path)
        return max(0, int(state.get("last_success_index", 0)))
    except Exception:
        return 0


def save_state(state_path: Path, index: int) -> None:
    """Persist key-rotation state; failures are intentionally non-fatal."""
    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=str(state_path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump({"last_success_index": index}, handle)
            os.replace(tmp_name, state_path)
        except Exception:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
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


def _trim_cache(cache_root: Path, max_entries: int = CACHE_MAX_ENTRIES, trim_to: int = CACHE_TRIM_TO) -> None:
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


def build_request_body(config: dict, image_url: str, prompt: str, max_tokens: int) -> dict:
    return {
        "model": config["model"],
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": image_url}},
                    {"type": "text", "text": prompt},
                ],
            }
        ],
        "max_tokens": max_tokens,
        "temperature": float(config.get("temperature", 0.2)),
    }


def call_api(
    config: dict,
    image_url: str,
    prompt: str,
    api_key: str,
    timeout: int,
    max_tokens: int,
) -> str:
    body = json.dumps(build_request_body(config, image_url, prompt, max_tokens)).encode("utf-8")
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
        raise RuntimeError(f"API error: {json.dumps(payload['error'], ensure_ascii=False)}")
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
        description="Describe an image with a Zhipu GLM vision model (API-key rotation)."
    )
    parser.add_argument("image", help="Local image path or http(s) URL")
    parser.add_argument("prompt", nargs="?", default=None, help="Instruction for the model")
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
    args = parser.parse_args(argv)

    try:
        config = load_config(Path(args.config))
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    prompt = args.prompt.strip() if args.prompt and args.prompt.strip() else DEFAULT_PROMPT
    max_tokens = args.max_tokens or int(config.get("max_tokens", DEFAULT_MAX_TOKENS))
    max_image_size = args.max_image_size or int(config.get("max_image_size", DEFAULT_MAX_IMAGE_SIZE))

    try:
        is_remote = is_remote_url(args.image)
        if is_remote:
            image_url = args.image
            sent_bytes = args.image.encode("utf-8")
        else:
            image_url = image_to_data_url(Path(args.image), max_image_size)
            sent_bytes = image_url.encode("ascii")
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    keys = config["api_keys"]
    timeout = int(config.get("timeout", 60))
    model = args.model or config["model"]

    cache_root = cache_dir(config)
    use_cache = not args.no_cache and not is_remote
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
        try:
            result = call_api(config, image_url, prompt, api_key, timeout, max_tokens)
        except RuntimeError as error:
            failures.append(f"key[{index}] ({masked_key(api_key)}): {error}")
            continue
        save_state(Path(args.state), index)
        if use_cache:
            cache_save(cache_root, cache_key(sent_bytes, prompt, model), prompt, model, result)
        print(result)
        return 0

    print("all API keys failed:", file=sys.stderr)
    for failure in failures:
        print(f"  {failure}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
