#!/usr/bin/env python3
"""
sync.py — pull the Henzi timeline spreadsheet and media into the repo.

Run:  python3 sync.py
Out:  data/timeline.json, data/images/*
"""

import csv
import hashlib
import io
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

SHEET_CSV_URL = (
    "https://docs.google.com/spreadsheets/d/e/"
    "2PACX-1vRaedjQigM9N4NU_disbqY0EttiGWCP8SXagsU9fp9UolCIDCPvKiAw3BWTuarVdp69eNABESDjDNss"
    "/pub?output=csv&gid=401812079"
)

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
IMG_DIR = DATA_DIR / "images"
OUT_JSON = DATA_DIR / "timeline.json"


def fetch(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "henzi-sync/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def gdrive_direct(url: str) -> str:
    """Convert a Google Drive share link to a direct download URL."""
    m = re.search(r"/file/d/([^/?]+)", url)
    if m:
        return f"https://drive.google.com/uc?export=download&id={m.group(1)}"
    return url


def image_filename(url: str) -> str:
    h = hashlib.md5(url.encode()).hexdigest()[:8]
    path = urllib.parse.urlparse(url).path
    ext = (path.rsplit(".", 1)[-1].lower() if "." in path.split("/")[-1] else "jpg")
    ext = re.sub(r"[^\w]", "", ext)[:5] or "jpg"
    stem = re.sub(r"[^\w\-]", "_", path.split("/")[-1].rsplit(".", 1)[0])[:40]
    return f"{stem}_{h}.{ext}"


def download_image(url: str) -> str | None:
    if not url or not url.startswith("http"):
        return None
    fetch_url = gdrive_direct(url)
    filename = image_filename(url)
    dest = IMG_DIR / filename
    web_path = f"data/images/{filename}"
    if dest.exists():
        print(f"  cached  {filename}")
        return web_path
    try:
        data = fetch(fetch_url, timeout=20)
        # Google Drive sometimes returns an HTML confirmation page for large files.
        # Detect it and skip rather than saving garbage HTML as an image.
        if data[:15].lstrip().startswith(b"<!"):
            print(f"  WARN    {url}: got HTML (Drive confirmation page?)", file=sys.stderr)
            return None
        dest.write_bytes(data)
        print(f"  saved   {filename}  ({len(data):,} bytes)")
        return web_path
    except Exception as e:
        print(f"  WARN    {url}: {e}", file=sys.stderr)
        return None


def parse_date(year="", month="", day="", time="") -> dict | None:
    d = {k: v.strip() for k, v in
         [("year", year), ("month", month), ("day", day), ("time", time)] if v.strip()}
    return d or None


def row_to_event(row: dict) -> dict | None:
    year = row.get("Year", "").strip()
    if not year:
        return None

    event: dict = {}

    start = parse_date(year, row.get("Month", ""), row.get("Day", ""), row.get("Time", ""))
    if start:
        event["start_date"] = start

    end = parse_date(
        row.get("End Year", ""), row.get("End Month", ""),
        row.get("End Day", ""), row.get("End Time", ""),
    )
    if end:
        event["end_date"] = end

    headline = row.get("Headline", "").strip()
    text_body = row.get("Text", "").strip()
    if headline or text_body:
        event["text"] = {k: v for k, v in
                         [("headline", headline), ("text", text_body)] if v}

    display_date = row.get("Display Date", "").strip()
    if display_date:
        event["display_date"] = display_date

    media_url = row.get("Media", "").strip()
    if media_url:
        local = download_image(media_url)
        media: dict = {"url": local or media_url}
        for field, key in [
            ("Media Caption", "caption"),
            ("Media Credit", "credit"),
            ("Media Thumbnail", "thumbnail"),
        ]:
            val = row.get(field, "").strip()
            if val:
                media[key] = val
        event["media"] = media

    row_type = row.get("Type", "").strip().lower()
    if row_type:
        event["type"] = row_type

    group = row.get("Group", "").strip()
    if group:
        event["group"] = group

    bg = row.get("Background", "").strip()
    if bg:
        local_bg = download_image(bg)
        event["background"] = {"url": local_bg or bg}

    return event


def main():
    IMG_DIR.mkdir(parents=True, exist_ok=True)

    print("Fetching spreadsheet …")
    raw = fetch(SHEET_CSV_URL)
    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8"))))
    print(f"  {len(rows)} rows")

    title_event = None
    events = []
    for row in rows:
        ev = row_to_event(row)
        if ev is None:
            continue
        if ev.get("type") == "title":
            title_event = ev
        else:
            events.append(ev)

    timeline = {"events": events}
    if title_event:
        timeline["title"] = title_event

    OUT_JSON.write_text(json.dumps(timeline, indent=2, ensure_ascii=False))
    print(f"\nWrote {OUT_JSON}  ({len(events)} events)")


if __name__ == "__main__":
    main()
