#!/usr/bin/env python3
"""Fill missing restaurant coordinates with the AMap Web Service API."""
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = ROOT / "data" / "restaurants.json"
API_URL = "https://restapi.amap.com/v3/geocode/geo"
PLACE_URL = "https://restapi.amap.com/v3/place/text"
WUHAN_BOUNDS = (113.6, 29.9, 115.1, 31.4)

def api_get(url, params):
    query = urllib.parse.urlencode(params)
    request = urllib.request.Request(f"{url}?{query}", headers={"User-Agent": "YummyMap/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)

def parse_location(value):
    try:
        longitude, latitude = (float(part) for part in value.split(","))
    except (AttributeError, TypeError, ValueError):
        return None
    west, south, east, north = WUHAN_BOUNDS
    if not (west <= longitude <= east and south <= latitude <= north):
        return None
    return longitude, latitude

def district_matches(expected, actual):
    if not expected or not actual:
        return True
    if expected in actual or actual in expected:
        return True
    return expected == "洪山区" and actual in {"东湖高新区", "武汉东湖新技术开发区"}

def search_place(item, key):
    keywords = f"{item['name']} {item.get('branch', '')}".strip()
    payload = api_get(PLACE_URL, {"key": key, "keywords": keywords, "city": "武汉", "citylimit": "true", "offset": 10, "page": 1, "extensions": "base"})
    if payload.get("status") != "1":
        raise RuntimeError(f"高德接口错误 {payload.get('infocode')}: {payload.get('info')}")
    for poi in payload.get("pois") or []:
        location = parse_location(poi.get("location"))
        if location and district_matches(item.get("district"), poi.get("adname", "")):
            return (*location, f"{poi.get('adname', '')}{poi.get('address', '')}", "POI")
    return None

def geocode_address(item, key):
    address = item["address"]
    variants = [
        f"武汉市{item.get('district', '')}{address.removeprefix('武汉市')}",
        f"武汉市{item.get('district', '')}{item['name']}{item.get('branch', '')}",
    ]
    for candidate in variants:
        payload = api_get(API_URL, {"key": key, "address": candidate, "city": "武汉", "output": "JSON"})
        if payload.get("status") != "1":
            print(f"地址解析跳过: {item['name']} | {payload.get('infocode')} {payload.get('info')}", file=sys.stderr)
            continue
        for result in payload.get("geocodes") or []:
            location = parse_location(result.get("location"))
            component = result.get("district", "")
            if location and district_matches(item.get("district"), component):
                return (*location, result.get("formatted_address", ""), "地址")
    return None

def main():
    key = os.environ.get("AMAP_WEB_SERVICE_KEY", "").strip()
    if not key:
        print("缺少 AMAP_WEB_SERVICE_KEY", file=sys.stderr)
        return 2
    payload = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    changed = 0
    for item in payload.get("restaurants", []):
        if isinstance(item.get("longitude"), (int, float)) and isinstance(item.get("latitude"), (int, float)):
            continue
        try:
            result = search_place(item, key) or geocode_address(item, key)
        except Exception as exc:
            print(f"定位失败: {item['name']} | {exc}", file=sys.stderr)
            continue
        if not result:
            print(f"未找到坐标: {item['name']} | {item['address']}", file=sys.stderr)
            continue
        longitude, latitude, formatted, method = result
        item["longitude"] = longitude
        item["latitude"] = latitude
        item["updatedAt"] = date.today().isoformat()
        changed += 1
        print(f"已定位: {item['name']} -> {longitude},{latitude} | {method} | {formatted}")
    if changed:
        payload["generatedAt"] = date.today().isoformat()
        DATA_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"更新 {changed} 家餐厅")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
