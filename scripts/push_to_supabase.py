#!/usr/bin/env python3
"""
Reads the last few days of data out of GarminDB's local SQLite databases
and upserts them into the `garmin_daily_metrics` table in Supabase.

GarminDB stores data in a few separate SQLite files under ~/HealthData/DBs:
  - garmin_monitoring.db  -> daily steps (in the 'steps' table, summed per day)
  - garmin_summary.db     -> daily summary incl. resting HR, body battery
  - garmin.db             -> sleep, weight

We read a rolling window (last 5 days) rather than just "today", since
Garmin sometimes finalises yesterday's totals late, and a failed run on
one day shouldn't leave a permanent gap.
"""

import os
import sqlite3
import requests
from datetime import date, timedelta
from pathlib import Path

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "resolution=merge-duplicates",
}

DB_DIR = Path.home() / "HealthData" / "DBs"
WINDOW_DAYS = 5  # how many recent days to (re-)sync each run


def open_db(name):
    path = DB_DIR / name
    if not path.exists():
        print(f"  (missing: {path}, skipping)")
        return None
    return sqlite3.connect(str(path))


def get_steps(conn, day):
    if conn is None:
        return None
    try:
        cur = conn.execute(
            "SELECT SUM(steps) FROM steps_activities WHERE day = ?", (day.isoformat(),)
        )
        row = cur.fetchone()
        return row[0] if row else None
    except sqlite3.OperationalError:
        # Schema can vary slightly between GarminDB versions; try the
        # daily summary table as a fallback.
        try:
            cur = conn.execute(
                "SELECT steps FROM daily_summary WHERE day = ?", (day.isoformat(),)
            )
            row = cur.fetchone()
            return row[0] if row else None
        except sqlite3.OperationalError:
            return None


def get_daily_summary(conn, day):
    if conn is None:
        return {}
    try:
        cur = conn.execute(
            """SELECT rhr, hrv_avg, bb_max, bb_min, total_sleep, weight
               FROM daily_summary WHERE day = ?""",
            (day.isoformat(),),
        )
        row = cur.fetchone()
        if not row:
            return {}
        return {
            "resting_hr": row[0],
            "hrv_avg": row[1],
            "body_battery_max": row[2],
            "body_battery_min": row[3],
            "sleep_secs": row[4],
            "weight_kg": row[5],
        }
    except sqlite3.OperationalError as e:
        print(f"  (daily_summary query failed: {e})")
        return {}


def main():
    monitoring_conn = open_db("garmin_monitoring.db")
    summary_conn = open_db("garmin_summary.db")

    today = date.today()
    synced = 0

    for offset in range(WINDOW_DAYS):
        day = today - timedelta(days=offset)
        record = {"metric_date": day.isoformat()}

        steps = get_steps(monitoring_conn, day)
        if steps:
            record["steps"] = int(steps)

        record.update(get_daily_summary(summary_conn, day))

        # Skip days where we genuinely got nothing -- no point writing an
        # empty row that just clutters the table.
        if len(record) <= 1:
            continue

        resp = requests.post(
            f"{SUPABASE_URL}/rest/v1/garmin_daily_metrics?on_conflict=metric_date",
            headers=HEADERS,
            json=record,
        )
        if resp.ok:
            print(f"  Synced {day.isoformat()}: {record}")
            synced += 1
        else:
            print(f"  FAILED {day.isoformat()}: {resp.status_code} {resp.text}")

    print(f"Done. Synced {synced}/{WINDOW_DAYS} days.")


if __name__ == "__main__":
    main()
