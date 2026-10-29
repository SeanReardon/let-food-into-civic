"""Authenticate notification triggers and claim provider calls once across workers."""
import base64
import sqlite3
import time
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


def verified_webhook(public_key, headers, body, now=None):
    try:
        timestamp = headers['telnyx-timestamp']
        if abs((time.time() if now is None else now) - int(timestamp)) > 300:
            return False
        key = Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key, validate=True))
        key.verify(base64.b64decode(headers['telnyx-signature-ed25519'], validate=True),
                   timestamp.encode() + b'|' + body)
        return True
    except Exception:
        return False


def claim_call(path, call_id):
    if not call_id or call_id == 'unknown' or len(call_id) > 512:
        return False
    with sqlite3.connect(path, timeout=2) as db:
        db.execute('CREATE TABLE IF NOT EXISTS notified_calls (call_id TEXT PRIMARY KEY, claimed_at REAL NOT NULL)')
        cursor = db.execute('INSERT OR IGNORE INTO notified_calls VALUES (?, ?)', (call_id, time.time()))
        return cursor.rowcount == 1
