#!/usr/bin/env python3
"""Fill missing restaurant coordinates with the AMap Web Service API."""
import json
import os
import sys
import urllib.parse
import urllib.request
import time
from datetime import date
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = ROOT / "data" / "restaurants.json"
API_URL = "https://restapi.amap.com/v3/geocode/geo"
PLACE_URL = "https://restapi.amap.com/v3/place/text"
CHINA_BOUNDS = (73.0, 18.0, 135.5, 54.0)
MANUAL_LOCATIONS = {
    "应城烧菜馆(清芬小区店)": (114.281810, 30.572944, "高德POI名称变体"),
    "烔記TUNGKEE古法粤菜": (114.334325, 30.558825, "高德POI名称变体"),
    "梧桐美式烤肉Phoenix bistro(东湖店)": (114.413882, 30.541434, "高德POI"),
    "遵义豆豉火锅（财大店）": (114.384688, 30.477315, "高德POI名称变体"),
    "韩味屋": (114.402875, 30.526393, "高德POI名称变体"),
    "酝满厨": (114.407699, 30.525585, "高德社区级近似位置"),
    "无名炸炸": (114.245868, 30.575006, "高德POI名称变体"),
}

def api_get(url, params, retries=4):
    query = urllib.parse.urlencode(params)
    request = urllib.request.Request(f"{url}?{query}", headers={"User-Agent": "YummyMap/1.0"})
    for attempt in range(retries + 1):
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)
        if payload.get("infocode") != "10021" or attempt == retries:
            time.sleep(0.25)
            return payload
        time.sleep(1.0 * (attempt + 1))

def parse_location(value):
    try:
        longitude, latitude = (float(part) for part in value.split(","))
    except (AttributeError, TypeError, ValueError):
        return None
    west, south, east, north = CHINA_BOUNDS
    if not (west <= longitude <= east and south <= latitude <= north):
        return None
    return longitude, latitude

def district_matches(expected, actual):
    if not expected or not actual:
        return True
    if expected.endswith("市"):
        return True
    if expected in actual or actual in expected:
        return True
    return expected == "洪山区" and actual in {"东湖高新区", "武汉东湖新技术开发区"}

def city_from_address(address):
    match = __import__("re").search(r"([^省市区县]{2,8}市)", address or "")
    if match:
        return match.group(1)
    hints = {
        "湘桥区": "潮州市", "梁溪区": "无锡市", "东宝区": "荆门市",
        "潜江市": "潜江市", "宜兴": "无锡市", "兰州": "兰州市",
    }
    for token, city in hints.items():
        if token in (address or ""):
            return city
    if any(name in (address or "") for name in ("江岸区", "江汉区", "硚口区", "汉阳区", "武昌区", "青山区", "洪山区", "江夏区", "黄陂区", "东西湖区", "蔡甸区", "新洲区")):
        return "武汉市"
    return "武汉市"

def search_place(item, key):
    keywords = f"{item['name']} {item.get('branch', '')}".strip()
    city = city_from_address(item.get("address", ""))
    params = {"key": key, "keywords": keywords, "citylimit": "true" if city else "false", "offset": 10, "page": 1, "extensions": "base"}
    if city:
        params["city"] = city
    payload = api_get(PLACE_URL, params)
    if payload.get("status") != "1":
        raise RuntimeError(f"高德接口错误 {payload.get('infocode')}: {payload.get('info')}")
    for poi in payload.get("pois") or []:
        location = parse_location(poi.get("location"))
        if location and district_matches(item.get("district"), poi.get("adname", "")):
            return (*location, f"{poi.get('adname', '')}{poi.get('address', '')}", "POI")
    return None

def geocode_address(item, key):
    address = item["address"]
    city = city_from_address(address)
    variants = [address, f"{city}{item.get('district', '')}{item['name']}{item.get('branch', '')}"]
    for candidate in variants:
        params = {"key": key, "address": candidate, "output": "JSON"}
        if city:
            params["city"] = city
        payload = api_get(API_URL, params)
        if payload.get("status") != "1":
            print(f"地址解析跳过: {item['name']} | {payload.get('infocode')} {payload.get('info')}", file=sys.stderr)
            continue
        for result in payload.get("geocodes") or []:
            if result.get("level") in {"国家", "省", "市", "区县"}:
                continue
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
        if (item.get("longitude"), item.get("latitude")) == (114.304569, 30.593354):
            item["longitude"] = None
            item["latitude"] = None
        if item.get("address") == "安居路" and isinstance(item.get("longitude"), (int, float)):
            item["longitude"] = None
            item["latitude"] = None
        if isinstance(item.get("longitude"), (int, float)) and isinstance(item.get("latitude"), (int, float)):
            continue
        if item.get("name") in MANUAL_LOCATIONS:
            longitude, latitude, method = MANUAL_LOCATIONS[item["name"]]
            item["longitude"] = longitude
            item["latitude"] = latitude
            item["verificationStatus"] = f"{item.get('verificationStatus', '').rstrip('；;')}；{method}"
            item["updatedAt"] = date.today().isoformat()
            payload["generatedAt"] = date.today().isoformat()
            DATA_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            changed += 1
            print(f"已定位: {item['name']} -> {longitude},{latitude} | {method}")
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
        payload["generatedAt"] = date.today().isoformat()
        DATA_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"已定位: {item['name']} -> {longitude},{latitude} | {method} | {formatted}")
    print(f"更新 {changed} 家餐厅")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
