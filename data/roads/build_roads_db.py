#!/usr/bin/env python3
"""
build_roads_db.py — GeoSentinel V2
===================================
One-time builder: reads data/roads/roads.json.gz and writes data/roads/roads.db.
Run this locally whenever the source road data changes.

Usage (from the repo root):
    python data/roads/build_roads_db.py

The output roads.db is committed to Git so Render never has to load the
full 177 MB JSON at startup.
"""

import gzip
import json
import math
import os
import sqlite3

HERE = os.path.dirname(os.path.abspath(__file__))
ROADS_GZ = os.path.join(HERE, "roads.json.gz")
DB_PATH = os.path.join(HERE, "roads.db")

# Maximum coordinate points kept per road after simplification.
# 10 points gives ~1 m accuracy for nearest-road projection while
# cutting coordinate storage to ≤10 % of some very detailed roads.
MAX_COORDS = 10

# Coordinate decimal places kept (5 dp = ~1 m precision at equator).
COORD_PRECISION = 5


def simplify_coords(coords):
    """Stride-sample a coordinate list down to at most MAX_COORDS points."""
    n = len(coords)
    if n <= MAX_COORDS:
        return coords
    step = max(1, n // MAX_COORDS)
    simplified = coords[::step]
    if simplified[-1] != coords[-1]:
        simplified = simplified + [coords[-1]]
    return simplified


def round_coords(coords):
    """Round every coordinate to COORD_PRECISION decimal places."""
    return [[round(c[0], COORD_PRECISION), round(c[1], COORD_PRECISION)]
            for c in coords]


def main():
    if not os.path.exists(ROADS_GZ):
        raise FileNotFoundError(f"Source not found: {ROADS_GZ}")

    print(f"Loading {ROADS_GZ} ...")
    with gzip.open(ROADS_GZ, "rb") as f:
        roads = json.loads(f.read().decode("utf-8"))
    print(f"  {len(roads):,} roads loaded")

    # Remove any existing database so we start clean.
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        print(f"  Removed existing {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Tune for fast bulk inserts.
    cur.executescript("""
        PRAGMA page_size    = 4096;
        PRAGMA journal_mode = OFF;
        PRAGMA synchronous  = OFF;
        PRAGMA cache_size   = -65536;

        CREATE TABLE roads (
            id     INTEGER PRIMARY KEY,
            name   TEXT,
            type   TEXT,
            coords TEXT NOT NULL
        );

        CREATE VIRTUAL TABLE roads_rtree USING rtree(
            id,
            min_lon, max_lon,
            min_lat, max_lat
        );
    """)

    inserted = 0
    skipped = 0

    for road in roads:
        raw_coords = road.get("coordinates", [])
        if len(raw_coords) < 2:
            skipped += 1
            continue

        simplified = round_coords(simplify_coords(raw_coords))

        lons = [c[0] for c in simplified]
        lats = [c[1] for c in simplified]

        cur.execute(
            "INSERT INTO roads (name, type, coords) VALUES (?, ?, ?)",
            (road.get("name"), road.get("type", "road"), json.dumps(simplified)),
        )
        row_id = cur.lastrowid
        cur.execute(
            "INSERT INTO roads_rtree VALUES (?, ?, ?, ?, ?)",
            (row_id, min(lons), max(lons), min(lats), max(lats)),
        )

        inserted += 1
        if inserted % 25_000 == 0:
            conn.commit()
            print(f"  {inserted:,} roads written …")

    conn.commit()

    # Compact the database to minimise file size.
    print("  Running VACUUM …")
    conn.execute("VACUUM")
    conn.close()

    size_mb = os.path.getsize(DB_PATH) / 1024 / 1024
    print(f"\nDone.")
    print(f"  Roads inserted : {inserted:,}")
    print(f"  Roads skipped  : {skipped:,}")
    print(f"  Database size  : {size_mb:.2f} MB")
    print(f"  Saved to       : {DB_PATH}")

    if size_mb > 100:
        print("\nWARNING: DB exceeds GitHub's 100 MB per-file limit!")
        print("  Consider reducing MAX_COORDS or COORD_PRECISION.")


if __name__ == "__main__":
    main()
