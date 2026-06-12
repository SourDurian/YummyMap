#!/usr/bin/env python3
import json
import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"

def main():
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir()
    for name in ("index.html", "assets", "data"):
        source = ROOT / name
        target = DIST / name
        shutil.copytree(source, target) if source.is_dir() else shutil.copy2(source, target)
    config = {
        "amapKey": os.environ.get("AMAP_JS_KEY", ""),
        "amapSecurityCode": os.environ.get("AMAP_SECURITY_CODE", ""),
    }
    (DIST / "config.js").write_text(
        "window.YUMMYMAP_CONFIG = " + json.dumps(config, ensure_ascii=True) + ";\n",
        encoding="utf-8",
    )
    print(f"Built {DIST}")

if __name__ == "__main__":
    main()
