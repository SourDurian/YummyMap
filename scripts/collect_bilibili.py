#!/usr/bin/env python3
"""Collect Bilibili video metadata into a review queue without inventing restaurant facts."""
import argparse
import csv
import json
import subprocess
import sys
import urllib.parse
import urllib.request
import http.cookiejar
import hashlib
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".cache" / "bilibili"
QUEUE = ROOT / "data" / "review_queue.csv"
SPACE_URL = "https://space.bilibili.com/9433848/upload/video"
FIELDS = [
    "bvid", "title", "published_at", "video_url", "description",
    "ai_summary", "ai_outline", "summary_status", "status", "notes",
]
MIXIN_KEY_ENC_TAB = [46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52]
HEADERS = {"User-Agent": "Mozilla/5.0 YummyMap/1.0", "Referer": "https://space.bilibili.com/9433848/"}

def run_ytdlp(args):
    command = [sys.executable, "-m", "yt_dlp", *args]
    return subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")

def get_json(url, opener=None):
    request = urllib.request.Request(url, headers=HEADERS)
    open_request = opener.open if opener else urllib.request.urlopen
    with open_request(request, timeout=20) as response:
        return json.load(response)

def cookie_opener(cookie_file):
    if not cookie_file:
        return None
    jar = http.cookiejar.MozillaCookieJar(str(cookie_file))
    jar.load(ignore_discard=True, ignore_expires=True)
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

def export_browser_cookies(browser, target):
    result = run_ytdlp([
        "--cookies-from-browser", browser,
        "--cookies", str(target),
        "--skip-download",
        "--print", "id",
        "https://www.bilibili.com/video/BV1APES6bErr",
    ])
    if result.returncode:
        detail = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "cookie export failed"
        raise RuntimeError(
            f"Unable to export {browser} cookies: {detail}. "
            "Close the browser first, or pass --cookies with a Netscape-format cookie file."
        )
    return target

class ChromeSession:
    def __init__(self, profile):
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
        except ImportError as exc:
            raise RuntimeError("Install Selenium first: python -m pip install selenium") from exc
        options = Options()
        options.add_argument(f"--user-data-dir={profile}")
        options.add_argument("--profile-directory=Default")
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-first-run")
        self.driver = webdriver.Chrome(options=options)
        self.driver.set_script_timeout(30)
        self.driver.get("https://www.bilibili.com/")
        self._mixin_key = None

    def get_json(self, url):
        for attempt in range(5):
            payload = self.driver.execute_async_script(
                """const url = arguments[0], done = arguments[1];
                fetch(url, {credentials: "include"})
                  .then(response => response.json()).then(done)
                  .catch(error => done({code: -1, message: String(error)}));""",
                url,
            )
            if payload.get("code") not in (-352, -799) or attempt == 4:
                time.sleep(0.15)
                return payload
            time.sleep(attempt + 1)

    def wbi_keys(self):
        if self._mixin_key:
            return self._mixin_key
        payload = self.get_json("https://api.bilibili.com/x/web-interface/nav")
        images = (payload.get("data") or {}).get("wbi_img") or {}
        img_key = Path(urllib.parse.urlparse(images.get("img_url", "")).path).stem
        sub_key = Path(urllib.parse.urlparse(images.get("sub_url", "")).path).stem
        combined = img_key + sub_key
        if not combined:
            raise RuntimeError("Unable to read WBI keys in Chrome session")
        self._mixin_key = "".join(combined[index] for index in MIXIN_KEY_ENC_TAB)[:32]
        return self._mixin_key

    def close(self):
        self.driver.quit()

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

def list_videos_wbi(limit, chrome_session=None):
    mixin_key = chrome_session.wbi_keys() if chrome_session else wbi_keys()
    entries, page, page_size = [], 1, 50
    while True:
        query = sign_wbi({"mid": "9433848", "pn": page, "ps": page_size, "order": "pubdate", "platform": "web"}, mixin_key)
        url = "https://api.bilibili.com/x/space/wbi/arc/search?" + query
        payload = chrome_session.get_json(url) if chrome_session else get_json(url)
        if payload.get("code") != 0:
            raise RuntimeError(f"视频列表接口返回 code={payload.get('code')}: {payload.get('message', '')}")
        videos = (((payload.get("data") or {}).get("list") or {}).get("vlist") or [])
        entries.extend({"id": item.get("bvid"), "url": f"https://www.bilibili.com/video/{item.get('bvid')}"} for item in videos if item.get("bvid"))
        total = int(((payload.get("data") or {}).get("page") or {}).get("count") or len(entries))
        if (limit and len(entries) >= limit) or not videos or len(entries) >= total:
            return entries[:limit] if limit else entries
        page += 1

def list_videos(limit, chrome_session=None):
    try:
        return list_videos_wbi(limit, chrome_session)
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

def video_metadata(bvid, url, browser, chrome_session=None):
    if chrome_session:
        payload = chrome_session.get_json(
            "https://api.bilibili.com/x/web-interface/view?" + urllib.parse.urlencode({"bvid": bvid})
        )
        if payload.get("code") == 0 and payload.get("data"):
            data = payload["data"]
            return {
                "id": data.get("bvid", bvid),
                "title": data.get("title", ""),
                "description": data.get("desc", ""),
                "timestamp": data.get("pubdate"),
                "webpage_url": url,
                "uploader": (data.get("owner") or {}).get("name", ""),
                "owner": data.get("owner") or {},
                "thumbnail": data.get("pic", ""),
                "duration": data.get("duration"),
                "cid": data.get("cid"),
            }, ""
        return None, f"Chrome metadata API code={payload.get('code')}: {payload.get('message', '')}"
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

def video_conclusion(info, opener=None, chrome_session=None):
    if not opener and not chrome_session:
        return None, "login_required"
    params = {
        "bvid": info.get("id") or info.get("bvid"),
        "cid": info.get("cid"),
        "up_mid": (info.get("owner") or {}).get("mid") or info.get("uploader_id") or "9433848",
    }
    if not all(params.values()):
        return None, "missing_video_identifiers"
    query = sign_wbi(params, chrome_session.wbi_keys() if chrome_session else wbi_keys())
    url = "https://api.bilibili.com/x/web-interface/view/conclusion/get?" + query
    payload = chrome_session.get_json(url) if chrome_session else get_json(url, opener=opener)
    if payload.get("code") != 0:
        return None, f"api_{payload.get('code')}: {payload.get('message', '')}"
    data = payload.get("data") or {}
    model = data.get("model_result") or {}
    if not model.get("summary") and not model.get("outline"):
        return data, "not_available"
    return data, "available"

def outline_text(conclusion):
    outline = ((conclusion or {}).get("model_result") or {}).get("outline") or []
    parts = []
    for item in outline:
        title = item.get("title") or ""
        timestamp = item.get("timestamp")
        detail = item.get("part_outline") or item.get("summary") or ""
        prefix = f"[{timestamp}s] " if timestamp is not None else ""
        parts.append(f"{prefix}{title}: {detail}".strip(": "))
    return " | ".join(parts)

def load_existing():
    if not QUEUE.exists():
        return {}
    with QUEUE.open(encoding="utf-8-sig", newline="") as handle:
        return {row["bvid"]: row for row in csv.DictReader(handle)}

def write_queue(rows):
    QUEUE.parent.mkdir(parents=True, exist_ok=True)
    with QUEUE.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in FIELDS} for row in rows.values())

def iso_date(info):
    stamp = info.get("timestamp") or info.get("release_timestamp")
    if stamp:
        return datetime.fromtimestamp(stamp, timezone.utc).date().isoformat()
    value = info.get("upload_date") or ""
    return f"{value[:4]}-{value[4:6]}-{value[6:8]}" if len(value) == 8 else ""

def main():
    parser = argparse.ArgumentParser(description="获取员外的觅食人生视频清单并生成复核队列")
    parser.add_argument("--limit", type=int, default=0, help="仅处理最新 N 条；0 表示全部")
    parser.add_argument("--batch-size", type=int, default=20, help="每次最多新增的复核条目数，降低触发风控的概率")
    parser.add_argument("--cookies-from-browser", choices=["chrome", "edge", "firefox"], help="使用已登录浏览器的 B 站会话")
    parser.add_argument("--cookies", type=Path, help="用于无人值守采集 AI 总结的 Netscape 格式 Cookie 文件")
    parser.add_argument("--chrome-profile", type=Path, help="由 Chrome 自己管理登录态的专用用户数据目录")
    parser.add_argument("--refresh-summaries", action="store_true", help="为队列中缺少 AI 总结的已有视频补采")
    args = parser.parse_args()
    CACHE.mkdir(parents=True, exist_ok=True)
    cookie_file = args.cookies
    if args.cookies_from_browser:
        cookie_file = export_browser_cookies(args.cookies_from_browser, CACHE / "session.cookies.txt")
    opener = cookie_opener(cookie_file) if cookie_file else None
    chrome_session = ChromeSession(args.chrome_profile) if args.chrome_profile else None
    existing = load_existing()
    requested_limit = args.limit if args.limit else (max(args.batch_size + len(existing), args.batch_size) if args.batch_size else 0)
    entries = list_videos(requested_limit, chrome_session)
    rows = dict(existing)
    added = 0
    try:
        for index, entry in enumerate(entries, 1):
            bvid = entry.get("id", "")
            existing_row = rows.get(bvid)
            needs_summary = args.refresh_summaries and existing_row and not existing_row.get("summary_status")
            if not bvid or (existing_row and not needs_summary):
                continue
            if args.batch_size and added >= args.batch_size:
                break
            url = entry.get("url") or f"https://www.bilibili.com/video/{bvid}"
            info, error = video_metadata(bvid, url, args.cookies_from_browser, chrome_session)
            if info:
                try:
                    conclusion, summary_status = video_conclusion(info, opener, chrome_session)
                except Exception as exc:
                    conclusion, summary_status = None, f"request_failed: {exc}"
                model = (conclusion or {}).get("model_result") or {}
                rows[bvid] = {
                    "bvid": bvid,
                    "title": info.get("title", ""),
                    "published_at": iso_date(info),
                    "video_url": info.get("webpage_url") or url,
                    "description": (info.get("description") or "").replace("\r", " ").replace("\n", " | "),
                    "ai_summary": model.get("summary") or "",
                    "ai_outline": outline_text(conclusion),
                    "summary_status": summary_status,
                    "status": (existing_row or {}).get("status") or "待筛选",
                    "notes": (existing_row or {}).get("notes") or "",
                }
                (CACHE / f"{bvid}.json").write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
                if conclusion is not None:
                    (CACHE / f"{bvid}.conclusion.json").write_text(
                        json.dumps(conclusion, ensure_ascii=False, indent=2), encoding="utf-8"
                    )
            else:
                rows[bvid] = {field: "" for field in FIELDS}
                rows[bvid].update({"bvid": bvid, "video_url": url, "status": "元数据受限", "notes": error})
            added += 1
            print(f"[{index}/{len(entries)}] {bvid}: {rows[bvid]['status']} | {rows[bvid].get('summary_status', '')}")
            write_queue(rows)
    finally:
        if chrome_session:
            chrome_session.close()
    write_queue(rows)
    print(f"已写入 {QUEUE}，共 {len(rows)} 条")

if __name__ == "__main__":
    main()
