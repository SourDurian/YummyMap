#!/usr/bin/env python3
"""Collect Bilibili video metadata into a review queue without inventing restaurant facts."""
import argparse
import csv
import json
import subprocess
import sys
import urllib.parse
import urllib.request
import hashlib
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".cache" / "bilibili"
QUEUE = ROOT / "data" / "review_queue.csv"
SPACE_URL = "https://space.bilibili.com/9433848/upload/video"
FIELDS = ["bvid", "title", "published_at", "video_url", "description", "status", "notes"]
MIXIN_KEY_ENC_TAB = [46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52]
HEADERS = {"User-Agent": "Mozilla/5.0 YummyMap/1.0", "Referer": "https://space.bilibili.com/9433848/"}

def run_ytdlp(args):
    command = [sys.executable, "-m", "yt_dlp", *args]
    return subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")

def get_json(url):
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)

def wbi_keys():
    payload = get_json("https://api.bilibili.com/x/web-interface/nav")
    images = (payload.get("data") or {}).get("wbi_img") or {}
    img_key = Path(urllib.parse.urlparse(images.get("img_url", "")).path).stem
    sub_key = Path(urllib.parse.urlparse(images.get("sub_url", "")).path).stem
    if not img_key or not sub_key:
        raise RuntimeError("无法取得 B 站 WBI 密钥")
    combined = img_key + sub_key
    return "".join(combined[index] for index in MIXIN_KEY_ENC_TAB)[:32]

def sign_wbi(params, mixin_key):
    params = {**params, "wts": int(time.time())}
    filtered = {key: str(value).translate({ord(char): None for char in "!'()*"}) for key, value in params.items()}
    query = urllib.parse.urlencode(sorted(filtered.items()))
    return query + "&w_rid=" + hashlib.md5((query + mixin_key).encode()).hexdigest()

def list_videos_wbi(limit):
    mixin_key = wbi_keys()
    entries, page, page_size = [], 1, 50
    while True:
        query = sign_wbi({"mid": "9433848", "pn": page, "ps": page_size, "order": "pubdate", "platform": "web"}, mixin_key)
        payload = get_json("https://api.bilibili.com/x/space/wbi/arc/search?" + query)
        if payload.get("code") != 0:
            raise RuntimeError(f"视频列表接口返回 code={payload.get('code')}: {payload.get('message', '')}")
        videos = (((payload.get("data") or {}).get("list") or {}).get("vlist") or [])
        entries.extend({"id": item.get("bvid"), "url": f"https://www.bilibili.com/video/{item.get('bvid')}"} for item in videos if item.get("bvid"))
        total = int(((payload.get("data") or {}).get("page") or {}).get("count") or len(entries))
        if (limit and len(entries) >= limit) or not videos or len(entries) >= total:
            return entries[:limit] if limit else entries
        page += 1

def list_videos(limit):
    try:
        return list_videos_wbi(limit)
    except Exception as api_error:
        print(f"WBI 列表接口不可用，改用 yt-dlp: {api_error}", file=sys.stderr)
    args = ["--flat-playlist", "--dump-single-json"]
    if limit:
        args += ["--playlist-end", str(limit)]
    result = run_ytdlp([*args, SPACE_URL])
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "无法读取视频列表")
    return json.loads(result.stdout).get("entries", [])

def public_api_metadata(bvid):
    endpoint = "https://api.bilibili.com/x/web-interface/view?" + urllib.parse.urlencode({"bvid": bvid})
    request = urllib.request.Request(endpoint, headers=HEADERS)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.load(response)
        if payload.get("code") == 0 and payload.get("data"):
            data = payload["data"]
            return {
                "id": data.get("bvid", bvid),
                "title": data.get("title", ""),
                "description": data.get("desc", ""),
                "timestamp": data.get("pubdate"),
                "webpage_url": f"https://www.bilibili.com/video/{bvid}",
                "uploader": (data.get("owner") or {}).get("name", ""),
                "thumbnail": data.get("pic", ""),
                "duration": data.get("duration"),
                "cid": data.get("cid"),
            }, ""
        return None, f"B 站接口返回 code={payload.get('code')}: {payload.get('message', '')}"
    except Exception as exc:
        return None, f"公开接口读取失败: {exc}"

def video_metadata(bvid, url, browser):
    info, error = public_api_metadata(bvid)
    if info:
        return info, ""
    args = ["--skip-download", "--dump-single-json"]
    if browser:
        args += ["--cookies-from-browser", browser]
    result = run_ytdlp([*args, url])
    if result.returncode or not result.stdout.strip() or result.stdout.strip() == "null":
        detail = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "元数据读取失败"
        return None, f"{error}; {detail}"
    return json.loads(result.stdout), ""

def load_existing():
    if not QUEUE.exists():
        return {}
    with QUEUE.open(encoding="utf-8-sig", newline="") as handle:
        return {row["bvid"]: row for row in csv.DictReader(handle)}

def iso_date(info):
    stamp = info.get("timestamp") or info.get("release_timestamp")
    if stamp:
        return datetime.fromtimestamp(stamp, timezone.utc).date().isoformat()
    value = info.get("upload_date") or ""
    return f"{value[:4]}-{value[4:6]}-{value[6:8]}" if len(value) == 8 else ""

def main():
    parser = argparse.ArgumentParser(description="获取员外的觅食人生视频清单并生成复核队列")
    parser.add_argument("--limit", type=int, default=0, help="仅处理最新 N 条；0 表示全部")
    parser.add_argument("--cookies-from-browser", choices=["chrome", "edge", "firefox"], help="使用已登录浏览器的 B 站会话")
    args = parser.parse_args()
    CACHE.mkdir(parents=True, exist_ok=True)
    existing = load_existing()
    entries = list_videos(args.limit)
    rows = dict(existing)
    for index, entry in enumerate(entries, 1):
        bvid = entry.get("id", "")
        if not bvid or bvid in rows:
            continue
        url = entry.get("url") or f"https://www.bilibili.com/video/{bvid}"
        info, error = video_metadata(bvid, url, args.cookies_from_browser)
        if info:
            rows[bvid] = {"bvid": bvid, "title": info.get("title", ""), "published_at": iso_date(info), "video_url": info.get("webpage_url") or url, "description": (info.get("description") or "").replace("\r", " ").replace("\n", " | "), "status": "待筛选", "notes": ""}
            (CACHE / f"{bvid}.json").write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            rows[bvid] = {"bvid": bvid, "title": "", "published_at": "", "video_url": url, "description": "", "status": "元数据受限", "notes": error}
        print(f"[{index}/{len(entries)}] {bvid}: {rows[bvid]['status']}")
    QUEUE.parent.mkdir(parents=True, exist_ok=True)
    with QUEUE.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows.values())
    print(f"已写入 {QUEUE}，共 {len(rows)} 条")

if __name__ == "__main__":
    main()
