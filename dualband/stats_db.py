import sqlite3
import threading
import time
from contextlib import contextmanager

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    correlation_key TEXT NOT NULL,
    sender TEXT,
    channel TEXT,
    text TEXT,
    first_band TEXT,
    first_seen_ts REAL,
    received_433 INTEGER DEFAULT 0,
    received_868 INTEGER DEFAULT 0,
    ts_433 REAL,
    ts_868 REAL,
    hops_433 INTEGER,
    hops_868 INTEGER,
    missed_by TEXT,
    finalized INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_corr ON messages(correlation_key);
CREATE INDEX IF NOT EXISTS idx_ts ON messages(first_seen_ts);
"""

class StatsDB:
    def __init__(self, path):
        self.path = path
        self._lock = threading.Lock()
        with self._conn() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.path, timeout=5)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def record_reception(self, corr_key, band, sender, channel, text, hops):
        now = time.time()
        with self._lock, self._conn() as c:
            row = c.execute(
                "SELECT * FROM messages WHERE correlation_key=? AND finalized=0",
                (corr_key,)
            ).fetchone()
            if row is None:
                c.execute("""
                    INSERT INTO messages
                    (correlation_key,sender,channel,text,first_band,
                     first_seen_ts,received_433,received_868,
                     ts_433,ts_868,hops_433,hops_868)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    corr_key, sender, channel, text, band, now,
                    1 if band=="433" else 0,
                    1 if band=="868" else 0,
                    now if band=="433" else None,
                    now if band=="868" else None,
                    hops if band=="433" else None,
                    hops if band=="868" else None,
                ))
                return True
            else:
                col_recv = f"received_{band}"
                col_ts   = f"ts_{band}"
                col_hop  = f"hops_{band}"
                c.execute(
                    f"UPDATE messages SET {col_recv}=1,{col_ts}=?,{col_hop}=? WHERE id=?",
                    (now, hops, row["id"])
                )
                return False

    def finalize_stale(self, grace_seconds):
        cutoff = time.time() - grace_seconds
        with self._lock, self._conn() as c:
            rows = c.execute(
                "SELECT id,received_433,received_868 FROM messages "
                "WHERE finalized=0 AND first_seen_ts<?", (cutoff,)
            ).fetchall()
            for r in rows:
                missed = None
                if r["received_433"] and not r["received_868"]:
                    missed = "868"
                elif r["received_868"] and not r["received_433"]:
                    missed = "433"
                c.execute(
                    "UPDATE messages SET finalized=1,missed_by=? WHERE id=?",
                    (missed, r["id"])
                )

    def summary(self):
        with self._conn() as c:
            total = c.execute(
                "SELECT COUNT(*) FROM messages WHERE finalized=1"
            ).fetchone()[0]
            if total == 0:
                return {"total": 0}
            r433 = c.execute(
                "SELECT COUNT(*) FROM messages WHERE finalized=1 AND received_433=1"
            ).fetchone()[0]
            r868 = c.execute(
                "SELECT COUNT(*) FROM messages WHERE finalized=1 AND received_868=1"
            ).fetchone()[0]
            both = c.execute(
                "SELECT COUNT(*) FROM messages WHERE finalized=1 "
                "AND received_433=1 AND received_868=1"
            ).fetchone()[0]
            return {
                "total": total,
                "received_433": r433,
                "received_868": r868,
                "received_both": both,
                "success_rate_433": round(100*r433/total, 2),
                "success_rate_868": round(100*r868/total, 2),
                "success_rate_both": round(100*both/total, 2),
            }

    def per_channel(self):
        with self._conn() as c:
            return [dict(r) for r in c.execute("""
                SELECT channel,
                       COUNT(*) AS total,
                       SUM(received_433) AS r433,
                       SUM(received_868) AS r868,
                       SUM(CASE WHEN received_433=1 AND received_868=1 THEN 1 ELSE 0 END) AS both
                FROM messages WHERE finalized=1
                GROUP BY channel
            """).fetchall()]

    def recent_missed(self, limit=50):
        with self._conn() as c:
            return [dict(r) for r in c.execute("""
                SELECT *, datetime(first_seen_ts,'unixepoch','localtime') AS readable_ts
                FROM messages
                WHERE finalized=1 AND missed_by IS NOT NULL
                ORDER BY first_seen_ts DESC LIMIT ?
            """, (limit,)).fetchall()]

    def recent_all(self, limit=100):
        with self._conn() as c:
            return [dict(r) for r in c.execute("""
                SELECT *, datetime(first_seen_ts,'unixepoch','localtime') AS readable_ts
                FROM messages WHERE finalized=1
                ORDER BY first_seen_ts DESC LIMIT ?
            """, (limit,)).fetchall()]
