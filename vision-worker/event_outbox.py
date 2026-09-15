"""Durable event delivery. No credentials are written to the outbox."""
import json
import os
import sqlite3
import threading
import time
import uuid


class EventOutbox:
    def __init__(self, path):
        if path != ':memory:':
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(path, check_same_thread=False, timeout=10, isolation_level=None)
        self._db.execute('PRAGMA journal_mode=WAL')
        self._db.execute('PRAGMA synchronous=FULL')
        self._db.executescript('''
            CREATE TABLE IF NOT EXISTS outbox (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT UNIQUE NOT NULL, destination TEXT NOT NULL,
                payload TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
                available_at REAL NOT NULL DEFAULT 0, lease_token TEXT,
                rejected INTEGER NOT NULL DEFAULT 0, error TEXT);
            CREATE TABLE IF NOT EXISTS chain (session_id TEXT PRIMARY KEY, last_hash TEXT NOT NULL);
        ''')

    def enqueue(self, destination, payload):
        payload = dict(payload)
        payload['eventHash'] = payload.get('eventHash') or uuid.uuid4().hex
        with self._lock:
            self._db.execute('BEGIN IMMEDIATE')
            try:
                self._db.execute('INSERT OR IGNORE INTO outbox(event_id,destination,payload) VALUES(?,?,?)',
                                 (payload['eventHash'], destination, json.dumps(payload)))
                if payload.get('sessionId'):
                    self._db.execute('INSERT OR REPLACE INTO chain VALUES(?,?)',
                                     (payload['sessionId'], payload['eventHash']))
                self._db.execute('COMMIT')
            except BaseException:
                self._db.execute('ROLLBACK')
                raise
        return payload['eventHash']

    def previous_hash(self, session_id):
        with self._lock:
            row = self._db.execute('SELECT last_hash FROM chain WHERE session_id=?', (session_id,)).fetchone()
            return row[0] if row else None

    def claim(self, now=None):
        now = time.time() if now is None else now
        with self._lock:
            self._db.execute('BEGIN IMMEDIATE')
            try:
                # Preserve sequence across retries and across competing consumers.
                row = self._db.execute('SELECT sequence,destination,payload,attempts,available_at FROM outbox WHERE rejected=0 ORDER BY sequence LIMIT 1').fetchone()
                if not row or row[4] > now:
                    self._db.execute('COMMIT')
                    return None
                token = uuid.uuid4().hex
                self._db.execute('UPDATE outbox SET lease_token=?,available_at=? WHERE sequence=?', (token, now + 30, row[0]))
                self._db.execute('COMMIT')
                return dict(sequence=row[0], url=row[1], payload=json.loads(row[2]), attempts=row[3], token=token)
            except BaseException:
                self._db.execute('ROLLBACK')
                raise

    def complete(self, job, *, accepted=False, permanent=False, error='', now=None):
        now = time.time() if now is None else now
        with self._lock:
            if accepted:
                self._db.execute('DELETE FROM outbox WHERE sequence=? AND lease_token=?', (job['sequence'], job['token']))
            else:
                delay = min(60, 2 ** min(job['attempts'], 6))
                self._db.execute('UPDATE outbox SET attempts=attempts+1, available_at=?, lease_token=NULL, rejected=?, error=? WHERE sequence=? AND lease_token=?',
                                 (now + delay, int(permanent), error[:500], job['sequence'], job['token']))

    def count(self, rejected=False):
        with self._lock:
            return self._db.execute('SELECT COUNT(*) FROM outbox WHERE rejected=?', (int(rejected),)).fetchone()[0]

    def close(self):
        with self._lock:
            self._db.close()
