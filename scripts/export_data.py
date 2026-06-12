#!/usr/bin/env python3
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

def main():
    payload = json.loads((DATA / "restaurants.json").read_text(encoding="utf-8"))
    restaurants = payload if isinstance(payload, list) else payload.get("restaurants", [])
    fields = ["id", "name", "branch", "address", "district", "cuisine", "pricePerPerson", "rating", "review", "recommendedDishes", "visitDate", "videoUrl", "longitude", "latitude", "verificationStatus", "updatedAt"]
    with (DATA / "restaurants.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for item in restaurants:
            writer.writerow({**item, "recommendedDishes": "、".join(item.get("recommendedDishes", []))})
    features = []
    for item in restaurants:
        lon, lat = item.get("longitude"), item.get("latitude")
        if isinstance(lon, (int, float)) and isinstance(lat, (int, float)):
            features.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]}, "properties": {key: value for key, value in item.items() if key not in ("longitude", "latitude")}})
    (DATA / "restaurants.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Exported {len(restaurants)} restaurants")

if __name__ == "__main__":
    main()
