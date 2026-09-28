import json
import sqlite3
from pathlib import Path
from datetime import datetime, timezone


def now():
    return datetime.now(timezone.utc).isoformat()


class State:
    def __init__(self, path):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS offers (
                fingerprint TEXT PRIMARY KEY, offer TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'new', evaluation TEXT,
                evaluator TEXT, application_id INTEGER, notified_at TEXT,
                first_seen TEXT NOT NULL, last_error TEXT);
            CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        """)
        self.db.commit()

    def close(self):
        self.db.close()

    def add(self, offer):
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO offers(fingerprint, offer, first_seen) VALUES (?, ?, ?)",
                            (offer.fingerprint, offer.model_dump_json(), now()))

    def get(self, fingerprint):
        return self.db.execute("SELECT * FROM offers WHERE fingerprint=?", (fingerprint,)).fetchone()

    def update(self, fingerprint, **fields):
        allowed = {"status", "evaluation", "evaluator", "application_id", "notified_at", "last_error"}
        if not fields or not set(fields) <= allowed:
            raise ValueError("Champs d'état invalides")
        with self.db:
            self.db.execute("UPDATE offers SET " + ", ".join(f"{key}=?" for key in fields) + " WHERE fingerprint=?",
                            (*fields.values(), fingerprint))

    def pending(self):
        return self.db.execute("SELECT * FROM offers WHERE status IN ('new','selected') ORDER BY first_seen, fingerprint").fetchall()

    def notifications(self):
        return self.db.execute("SELECT * FROM offers WHERE status='imported' AND notified_at IS NULL ORDER BY first_seen").fetchall()

    def metadata(self, key):
        row = self.db.execute("SELECT value FROM metadata WHERE key=?", (key,)).fetchone()
        return row[0] if row else None

    def mark_notified(self, rows):
        timestamp = now()
        with self.db:
            self.db.executemany("UPDATE offers SET notified_at=? WHERE fingerprint=?", [(timestamp, r["fingerprint"]) for r in rows])
            self.db.execute("INSERT OR REPLACE INTO metadata VALUES ('last_digest', ?)", (timestamp,))
