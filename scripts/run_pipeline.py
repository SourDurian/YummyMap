#!/usr/bin/env python3
"""Run the unattended collection-to-site pipeline."""
import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def run(script, *args, optional=False):
    command = [sys.executable, str(ROOT / "scripts" / script), *args]
    print("+", " ".join(command))
    result = subprocess.run(command, cwd=ROOT)
    if result.returncode and not optional:
        raise SystemExit(result.returncode)
    return result.returncode

def main():
    parser = argparse.ArgumentParser(description="Collect summaries, extract restaurants, geocode, validate, and build")
    session = parser.add_mutually_exclusive_group(required=True)
    session.add_argument("--cookies", type=Path, help="Netscape-format Bilibili cookie file")
    session.add_argument("--chrome-profile", type=Path, help="Dedicated Chrome user-data directory")
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--skip-geocode", action="store_true")
    parser.add_argument("--heuristic", action="store_true", help="Extract conservatively without an LLM service")
    args = parser.parse_args()
    session_args = ["--cookies", str(args.cookies)] if args.cookies else ["--chrome-profile", str(args.chrome_profile)]
    run("collect_bilibili.py", *session_args, "--batch-size", str(args.batch_size), "--refresh-summaries")
    run("extract_restaurants.py", *(["--heuristic"] if args.heuristic else []))
    if not args.skip_geocode and os.environ.get("AMAP_WEB_SERVICE_KEY"):
        run("geocode_restaurants.py")
    run("validate_data.py")
    run("export_data.py")
    run("build_site.py")

if __name__ == "__main__":
    main()
