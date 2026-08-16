#!/usr/bin/env python3
"""
Threads Post Scheduler (debug-friendly version)
--------------------------------------------------
Reads scheduled posts from posts.csv and publishes any that are due
to your Threads account using the official Threads Graph API.

This version ALWAYS writes scheduler.log, from the very first line of
execution, even if something crashes immediately. If you run this and
still see no log file, something is preventing Python from writing to
this folder at all (permissions) — tell me what error appears.

Setup:
    1. Copy .env.example to .env and fill in your credentials.
    2. pip install -r requirements.txt
    3. Add rows to posts.csv
    4. Run manually to test:  python3 threads_scheduler.py
    5. Add to cron / Task Scheduler for real automation.
"""

import sys
import os
import csv
import time
import traceback
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Fixed offset for India Standard Time (UTC+5:30). Calculated explicitly
# instead of relying on the server's TZ environment variable, since that
# isn't reliably respected across different runners (e.g. GitHub Actions).
IST = timezone(timedelta(hours=5, minutes=30))

BASE_DIR = Path(__file__).resolve().parent
CSV_PATH = BASE_DIR / "posts.csv"
LOG_PATH = BASE_DIR / "scheduler.log"
GRAPH_API_VERSION = "v1.0"  # Threads API uses its own versioning, NOT the v21.0-style Graph API versions


# ---- Logging (write immediately, flush every line, never buffer) --------

def log(message: str):
    timestamp = datetime.now(timezone.utc).astimezone(IST).strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    print(line, flush=True)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
            f.flush()
    except Exception as e:
        # If we can't even write the log file, at least this prints
        print(f"!! Could not write to log file: {e}", flush=True)


# Write the very first log line before anything else runs, so we know
# the script started at all.
log(f"Script started. Working directory: {BASE_DIR}")

try:
    import requests
except ImportError:
    log("ERROR: the 'requests' library is not installed.")
    log("Run: pip install -r requirements.txt")
    sys.exit(1)


# ---- Load .env -----------------------------------------------------------

def load_env():
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        log(f"WARNING: .env file not found at {env_path}")
        return
    log(f".env file found at {env_path}, loading...")
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())

load_env()

THREADS_USER_ID = os.environ.get("THREADS_USER_ID", "").strip()
THREADS_ACCESS_TOKEN = os.environ.get("THREADS_ACCESS_TOKEN", "").strip()

log(f"THREADS_USER_ID loaded: {'YES' if THREADS_USER_ID else 'NO (missing!)'}")
log(f"THREADS_ACCESS_TOKEN loaded: {'YES (' + str(len(THREADS_ACCESS_TOKEN)) + ' chars)' if THREADS_ACCESS_TOKEN else 'NO (missing!)'}")

if not THREADS_USER_ID or not THREADS_ACCESS_TOKEN:
    log("ERROR: Missing THREADS_USER_ID or THREADS_ACCESS_TOKEN.")
    log("Check that your .env file has both filled in with real values (no quotes needed).")
    sys.exit(1)


# ---- Threads API ---------------------------------------------------------

def publish_to_threads(text: str, image_url: str = ""):
    try:
        create_url = f"https://graph.threads.net/{GRAPH_API_VERSION}/{THREADS_USER_ID}/threads"
        params = {"access_token": THREADS_ACCESS_TOKEN, "text": text}
        if image_url:
            params["media_type"] = "IMAGE"
            params["image_url"] = image_url
        else:
            params["media_type"] = "TEXT"

        log(f"Creating post container...")
        create_resp = requests.post(create_url, data=params, timeout=30)
        log(f"Create response status: {create_resp.status_code}")
        log(f"Create response body: {create_resp.text[:500]}")
        create_resp.raise_for_status()
        creation_id = create_resp.json().get("id")
        if not creation_id:
            return False, f"No creation id returned: {create_resp.text}"

        time.sleep(5)

        publish_url = f"https://graph.threads.net/{GRAPH_API_VERSION}/{THREADS_USER_ID}/threads_publish"
        publish_resp = requests.post(
            publish_url,
            data={"access_token": THREADS_ACCESS_TOKEN, "creation_id": creation_id},
            timeout=30,
        )
        log(f"Publish response status: {publish_resp.status_code}")
        log(f"Publish response body: {publish_resp.text[:500]}")
        publish_resp.raise_for_status()
        return True, publish_resp.json().get("id", "posted")

    except requests.exceptions.RequestException as e:
        detail = e.response.text if e.response is not None else ""
        return False, f"{e} {detail}"


# ---- CSV handling --------------------------------------------------------

FIELDNAMES = ["id", "text", "image_url", "scheduled_time", "status", "posted_at", "note"]


def read_rows():
    if not CSV_PATH.exists():
        log(f"ERROR: {CSV_PATH} not found.")
        sys.exit(1)
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    log(f"Loaded {len(rows)} row(s) from posts.csv")
    return rows


def write_rows(rows):
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    log("posts.csv updated.")


def parse_time(value: str) -> datetime:
    return datetime.strptime(value.strip(), "%Y-%m-%d %H:%M")


# ---- Main ------------------------------------------------------------

def main():
    rows = read_rows()
    # Always compute the current time in IST explicitly, regardless of
    # what timezone the machine running this script is actually set to.
    now = datetime.now(timezone.utc).astimezone(IST).replace(tzinfo=None)
    log(f"Current time: {now.strftime('%Y-%m-%d %H:%M')}")
    changed = False

    due = [r for r in rows if r.get("status", "").strip().lower() == "pending"]
    log(f"Found {len(due)} row(s) with status 'pending'")

    if not due:
        log("No pending posts in queue. Nothing to do.")

    for row in due:
        try:
            scheduled = parse_time(row["scheduled_time"])
        except (ValueError, KeyError) as e:
            log(f"Row id={row.get('id')} has an invalid scheduled_time ('{row.get('scheduled_time')}') — skipping. ({e})")
            continue

        log(f"Row id={row.get('id')}: scheduled={scheduled}, now={now}, due={scheduled <= now}")

        if scheduled > now:
            continue

        text = row.get("text", "").strip()
        image_url = row.get("image_url", "").strip()

        if not text and not image_url:
            row["status"] = "error"
            row["note"] = "Empty post"
            changed = True
            continue

        log(f"Posting id={row.get('id')} scheduled for {row['scheduled_time']} ...")
        success, info = publish_to_threads(text, image_url)

        if success:
            row["status"] = "posted"
            row["posted_at"] = now.strftime("%Y-%m-%d %H:%M:%S")
            row["note"] = f"OK ({info})"
            log(f"  -> SUCCESS (post id: {info})")
        else:
            row["status"] = "error"
            row["note"] = str(info)[:300]
            log(f"  -> FAILED: {info}")

        changed = True

    if changed:
        write_rows(rows)
    else:
        log("No changes made to posts.csv this run.")

    log("Script finished normally.")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log("!!! SCRIPT CRASHED WITH AN UNEXPECTED ERROR !!!")
        log(traceback.format_exc())
        sys.exit(1)