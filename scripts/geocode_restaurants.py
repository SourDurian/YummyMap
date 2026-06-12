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
WUHAN_BOUNDS = (113.6, 29.9, 115.1, 31.4)

def geocode(address, key):
    query = urllib.parse.urlencode({"key": key, "address": address, "city": "武汉", "output": "JSON"})
    request = urllib.request.Request(f"{API_URL}?{query}", headers={"User-Agent": "YummyMap/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)
    if payload.get("status") != "1":
        raise RuntimeError(f"高德接口错误 {payload.get('infocode')}: {payload.get('info')}")
    results = payload.get("geocodes") or []
    if not results:
        return None
    result = results[0]
    try:
        longitude, latitude = (float(value) for value in result["location"].split(","))
    except (KeyError, TypeError, ValueError):
        return None
    west, south, east, north = WUHAN_BOUNDS
    if not (west <= longitude <= east and south <= latitude <= north):
        raise RuntimeError(f"地址解析结果不在武汉范围内: {address} -> {longitude},{latitude}")
    return longitude, latitude, result.get("formatted_address", "")

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
        result = geocode(item["address"], key)
        if not result:
            print(f"未找到坐标: {item['name']} | {item['address']}", file=sys.stderr)
            continue
        longitude, latitude, formatted = result
        item["longitude"] = longitude
        item["latitude"] = latitude
        item["updatedAt"] = date.today().isoformat()
        changed += 1
        print(f"已定位: {item['name']} -> {longitude},{latitude} | {formatted}")
    if changed:
        payload["generatedAt"] = date.today().isoformat()
        DATA_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"更新 {changed} 家餐厅")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
