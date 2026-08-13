#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MiniMax music-3.0-free 试听预览生成脚本（仅用 Python 标准库）。

流程：
  1. 调用 MiniMax 音乐生成接口（model=music-3.0-free，WAV + URL）
  2. 下载返回的音频
  3. 裁剪到 <= --seconds 秒（默认 30 秒；不足 15 秒保留原长）
  4. 保存到 --out 目录，打印保存路径与时长

密钥来源（按优先级）：
  1. 环境变量 MINIMAX_API_KEY
  2. ~/.codex/miao-song-planner/config.json 中的 "api_key"

严禁把 API Key 写入任何仓库文件或提交到 GitHub。

退出码：
  0 = 成功；2 = 缺少密钥；3 = 网络/下载失败；4 = MiniMax 业务错误；5 = 其他（合成中/无音频）。
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
import wave
from pathlib import Path

API_URL = "https://api.minimaxi.com/v1/music_generation"
MODEL = "music-3.0-free"
DEFAULT_SECONDS = 30

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def get_api_key():
    key = os.environ.get("MINIMAX_API_KEY", "").strip()
    if key:
        return key
    cfg = Path.home() / ".codex" / "miao-song-planner" / "config.json"
    if cfg.exists():
        try:
            key = json.loads(cfg.read_text(encoding="utf-8")).get("api_key", "").strip()
        except Exception:
            key = ""
    if not key:
        sys.stderr.write(
            "未找到 MiniMax API Key：请设置环境变量 MINIMAX_API_KEY，"
            "或在 ~/.codex/miao-song-planner/config.json 中提供 api_key。\n"
        )
        sys.exit(2)
    return key


def call_music(prompt, lyrics, instrumental):
    key = get_api_key()
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "audio_setting": {"format": "wav", "sample_rate": 44100, "bitrate": 256000},
        "output_format": "url",
        "is_instrumental": bool(instrumental),
    }
    if lyrics:
        payload["lyrics"] = lyrics
    elif not instrumental:
        payload["lyrics_optimizer"] = True

    req = urllib.request.Request(
        API_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + key,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=240) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        sys.stderr.write(f"接口 HTTP {e.code}: {body}\n")
        sys.exit(3)
    except Exception as e:
        sys.stderr.write(f"网络请求失败: {e}\n")
        sys.exit(3)

    base = result.get("base_resp", {})
    code = base.get("status_code", -1)
    if code != 0:
        msg = base.get("status_msg", "未知错误")
        hint = {
            1002: "触发限流（每分钟最多 3 次），请稍候再试。",
            1004: "API Key 鉴权失败，请检查密钥。",
            1008: "账户余额不足：请到 platform.minimaxi.com 充值后重试（免费档同样需要账户有余额）。",
            2013: "请求参数异常，请检查 prompt/歌词格式。",
            2049: "API Key 无效，请检查密钥。",
        }.get(code, "")
        sys.stderr.write(f"MiniMax 返回错误 {code}: {msg}。{hint}\n")
        sys.exit(4)

    data = result.get("data") or {}
    if data.get("status") == 1:
        sys.stderr.write("音乐仍在合成中，请稍后重试本次调用。\n")
        sys.exit(5)
    audio = data.get("audio") or data.get("audio_url") or ""
    if not audio:
        sys.stderr.write("返回数据中没有音频。\n")
        sys.exit(5)
    return audio


def fetch_audio(audio):
    if audio.startswith("http://") or audio.startswith("https://"):
        try:
            with urllib.request.urlopen(audio, timeout=240) as resp:
                return resp.read()
        except Exception as e:
            sys.stderr.write(f"音频下载失败: {e}\n")
            sys.exit(3)
    try:
        return bytes.fromhex(audio)
    except ValueError:
        sys.stderr.write("无法解析返回的音频数据。\n")
        sys.exit(5)


def load_and_trim(raw, max_seconds):
    tmp = Path(os.environ.get("TEMP", ".")) / f"minimax_tmp_{int(time.time() * 1000)}.wav"
    tmp.write_bytes(raw)
    try:
        with wave.open(str(tmp), "rb") as w:
            params = w.getparams()
            nframes = w.getnframes()
            rate = w.getframerate() or 44100
            cut = min(nframes, int(max_seconds * rate))
            frames = w.readframes(cut)
        params = list(params)
        params[3] = len(frames) // (params[0] * params[1]) if params[0] else 0
        return tuple(params), frames, cut / rate
    finally:
        tmp.unlink(missing_ok=True)


def main():
    ap = argparse.ArgumentParser(description="MiniMax 音乐试听预览")
    ap.add_argument("--prompt", required=True, help="风格/情绪/场景描述")
    ap.add_argument("--lyrics", default="", help="歌词（可选；不传且非纯音乐时由模型自动写词）")
    ap.add_argument("--instrumental", action="store_true", help="纯音乐（无歌词）")
    ap.add_argument("--out", default=".", help="输出目录")
    ap.add_argument("--tag", default="preview", help="文件名前缀")
    ap.add_argument("--seconds", type=int, default=DEFAULT_SECONDS, help="裁剪时长（默认 30 秒）")
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    audio = call_music(args.prompt.strip(), args.lyrics.strip(), args.instrumental)
    raw = fetch_audio(audio)
    params, frames, duration = load_and_trim(raw, args.seconds)

    ts = time.strftime("%Y%m%d_%H%M%S")
    dest = out_dir / f"{args.tag}_{ts}.wav"
    with wave.open(str(dest), "wb") as w:
        w.setparams(params)
        w.writeframes(frames)

    print(f"SAVED:{dest}")
    print(f"DURATION:{duration:.1f}")


if __name__ == "__main__":
    main()
