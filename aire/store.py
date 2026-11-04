import json
import sqlite3
import time
from datetime import date, timedelta
from pathlib import Path

from .connectors import DAY, fixture_page, normalize

ROOT = Path(__file__).resolve().parent.parent


def catalog():
    return json.loads((ROOT / "fixtures/catalog.json").read_text())


def connect(path):
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    db.executescript("""
    CREATE TABLE IF NOT EXISTS samples(
      tenant TEXT, ref TEXT, day TEXT, meter TEXT, env TEXT, start TEXT, end TEXT,
      value TEXT, source_id TEXT, PRIMARY KEY(tenant,ref,meter,env,start));
    CREATE TABLE IF NOT EXISTS checkpoints(
      tenant TEXT, ref TEXT, next_day TEXT, PRIMARY KEY(tenant,ref));
    """)
    return db


def collect(db, tenant, ref, until, fetch=fixture_page, sleep=time.sleep, budget=100, refresh=False):
    spec = catalog()["bindings"][tenant][ref]
    first = date.fromisoformat(spec["first_day"])
    end = date.fromisoformat(until)
    if not first <= end <= date.fromisoformat(spec["end_exclusive"]):
        raise ValueError("outside fixture period")
    # One SQLite writer serializes collectors. Pages, snapshots and cursor commit together.
    with db:
        db.execute("BEGIN IMMEDIATE")
        saved = db.execute("SELECT next_day FROM checkpoints WHERE tenant=? AND ref=?", (tenant, ref)).fetchone()
        cursor_day = date.fromisoformat(saved[0]) if saved else first
        day = max(first, min(cursor_day, end) - timedelta(days=3)) if refresh else cursor_day
        calls = 0
        while day < end:
            page_cursor = None
            seen = set()
            db.execute("DELETE FROM samples WHERE tenant=? AND ref=? AND day=?", (tenant, ref, day.isoformat()))
            while True:
                seen.add(page_cursor)
                for attempt in range(3):
                    if calls >= budget:
                        raise RuntimeError("collection call limit")
                    calls += 1
                    try:
                        page, next_cursor = fetch(spec, ref, day, page_cursor)
                        break
                    except (TimeoutError, ConnectionError):
                        if attempt == 2:
                            raise
                        sleep(0.25 * 2 ** attempt)
                for row in normalize(spec, page, day):
                    args = (tenant, ref, day.isoformat(), *row)
                    db.execute("INSERT OR IGNORE INTO samples VALUES(?,?,?,?,?,?,?,?,?)", args)
                    stored = db.execute("SELECT end,value FROM samples WHERE tenant=? AND ref=? AND meter=? AND env=? AND start=?",
                                        (tenant, ref, row[0], row[1], row[2])).fetchone()
                    if tuple(stored) != (row[3], row[4]):
                        raise ValueError("conflicting duplicate")
                if next_cursor is None:
                    break
                if next_cursor in seen:
                    raise ValueError("pagination cycle")
                page_cursor = next_cursor
            day += DAY
        db.execute("INSERT OR REPLACE INTO checkpoints VALUES(?,?,?)",
                   (tenant, ref, max(cursor_day, end).isoformat()))
    return calls
