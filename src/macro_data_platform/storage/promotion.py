"""Append-only, hash-chained JSONL decision events for policy promotion."""

import hashlib
import json
import os
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

_ZERO_HASH = "0" * 64
_MAX_EVENTS = 10_000
_MAX_LEDGER_BYTES = 32 * 1024 * 1024


def _canonical_bytes(value):
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _digest(value):
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key in promotion ledger")
        result[key] = value
    return result


@contextmanager
def _locked_file(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_RDWR | os.O_CREAT | os.O_APPEND | getattr(os, "O_BINARY", 0)
    descriptor = os.open(path, flags, 0o600)
    locked = False
    try:
        if os.name == "nt":
            import msvcrt

            os.lseek(descriptor, 0, os.SEEK_SET)
            msvcrt.locking(descriptor, msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(descriptor, fcntl.LOCK_EX)
        locked = True
        yield descriptor
    finally:
        if locked:
            if os.name == "nt":
                import msvcrt

                os.lseek(descriptor, 0, os.SEEK_SET)
                msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


class PromotionLedger:
    """Append and verify immutable events; Git tracks the resulting decision history."""

    def __init__(self, path: Path):
        self.path = Path(path).resolve()

    @staticmethod
    def _read(descriptor):
        size = os.fstat(descriptor).st_size
        if size > _MAX_LEDGER_BYTES:
            raise ValueError("promotion ledger exceeds the size limit")
        os.lseek(descriptor, 0, os.SEEK_SET)
        chunks = []
        remaining = size
        while remaining:
            chunk = os.read(descriptor, min(64 * 1024, remaining))
            if not chunk:
                raise ValueError("promotion ledger changed while being read")
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        if not raw:
            return []
        if not raw.endswith(b"\n"):
            raise ValueError("promotion ledger ends with an incomplete event")
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("promotion ledger is not valid UTF-8") from exc

        events = []
        expected_previous = _ZERO_HASH
        lines = text.splitlines()
        if len(lines) > _MAX_EVENTS:
            raise ValueError("promotion ledger exceeds the event limit")
        for expected_sequence, line in enumerate(lines, 1):
            try:
                event = json.loads(line, object_pairs_hook=_unique_object)
            except (json.JSONDecodeError, TypeError) as exc:
                raise ValueError("promotion ledger contains invalid JSON") from exc
            required = {
                "event_sequence", "event_id", "previous_event_hash", "body", "event_hash",
            }
            if not isinstance(event, dict) or set(event) != required:
                raise ValueError("promotion ledger event fields are invalid")
            sequence = event["event_sequence"]
            body = event["body"]
            previous_hash = event["previous_event_hash"]
            event_id = event["event_id"]
            if (type(sequence) is not int or sequence != expected_sequence
                    or not isinstance(body, dict) or previous_hash != expected_previous
                    or not isinstance(event_id, str) or not event_id):
                raise ValueError("promotion ledger sequence or chain link is invalid")
            envelope = {
                "event_sequence": sequence,
                "event_id": event_id,
                "previous_event_hash": previous_hash,
                "body": body,
            }
            if _digest(envelope) != event["event_hash"]:
                raise ValueError("promotion ledger event hash mismatch")
            events.append({**envelope, "event_hash": event["event_hash"]})
            expected_previous = event["event_hash"]
        return events

    def verify(self):
        with _locked_file(self.path) as descriptor:
            events = self._read(descriptor)
        return {
            "status": "PASS",
            "event_count": len(events),
            "last_event_hash": events[-1]["event_hash"] if events else _ZERO_HASH,
        }

    def events(self):
        with _locked_file(self.path) as descriptor:
            return self._read(descriptor)

    def append(self, body):
        if not isinstance(body, dict):
            raise TypeError("promotion ledger event body must be an object")
        body = {**body, "created_at_utc": datetime.now(UTC).isoformat()}
        with _locked_file(self.path) as descriptor:
            events = self._read(descriptor)
            sequence = len(events) + 1
            if sequence > _MAX_EVENTS:
                raise ValueError("promotion ledger exceeds the event limit")
            event_id = str(uuid4())
            previous_hash = events[-1]["event_hash"] if events else _ZERO_HASH
            envelope = {
                "event_sequence": sequence,
                "event_id": event_id,
                "previous_event_hash": previous_hash,
                "body": body,
            }
            event_hash = _digest(envelope)
            encoded = _canonical_bytes({**envelope, "event_hash": event_hash}) + b"\n"
            if os.fstat(descriptor).st_size + len(encoded) > _MAX_LEDGER_BYTES:
                raise ValueError("promotion ledger exceeds the size limit")
            offset = 0
            while offset < len(encoded):
                offset += os.write(descriptor, encoded[offset:])
            os.fsync(descriptor)
        return {**envelope, "event_hash": event_hash}
