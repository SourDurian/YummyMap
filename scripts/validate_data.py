#!/usr/bin/env python3
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = {"id", "name", "address", "videoUrl", "verificationStatus"}
RATINGS = {"recommended", "mixed", "not_recommended", "unknown"}

def main():
    payload = json.loads((ROOT / "data" / "restaurants.json").read_text(encoding="utf-8"))
    rows = payload if isinstance(payload, list) else payload.get("restaurants", [])
    errors, ids = [], set()
    for index, item in enumerate(rows, 1):
        missing = sorted(key for key in REQUIRED if not item.get(key))
        if missing: errors.append(f"#{index} 缺少字段: {', '.join(missing)}")
        if item.get("id") in ids: errors.append(f"#{index} ID 重复: {item.get('id')}")
        ids.add(item.get("id"))
        if item.get("rating", "unknown") not in RATINGS: errors.append(f"#{index} rating 无效")
        for key in ("longitude", "latitude"):
            value = item.get(key)
            if value is not None and not isinstance(value, (int, float)): errors.append(f"#{index} {key} 必须是数字或 null")
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"Validated {len(rows)} restaurants")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
