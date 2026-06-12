#!/usr/bin/env python3
"""Download a public Bilibili audio track and create a local review transcript."""
import argparse
import json
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".cache" / "audio"
TRANSCRIPTS = ROOT / "data" / "transcripts"
HEADERS = {"User-Agent": "Mozilla/5.0 YummyMap/1.0", "Referer": "https://www.bilibili.com/"}

def get_json(url):
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)

def video_info(bvid):
    payload = get_json("https://api.bilibili.com/x/web-interface/view?" + urllib.parse.urlencode({"bvid": bvid}))
    if payload.get("code") != 0:
        raise RuntimeError(payload.get("message") or "视频详情读取失败")
    return payload["data"]

def audio_url(bvid, cid):
    query = urllib.parse.urlencode({"bvid": bvid, "cid": cid, "qn": 16, "fnval": 16, "fourk": 0})
    payload = get_json("https://api.bilibili.com/x/player/playurl?" + query)
    audio = ((payload.get("data") or {}).get("dash") or {}).get("audio") or []
    if not audio:
        raise RuntimeError("公开视频接口没有返回音轨")
    return max(audio, key=lambda item: item.get("bandwidth", 0)).get("baseUrl") or audio[0].get("base_url")

def download(url, target):
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=120) as response, target.open("wb") as handle:
        while chunk := response.read(1024 * 1024):
            handle.write(chunk)

def main():
    parser = argparse.ArgumentParser(description="下载 B 站公开视频音轨并生成中文转写")
    parser.add_argument("bvid")
    parser.add_argument("--model", default="base", help="faster-whisper 模型，默认 base")
    args = parser.parse_args()
    CACHE.mkdir(parents=True, exist_ok=True)
    TRANSCRIPTS.mkdir(parents=True, exist_ok=True)
    info = video_info(args.bvid)
    audio_path = CACHE / f"{args.bvid}.m4s"
    if not audio_path.exists():
        print(f"下载音轨: {info.get('title', args.bvid)}")
        download(audio_url(args.bvid, info["cid"]), audio_path)
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError("请先安装 faster-whisper: python -m pip install faster-whisper") from exc
    print(f"加载模型: {args.model}")
    model = WhisperModel(args.model, device="cpu", compute_type="int8")
    segments, detected = model.transcribe(str(audio_path), language="zh", vad_filter=True, beam_size=5)
    lines = [f"# {info.get('title', args.bvid)}", "", f"- BV号：{args.bvid}", f"- 识别语言：{detected.language}", ""]
    for segment in segments:
        minutes, seconds = divmod(int(segment.start), 60)
        lines.append(f"[{minutes:02d}:{seconds:02d}] {segment.text.strip()}")
    target = TRANSCRIPTS / f"{args.bvid}.md"
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"转写完成: {target}")

if __name__ == "__main__":
    main()
