"""SQLite event journal with ordering, timing, and a verifiable hash chain."""

import json
from pathlib import Path
import sqlite3
import time

from .tools import digest


class Journal:
    def __init__(self, path: Path):
        self.path = path
        with sqlite3.connect(path) as db:
            db.execute("CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY, payload TEXT NOT NULL, hash TEXT NOT NULL)")

    def add(self, event: str, revision: int, **details):
        # Each writer gets a connection; BEGIN IMMEDIATE serializes parallel branches.
        with sqlite3.connect(self.path, timeout=10) as db:
            db.execute("BEGIN IMMEDIATE")
            last = db.execute("SELECT hash FROM events ORDER BY seq DESC LIMIT 1").fetchone()
            payload = {"time": time.time(), "event": event, "revision": revision,
                       "previous": last[0] if last else "", **details}
            db.execute("INSERT INTO events(payload, hash) VALUES (?, ?)",
                       (json.dumps(payload, sort_keys=True), digest(payload)))

    def events(self) -> list[dict]:
        with sqlite3.connect(self.path) as db:
            return [{"seq": seq, **json.loads(payload), "hash": hash_}
                    for seq, payload, hash_ in db.execute("SELECT seq, payload, hash FROM events ORDER BY seq")]

    def verify(self) -> bool:
        previous = ""
        try:
            events = self.events()
        except (ValueError, TypeError):
            return False
        for event in events:
            event.pop("seq")
            stored_hash = event.pop("hash")
            if event.get("previous") != previous or digest(event) != stored_hash:
                return False
            previous = stored_hash
        return True

    def metrics(self) -> dict:
        events = self.events()
        counts = {name: sum(e["event"] == name for e in events)
                  for name in ("retry", "rollback", "fallback", "replan", "failure", "completed", "stopped", "rejected")}
        recovery = []
        started = None
        for event in events:
            if event["event"] == "failure" and started is None:
                started = event["time"]
            if event["event"] == "completed" and started is not None:
                recovery.append(event["time"] - started)
                started = None
        return {**counts,
                "elapsed_seconds": round(events[-1]["time"] - events[0]["time"], 3) if events else 0,
                "active_stage_seconds": round(sum(e.get("duration", 0) for e in events), 3),
                "mttr_seconds": sum(recovery) / len(recovery) if recovery else None,
                "journal_chain_valid": self.verify()}
