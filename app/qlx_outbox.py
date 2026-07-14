import json
import os
import sqlite3
import time
import uuid
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class OutboxEvent:
    event_id: str
    payload: dict[str, Any]
    attempts: int
    next_attempt_at: float


class EventOutbox:
    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()

    def _connect(self):
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=30000;")
        return conn

    def _init_db(self):
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS outbox_events (
                    event_id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    next_attempt_at REAL NOT NULL DEFAULT 0,
                    last_error TEXT
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_outbox_pending "
                "ON outbox_events(status, next_attempt_at, created_at)"
            )

    def enqueue(self, payload: dict[str, Any]) -> str:
        event_id = payload.get("event_id") or str(uuid.uuid4())
        durable_payload = dict(payload)
        durable_payload["event_id"] = event_id
        durable_payload["idempotency_key"] = durable_payload.get("idempotency_key") or event_id
        now_ts = time.time()
        payload_json = json.dumps(durable_payload, ensure_ascii=False, sort_keys=True)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO outbox_events
                    (event_id, payload_json, status, attempts, created_at, updated_at, next_attempt_at)
                VALUES (?, ?, 'pending', 0, ?, ?, 0)
                """,
                (event_id, payload_json, now_ts, now_ts),
            )
        return event_id

    def next_pending(self, limit: int = 20, now_ts: float | None = None) -> list[OutboxEvent]:
        ready_at = time.time() if now_ts is None else now_ts
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT event_id, payload_json, attempts, next_attempt_at
                FROM outbox_events
                WHERE status='pending' AND next_attempt_at <= ?
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (ready_at, limit),
            ).fetchall()
        return [
            OutboxEvent(
                event_id=row[0],
                payload=json.loads(row[1]),
                attempts=int(row[2]),
                next_attempt_at=float(row[3]),
            )
            for row in rows
        ]

    def mark_sent(self, event_id: str):
        now_ts = time.time()
        with self._connect() as conn:
            conn.execute(
                "UPDATE outbox_events SET status='sent', updated_at=?, last_error=NULL WHERE event_id=?",
                (now_ts, event_id),
            )

    def mark_failed(self, event_id: str, error: str, base_delay_seconds: int = 5, max_delay_seconds: int = 300):
        with self._connect() as conn:
            row = conn.execute(
                "SELECT attempts FROM outbox_events WHERE event_id=?",
                (event_id,),
            ).fetchone()
            attempts = int(row[0]) + 1 if row else 1
            delay = min(max_delay_seconds, base_delay_seconds * (2 ** min(attempts - 1, 6)))
            now_ts = time.time()
            conn.execute(
                """
                UPDATE outbox_events
                SET attempts=?, updated_at=?, next_attempt_at=?, last_error=?
                WHERE event_id=?
                """,
                (attempts, now_ts, now_ts + delay, error[:1000], event_id),
            )

    def pending_count(self) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM outbox_events WHERE status='pending'"
            ).fetchone()
        return int(row[0])

    def prune_sent(self, older_than_seconds: int = 7 * 24 * 3600) -> int:
        cutoff = time.time() - older_than_seconds
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM outbox_events WHERE status='sent' AND updated_at < ?",
                (cutoff,),
            )
            return int(cursor.rowcount)
