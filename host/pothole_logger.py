import json
import os
import sys
import sqlite3
import argparse
from datetime import datetime, timezone
from serial import Serial
from serial.serialutil import SerialException

# ------------------- CLI -------------------
def parse_args():
    p = argparse.ArgumentParser(description="UART JSON -> separate JSON logs + single SQLite DB")
    p.add_argument("--port", default="COM10", help="Serial port (e.g., COM7, /dev/ttyACM0)")
    p.add_argument("--baud", type=int, default=115200, help="Baud rate (default 115200)")
    p.add_argument("--potholes-json", default="potholes.json", help="Output JSON for pothole events")
    p.add_argument("--speedbrk-json", default="speedbreakers.json", help="Output JSON for speed breaker events")
    p.add_argument("--db", default="pothole_data.db", help="SQLite database file (all events)")
    p.add_argument("--session", default=None, help="Optional session id (default: timestamp)")
    p.add_argument("--max-json-records", type=int, default=0, help="0 = no rotation; else keep last N records per file")
    return p.parse_args()

# ------------------- JSON helpers -------------------
def ensure_json_file(path: str):
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump([], f, indent=2)

def append_json_record(path: str, record: dict, max_records: int = 0):
    """Append to JSON array file; optionally truncate to last N."""
    try:
        with open(path, "r+", encoding="utf-8") as f:
            try:
                data = json.load(f)
                if not isinstance(data, list):
                    data = []
            except Exception:
                data = []
            data.append(record)
            if max_records and len(data) > max_records:
                data = data[-max_records:]
            f.seek(0)
            json.dump(data, f, indent=2)
            f.truncate()
    except Exception as e:
        print("[ERROR] Writing JSON:", e, file=sys.stderr)

# ------------------- SQLite -------------------
def init_sqlite(db_path: str):
    conn = sqlite3.connect(db_path, isolation_level=None, check_same_thread=False)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS events (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      session TEXT NOT NULL,
      type TEXT NOT NULL,           -- 'POTHOLE' or 'SPEEDBRK'
      severity INTEGER,             -- 1..3 for pothole; NULL for speedbrk
      peak_mV INTEGER NOT NULL,
      width INTEGER NOT NULL,
      timestamp INTEGER NOT NULL,   -- device timestamp (ms)
      x INTEGER NOT NULL,
      y INTEGER NOT NULL,
      ingest_utc TEXT NOT NULL,
      raw_json TEXT NOT NULL
    );
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_events_ts ON events(timestamp);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_events_type ON events(type);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_events_session ON events(session);")
    return conn

def insert_sqlite(conn, session: str, rec: dict, raw_json: str):
    conn.execute("""
    INSERT INTO events
      (session, type, severity, peak_mV, width, timestamp, x, y, ingest_utc, raw_json)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, (
        session,
        rec["type"],
        rec.get("severity"),
        rec["peak_mV"],
        rec["width"],
        rec["timestamp"],
        rec["x"],
        rec["y"],
        datetime.now(timezone.utc).isoformat(),
        raw_json
    ))

# ------------------- Parsing -------------------
REQUIRED_COMMON = {"type", "peak_mV", "width", "timestamp", "x", "y"}

def parse_record(s: str):
    """
    Accepts lines like:
      POTHOLE:  {"type":"POTHOLE","severity":1,"peak_mV":477,"width":1580,"timestamp":745917,"x":745,"y":745}
      SPEEDBRK: {"type":"SPEEDBRK","peak_mV":488,"width":1807,"timestamp":178474,"x":178,"y":178}
    Returns normalized dict or None on error.
    """
    obj = json.loads(s)
    if not isinstance(obj, dict):
        return None

    # Basic required fields for both
    if not REQUIRED_COMMON.issubset(obj.keys()):
        return None

    t = str(obj["type"]).upper()
    if t not in ("POTHOLE", "SPEEDBRK"):
        return None

    # Cast core types; raise to caller if invalid
    rec = {
        "type": t,
        "peak_mV": int(obj["peak_mV"]),
        "width": int(obj["width"]),
        "timestamp": int(obj["timestamp"]),
        "x": int(obj["x"]),
        "y": int(obj["y"])
    }

    # Severity only for POTHOLE
    if t == "POTHOLE":
        if "severity" not in obj:
            return None  # pothole requires severity
        sev = int(obj["severity"])
        if not (1 <= sev <= 3):
            return None
        rec["severity"] = sev
    else:
        # SPEEDBRK: ensure no severity required; store None
        rec["severity"] = None

    return rec

# ------------------- Main -------------------
def main():
    args = parse_args()
    session = args.session or datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    # Prepare outputs
    ensure_json_file(args.potholes_json)
    ensure_json_file(args.speedbrk_json)
    conn = init_sqlite(args.db)

    print(f"Listening on {args.port} @ {args.baud}")
    print(f"Session: {session}")
    print(f"→ Potholes JSON:      {args.potholes_json}")
    print(f"→ Speed breakers JSON:{args.speedbrk_json}")
    print(f"→ SQLite DB:          {args.db}")

    try:
        with Serial(args.port, args.baud, timeout=1) as ser:
            while True:
                line = ser.readline()
                if not line:
                    continue
                s = line.decode("utf-8", errors="ignore").strip()
                if not s:
                    continue

                try:
                    rec = parse_record(s)
                except Exception:
                    # Non-fatal: skip malformed line silently
                    rec = None

                if rec is None:
                    continue

                # Add session for JSON & DB
                rec_out = dict(rec)
                rec_out["session"] = session

                # Route to proper JSON file
                if rec["type"] == "POTHOLE":
                    append_json_record(args.potholes_json, rec_out, args.max_json_records)
                else:  # SPEEDBRK
                    append_json_record(args.speedbrk_json, rec_out, args.max_json_records)

                # Insert into DB (all events)
                try:
                    insert_sqlite(conn, session, rec, s)
                except Exception as e:
                    print("[ERROR] SQLite insert:", e, file=sys.stderr)

    except SerialException as e:
        print("[ERROR] Serial:", e, file=sys.stderr)
    except KeyboardInterrupt:
        print("\nStopped.")

if __name__ == "__main__":
    main()

# python pothole_logger.py --port COM10 --baud 115200