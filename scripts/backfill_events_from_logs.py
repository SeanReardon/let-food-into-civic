#!/usr/bin/env python3
"""
Backfill structured event files from application logs.

Creates:
  - {ISO8601-UTC}-call-event.json
  - {ISO8601-UTC}-snooze-event.json
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path


CALL_MARKER = "INCOMING CALL RECEIVED"
CALLER_RE = re.compile(r"\sFrom:\s*(.+)$")
SNOOZE_RE = re.compile(
    r"(?:snooze set to True|skip_next set to True)", re.IGNORECASE
)
USER_RE = re.compile(r"\b(Sean|Linda)\b", re.IGNORECASE)
SUMMARY_RE = re.compile(
    r"SMS summary:\s+\d+\s+succeeded,\s+\d+\s+failed,\s+(\d+)\s+skipped",
    re.IGNORECASE,
)


def parse_log_timestamp(line: str) -> str | None:
    """
    Parse a log-line prefix timestamp into ISO8601 UTC.

    Example log prefix:
      2026-02-25 18:29:08,123 - src.main - INFO - ...
    """
    prefix = line.split(" - ", 1)[0].strip()
    for fmt in ("%Y-%m-%d %H:%M:%S,%f", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.strptime(prefix, fmt).replace(tzinfo=timezone.utc)
            return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")
        except ValueError:
            continue
    return None


def event_filename(timestamp: str, event_type: str) -> str:
    return f"{timestamp}-{event_type}.json"


def write_event(
    output_dir: Path, timestamp: str, event_type: str, payload: dict
) -> bool:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / event_filename(timestamp, event_type)
    if path.exists():
        return False

    body = {
        "schemaVersion": "1.0.0",
        "eventType": event_type,
        "timestamp": timestamp,
        **payload,
    }
    path.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
    return True


def backfill(log_file: Path, output_dir: Path) -> tuple[int, int]:
    created_calls = 0
    created_snoozes = 0

    in_call_block = False
    pending_call_ts: str | None = None
    call_ts_to_snoozed: dict[str, str] = {}

    lines = log_file.read_text(encoding="utf-8", errors="ignore").splitlines()
    for raw in lines:
        ts = parse_log_timestamp(raw)
        if not ts:
            continue

        if CALL_MARKER in raw:
            in_call_block = True
            pending_call_ts = ts
            continue

        if in_call_block:
            m = CALLER_RE.search(raw)
            if m:
                caller = m.group(1).strip()
                if write_event(
                    output_dir,
                    ts,
                    "call-event",
                    {"fromNumber": caller, "snoozedUsersCsv": ""},
                ):
                    created_calls += 1
                in_call_block = False
                continue
            # End call block if we reached next divider-like line.
            if "====" in raw:
                in_call_block = False

        if SNOOZE_RE.search(raw):
            um = USER_RE.search(raw)
            if um:
                user = um.group(1).lower()
                if write_event(
                    output_dir,
                    ts,
                    "snooze-event",
                    {"snoozedUser": user},
                ):
                    created_snoozes += 1

        summary_match = SUMMARY_RE.search(raw)
        if summary_match and pending_call_ts:
            skipped = int(summary_match.group(1))
            if skipped > 0:
                # Logs do not reliably identify which users were skipped per call,
                # so we preserve count in placeholder entries.
                placeholders = [f"unknown{i+1}" for i in range(skipped)]
                call_ts_to_snoozed[pending_call_ts] = ",".join(placeholders)
            else:
                call_ts_to_snoozed[pending_call_ts] = ""
            pending_call_ts = None

    # Second pass: inject best-effort snoozed list into call events by timestamp.
    for call_file in output_dir.glob("*-call-event.json"):
        try:
            payload = json.loads(call_file.read_text(encoding="utf-8"))
            ts = payload.get("timestamp")
            if not ts:
                continue
            payload["snoozedUsersCsv"] = call_ts_to_snoozed.get(
                ts, payload.get("snoozedUsersCsv", "")
            )
            call_file.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        except Exception:
            continue

    return created_calls, created_snoozes


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill structured event files from app.log"
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        default=Path("/app/data/logs/app.log"),
        help="Path to app log file",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("/app/data/events"),
        help="Directory to write event files",
    )
    args = parser.parse_args()

    if not args.log_file.exists():
        raise SystemExit(f"log file not found: {args.log_file}")

    calls, snoozes = backfill(args.log_file, args.output_dir)
    print(
        "Backfill complete. "
        f"created_call_events={calls} "
        f"created_snooze_events={snoozes} "
        f"output_dir={args.output_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
