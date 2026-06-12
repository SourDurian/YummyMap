#!/usr/bin/env python3
"""Convert collected Bilibili summaries into restaurant records with an LLM."""
import csv
import argparse
import json
import os
import re
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUEUE = ROOT / "data" / "review_queue.csv"
DATA_FILE = ROOT / "data" / "restaurants.json"

SYSTEM_PROMPT = """You extract Wuhan restaurant visits from Chinese video summaries.
Return JSON only: an array of objects with keys name, branch, address, district,
cuisine, pricePerPerson, rating, review, recommendedDishes. rating must be one of
recommended, mixed, not_recommended, unknown. Use null or empty values when the
source does not state a fact. Never invent addresses, prices, dishes, or opinions.
Return [] when the video is not a Wuhan restaurant visit."""

DISTRICTS = "江岸区|江汉区|硚口区|汉阳区|武昌区|青山区|洪山区|东西湖区|汉南区|蔡甸区|江夏区|黄陂区|新洲区"
CUISINES = [
    ("川菜", "川菜"), ("火锅", "火锅"), ("烤肉", "烤肉"), ("烧烤", "烧烤"),
    ("江西", "江西菜"), ("南洋", "南洋菜"), ("猪排", "日式简餐"),
    ("和牛", "日式烤肉"), ("潮汕牛肉", "潮汕火锅"), ("炒面", "武汉小吃"),
    ("面线糊", "闽南小吃"), ("海鲜", "海鲜"), ("新疆", "新疆菜"),
    ("烧腊", "粤式烧腊"), ("馄饨", "中式小吃"), ("西餐", "西餐"),
]

def clean_segment(value):
    return re.sub(r"^\s*\d+\s*[：:、，,.]\s*", "", value).strip(" -；;")

def looks_like_address(value):
    return len(value) >= 3 and bool(re.search(r"省|市|区|县|镇|乡|街道|街|路|巷|弄|号|商铺|门面|广场|大厦|小区|社区|地铁站", value))

def normalize_address(address, title):
    aliases = {"江岸": "江岸区", "江汉": "江汉区", "硚口": "硚口区", "汉阳": "汉阳区", "武昌": "武昌区", "青山": "青山区", "洪山": "洪山区", "江夏": "江夏区", "黄陂": "黄陂区"}
    for short, full in aliases.items():
        if address.startswith(short) and not address.startswith(full):
            address = full + address[len(short):]
            break
    if "武汉" in title and not re.search(r"^[^省]{2,8}省|^[^市]{2,8}市", address):
        address = "武汉市" + address
    return address

def address_region(address):
    city = re.search(r"([^省市区县]{2,8}市)", address)
    district = re.search(r"([^省市区县]{1,8}(?:区|县))", address)
    return (district.group(1) if district else city.group(1) if city else "")

def split_places(description, title):
    places = []
    raws = []
    for block in re.split(r"\s*\|\s*|[\r\n]+", description):
        raws.extend(re.split(r"[，,](?=[^，,：:]{1,30}[：:])", block))
    for raw in raws:
        segment = clean_segment(raw)
        if not segment:
            continue
        pair = re.split(r"[：:]", segment, maxsplit=1)
        if len(pair) != 2:
            continue
        left, right = (part.strip() for part in pair)
        if looks_like_address(left) and 1 < len(right) <= 80:
            address, name = left, right
        elif looks_like_address(right) and 1 < len(left) <= 80:
            address, name = right, left
        else:
            continue
        address = normalize_address(address, title)
        name = re.sub(r"[（(]?我复制的[）)]?", "", name)
        name = re.sub(r"\s*#.*$", "", name).strip()
        if name in {"导航至", "地址", "地址导航", "导航", "店名"}:
            continue
        if name and address and not re.search(r"[：:]", name + address):
            places.append((name, address, address_region(address)))
    return places

def heuristic_extract(row):
    description = (row.get("description") or "").strip()
    title = row.get("title") or ""
    places = split_places(description, title)
    if not places:
        return []
    source = f"{row.get('title', '')} {row.get('ai_summary', '')}"
    cuisine = next((value for keyword, value in CUISINES if keyword in source), "其他")
    per_person = re.search(r"人均(?:消费)?\s*(\d+)\s*元", source)
    summary = row.get("ai_summary") or ""
    negative = any(word in summary for word in ("一般", "稍硬", "需提升", "需改进", "待优化", "问题", "谨慎"))
    positive = any(word in summary for word in ("推荐", "值得", "好评", "突出", "超出预期"))
    rating = "mixed" if negative else "recommended" if positive else "unknown"
    dishes = []
    recommendation = re.search(r"(?:重点推荐|推荐)([^。；]+)", summary)
    if recommendation:
        dishes = [
            re.sub(r"（.*?）|\(.*?\)|等.*$|的.*$", "", part).strip(" 、，及")
            for part in re.split(r"[、，及]", recommendation.group(1))
        ]
        dishes = [dish for dish in dishes if 1 < len(dish) <= 18][:8]
    review = summary or f"视频《{title}》中提及该店；B站未提供AI摘要，具体评价待整理。"
    return [{
        "name": name,
        "branch": "",
        "address": address,
        "district": district,
        "cuisine": cuisine,
        "pricePerPerson": int(per_person.group(1)) if per_person else None,
        "rating": rating,
        "review": review,
        "recommendedDishes": dishes,
    } for name, address, district in places]

def signature(item):
    compact = lambda value: re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]", "", value or "").lower()
    return compact(item.get("name")), compact(item.get("address"))

def call_llm(text):
    url = os.environ.get("LLM_API_URL", "http://localhost:11434/v1/chat/completions")
    model = os.environ.get("LLM_MODEL", "qwen2.5:7b")
    key = os.environ.get("LLM_API_KEY", "").strip()
    body = json.dumps({
        "model": model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
    }).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=180) as response:
        payload = json.load(response)
    content = payload["choices"][0]["message"]["content"].strip()
    content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content, flags=re.I)
    result = json.loads(content)
    if not isinstance(result, list):
        raise ValueError("LLM response must be a JSON array")
    return result

def record_id(bvid, index):
    return f"{bvid.lower()}-{index + 1}"

def main():
    parser = argparse.ArgumentParser(description="Extract restaurant records from the review queue")
    parser.add_argument("--heuristic", action="store_true", help="Use conservative description/summary rules without an LLM")
    args = parser.parse_args()
    if not QUEUE.exists():
        raise RuntimeError("Run collect_bilibili.py first")
    payload = json.loads(DATA_FILE.read_text(encoding="utf-8")) if DATA_FILE.exists() else {"restaurants": []}
    invalid_names = {"导航至", "地址", "地址导航", "导航", "店名"}
    restaurants = []
    for item in payload.get("restaurants", []):
        item["name"] = re.sub(r"\s*#.*$", "", item.get("name") or "").strip()
        if item.get("name") in invalid_names or re.search(r"[：:]", item.get("address") or ""):
            continue
        restaurants.append(item)
    deduped, seen_ids = [], set()
    for item in restaurants:
        if item.get("id") in seen_ids:
            continue
        deduped.append(item)
        seen_ids.add(item.get("id"))
    restaurants = deduped
    existing_signatures = {signature(item) for item in restaurants}
    existing_ids = {item.get("id") for item in restaurants}
    added = 0
    with QUEUE.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        if not row.get("ai_summary") and not (args.heuristic and row.get("description")):
            continue
        source = "\n".join([
            f"Title: {row.get('title', '')}",
            f"Published: {row.get('published_at', '')}",
            f"Description: {row.get('description', '')}",
            f"AI summary: {row.get('ai_summary', '')}",
            f"Outline: {row.get('ai_outline', '')}",
        ])
        extracted = heuristic_extract(row) if args.heuristic else call_llm(source)
        for index, item in enumerate(extracted):
            if not item.get("name") or not item.get("address"):
                continue
            candidate_id = record_id(row["bvid"], index)
            item_signature = signature(item)
            if candidate_id in existing_ids or item_signature in existing_signatures:
                continue
            item.update({
                "id": candidate_id,
                "visitDate": row.get("published_at") or None,
                "videoUrl": row["video_url"],
                "longitude": None,
                "latitude": None,
                "verificationStatus": "AI摘要自动提取，待抽查",
                "updatedAt": date.today().isoformat(),
            })
            item.setdefault("branch", "")
            item.setdefault("district", "")
            item.setdefault("cuisine", "")
            item.setdefault("pricePerPerson", None)
            item.setdefault("rating", "unknown")
            item.setdefault("review", "")
            item.setdefault("recommendedDishes", [])
            restaurants.append(item)
            existing_signatures.add(item_signature)
            existing_ids.add(candidate_id)
            added += 1
        print(f"{row['bvid']}: extracted {len(extracted)} candidate(s)")
    payload.update({"generatedAt": date.today().isoformat(), "restaurants": restaurants})
    DATA_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Added {added} restaurant(s)")

if __name__ == "__main__":
    main()
