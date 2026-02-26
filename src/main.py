"""
let-food-into-civic - Automatic Call Box Unlocker

When the apartment call box rings, this service answers and plays DTMF tone "5"
repeatedly to unlock the gate for food deliveries.

Features:
- Answers calls and plays DTMF tones via TeXML
- Sends SMS notifications when gate is unlocked
"""

import json
import logging
import os
import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from flask import Flask, Response, request, jsonify, redirect, send_from_directory, abort
import telnyx

# Load environment variables from .env file
load_dotenv()

# Data directory paths
DATA_DIR = Path("/app/data")
LOGS_DIR = DATA_DIR / "logs"
OPT_IN_FLOW_DIR = DATA_DIR / "opt-in-flow"

# Create directories if they don't exist
LOGS_DIR.mkdir(parents=True, exist_ok=True)
OPT_IN_FLOW_DIR.mkdir(parents=True, exist_ok=True)

# Configure logging with both console and file handlers
log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
handlers = [logging.StreamHandler(sys.stdout)]

# Add file handler for persistent logs
log_file = LOGS_DIR / "app.log"
file_handler = logging.FileHandler(log_file)
file_handler.setFormatter(logging.Formatter(log_format))
handlers.append(file_handler)

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format=log_format,
    handlers=handlers,
)

logger = logging.getLogger(__name__)

app = Flask(__name__)

# =============================================================================
# Configuration
# =============================================================================

# Telnyx API Key
TELNYX_API_KEY = os.getenv("TELNYX_LET_FOOD_INTO_CIVIC_KEY", "")

# DTMF tone configuration
UNLOCK_DIGIT = os.getenv("UNLOCK_DIGIT", "5")
TONE_DURATION_REPEATS = int(
    os.getenv("TONE_DURATION_REPEATS", "8")
)  # ~2 seconds (8 x 250ms)
PAUSE_DURATION = float(os.getenv("PAUSE_DURATION", "0.5"))  # seconds
ITERATIONS = int(os.getenv("ITERATIONS", "6"))

# SMS notification configuration
# Comma-separated list of phone numbers to notify (accepts various formats, normalized to E.164)
NOTIFY_NUMBERS_RAW = [
    n.strip() for n in os.getenv("NOTIFY_NUMBERS", "").split(",") if n.strip()
]


def is_local_network(req) -> bool:
    """
    Check if a request originates from the local network.

    Returns True for:
    - Private IP ranges: 192.168.x.x, 10.x.x.x, 172.16-31.x.x
    - Localhost: 127.0.0.1, ::1

    When behind a reverse proxy (nginx), checks X-Forwarded-For header.
    """
    import ipaddress

    # Get the client IP - check X-Forwarded-For first (for reverse proxy setups)
    forwarded_for = req.headers.get("X-Forwarded-For", "")
    if forwarded_for:
        # X-Forwarded-For can contain multiple IPs: "client, proxy1, proxy2"
        # The first IP is the original client
        client_ip = forwarded_for.split(",")[0].strip()
    else:
        # Fall back to remote_addr for direct connections
        client_ip = req.remote_addr or ""

    if not client_ip:
        return False

    try:
        ip = ipaddress.ip_address(client_ip)

        # Check for localhost
        if ip.is_loopback:
            return True

        # Check for private network ranges
        if ip.is_private:
            return True

        return False
    except ValueError:
        # Invalid IP address
        logger.warning(f"Invalid IP address for local network check: {client_ip}")
        return False


def is_internal_network(req) -> bool:
    """
    Determine internal access using nginx-provided network header.

    Header contract:
    - X-Internal-Network: true   -> internal dashboard
    - X-Internal-Network: false  -> external/public page

    Falls back to legacy IP-based local detection if the header is absent.
    """
    header_value = req.headers.get("X-Internal-Network", "").strip().lower()
    if header_value == "true":
        return True
    if header_value == "false":
        return False
    return is_local_network(req)


def normalize_phone_number(phone: str) -> str:
    """
    Normalize phone number to E.164 format (+1XXXXXXXXXX).

    Handles various formats:
    - +12149090499 (already E.164)
    - (214) 909-0499
    - 214-909-0499
    - 2149090499
    - 12149090499
    - 1-214-909-0499
    - etc.

    Assumes US numbers unless obviously not (starts with + and country code other than 1).
    """
    import re

    # Remove all non-digit characters
    digits = re.sub(r"\D", "", phone)

    # Handle empty or invalid
    if not digits:
        return phone  # Return original if we can't parse

    # If it starts with +, check if it's already E.164
    if phone.startswith("+"):
        # Extract digits after +
        digits_after_plus = re.sub(r"\D", "", phone[1:])
        if len(digits_after_plus) == 11 and digits_after_plus.startswith("1"):
            return "+" + digits_after_plus
        elif len(digits_after_plus) == 10:
            # US number without country code
            return "+1" + digits_after_plus
        else:
            # International number - return as-is
            return phone

    # Handle US numbers (10 or 11 digits)
    if len(digits) == 10:
        # 10 digits: assume US, add country code
        return "+1" + digits
    elif len(digits) == 11 and digits.startswith("1"):
        # 11 digits starting with 1: US number
        return "+" + digits
    elif len(digits) > 11:
        # More than 11 digits: might be international, return with +
        return "+" + digits
    else:
        # Less than 10 digits: invalid, return original
        # Note: logger not available yet at module load time, so we'll log later if needed
        return phone


# Normalize all phone numbers to E.164 format
NOTIFY_NUMBERS = [normalize_phone_number(n) for n in NOTIFY_NUMBERS_RAW]

# Your Telnyx phone number (the one that receives calls and sends SMS)
# Normalize to E.164 format
TELNYX_PHONE_NUMBER_RAW = os.getenv("TELNYX_PHONE_NUMBER", "")
TELNYX_PHONE_NUMBER = (
    normalize_phone_number(TELNYX_PHONE_NUMBER_RAW) if TELNYX_PHONE_NUMBER_RAW else ""
)

# Initialize Telnyx client
telnyx_client = telnyx.Telnyx(api_key=TELNYX_API_KEY) if TELNYX_API_KEY else None

# Opt-in tracking file
OPT_IN_FILE = OPT_IN_FLOW_DIR / "opt-ins.json"

# Snooze state file
SNOOZE_FILE = DATA_DIR / "snooze.json"
SMS_PAUSE_STATE_FILE = DATA_DIR / "sms-pause-state.json"

# Events log file
EVENTS_FILE = DATA_DIR / "events.json"

# Phone number to name mapping for snooze feature
PHONE_TO_NAME = {
    "+14693059242": "linda",
    "+12149090499": "sean",
}
NAME_TO_PHONE = {v: k for k, v in PHONE_TO_NAME.items()}
ART_DIR = Path("/app/art")


# =============================================================================
# Opt-In/Opt-Out Management
# =============================================================================


def load_opt_ins():
    """Load opt-in status from file."""
    if not OPT_IN_FILE.exists():
        return {}
    try:
        with open(OPT_IN_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load opt-ins: {e}")
        return {}


def save_opt_ins(opt_ins):
    """Save opt-in status to file."""
    try:
        with open(OPT_IN_FILE, "w") as f:
            json.dump(opt_ins, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save opt-ins: {e}")


def is_opted_in(phone_number):
    """Check if a phone number has opted in."""
    opt_ins = load_opt_ins()
    return opt_ins.get(phone_number, {}).get("status") == "opted_in"


def opt_in(phone_number, source="manual"):
    """Record an opt-in event."""
    opt_ins = load_opt_ins()
    timestamp = datetime.now().isoformat()

    opt_ins[phone_number] = {
        "status": "opted_in",
        "opted_in_at": timestamp,
        "source": source,
    }

    save_opt_ins(opt_ins)

    # Audit log
    audit_log_opt_in_event(phone_number, "opted_in", source, timestamp)

    logger.info(f"✅ {phone_number} opted in (source: {source})")


def opt_out(phone_number, source="manual"):
    """Record an opt-out event."""
    opt_ins = load_opt_ins()
    timestamp = datetime.now().isoformat()

    # Preserve original opt-in timestamp if it exists
    original_opt_in = opt_ins.get(phone_number, {}).get("opted_in_at")

    opt_ins[phone_number] = {
        "status": "opted_out",
        "opted_out_at": timestamp,
        "opted_in_at": original_opt_in,  # Preserve history
        "source": source,
    }

    save_opt_ins(opt_ins)

    # Audit log
    audit_log_opt_in_event(phone_number, "opted_out", source, timestamp)

    logger.info(f"🛑 {phone_number} opted out (source: {source})")


def audit_log_opt_in_event(phone_number, action, source, timestamp):
    """Write audit log entry for opt-in/opt-out events."""
    audit_file = OPT_IN_FLOW_DIR / f"audit-{datetime.now().strftime('%Y-%m')}.log"

    entry = {
        "timestamp": timestamp,
        "phone_number": phone_number,
        "action": action,
        "source": source,
    }

    try:
        with open(audit_file, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        logger.error(f"Failed to write audit log: {e}")


# =============================================================================
# SMS Pause State Management (skip next unlock only)
# =============================================================================


def default_sms_pause_state():
    return {
        "sean": {"skip_next": False, "phone": NAME_TO_PHONE.get("sean", "")},
        "linda": {"skip_next": False, "phone": NAME_TO_PHONE.get("linda", "")},
    }


def load_sms_pause_state():
    """
    Load per-user SMS pause state from file.

    Schema:
    {
      "sean": {"skip_next": false, "phone": "+1..."},
      "linda": {"skip_next": false, "phone": "+1..."}
    }
    """
    default_state = default_sms_pause_state()

    if SMS_PAUSE_STATE_FILE.exists():
        try:
            with open(SMS_PAUSE_STATE_FILE, "r") as f:
                state = json.load(f)
                for user, defaults in default_state.items():
                    if user not in state or not isinstance(state[user], dict):
                        state[user] = defaults.copy()
                    state[user]["skip_next"] = bool(state[user].get("skip_next", False))
                    state[user]["phone"] = state[user].get("phone") or defaults["phone"]
                return state
        except Exception as e:
            logger.error(f"Failed to load SMS pause state: {e}")
            return default_state

    # One-time migration from legacy boolean snooze state.
    if SNOOZE_FILE.exists():
        try:
            with open(SNOOZE_FILE, "r") as f:
                legacy = json.load(f)
            migrated = default_state.copy()
            for user in ["sean", "linda"]:
                migrated[user]["skip_next"] = bool(legacy.get(user, False))
            save_sms_pause_state(migrated)
            return migrated
        except Exception as e:
            logger.error(f"Failed to migrate legacy snooze state: {e}")

    save_sms_pause_state(default_state)
    return default_state


def save_sms_pause_state(state):
    """Persist per-user SMS pause state."""
    try:
        with open(SMS_PAUSE_STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save SMS pause state: {e}")


def set_sms_pause_state(user: str, skip_next: bool):
    """Set skip-next state for one user."""
    state = load_sms_pause_state()
    if user not in state:
        return state
    state[user]["skip_next"] = bool(skip_next)
    save_sms_pause_state(state)
    return state


def reset_all_sms_pause_state():
    """Reset skip-next flags for all users after each unlock action."""
    state = load_sms_pause_state()
    for user in state:
        state[user]["skip_next"] = False
    save_sms_pause_state(state)
    logger.info("🔄 Reset all SMS pause flags to false after unlock")


def get_name_for_phone(phone_number):
    """Get recipient name for a phone number."""
    normalized = normalize_phone_number(phone_number)
    return PHONE_TO_NAME.get(normalized)


def is_sms_paused_for_next_unlock(phone_number):
    """Check if a phone number is marked 'skip on next unlock'."""
    name = get_name_for_phone(phone_number)
    if not name:
        return False
    state = load_sms_pause_state()
    return bool(state.get(name, {}).get("skip_next", False))


# =============================================================================
# Event Logging
# =============================================================================


def load_events():
    """
    Load gate unlock events from file.

    Returns list of event objects with 'timestamp' field.
    Creates file with empty event list if it doesn't exist.
    """
    if not EVENTS_FILE.exists():
        save_events([])
        return []

    try:
        with open(EVENTS_FILE, "r") as f:
            events = json.load(f)
            # Validate events format
            if not isinstance(events, list):
                logger.error(
                    f"Invalid events format: expected array, got {type(events)}"
                )
                return []
            return events
    except Exception as e:
        logger.error(f"Failed to load events: {e}")
        return []


def save_events(events):
    """Save events to file."""
    try:
        with open(EVENTS_FILE, "w") as f:
            json.dump(events, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save events: {e}")


def append_event(timestamp):
    """
    Add a new gate unlock event to the event log.

    Events are stored in chronological order (newest at the end).
    """
    events = load_events()
    events.append({"timestamp": timestamp})
    save_events(events)


def parse_event_timestamps():
    """Parse unlock event timestamps into timezone-aware datetimes."""
    parsed = []
    for event in load_events():
        ts_str = event.get("timestamp")
        if not ts_str:
            continue
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00")).astimezone(
                TZ_DALLAS
            )
            parsed.append(ts)
        except Exception as e:
            logger.debug(f"Failed to parse timestamp for event stats: {ts_str}, {e}")
    parsed.sort()
    return parsed


def format_duration(delta: timedelta) -> str:
    """Format a timedelta in a compact human-readable form."""
    total_seconds = int(delta.total_seconds())
    if total_seconds < 60:
        return f"{total_seconds} seconds"
    minutes, seconds = divmod(total_seconds, 60)
    if minutes < 60:
        return f"{minutes} minute{'s' if minutes != 1 else ''} {seconds} second{'s' if seconds != 1 else ''}"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} hour{'s' if hours != 1 else ''} {minutes} minute{'s' if minutes != 1 else ''}"


def get_event_stats():
    """Compute playful diagnostics for internal dashboard cards."""
    parsed = parse_event_timestamps()
    now = datetime.now(TZ_DALLAS)
    seven_days_ago = now - timedelta(days=7)
    total = len(parsed)
    last_event = parsed[-1] if parsed else None
    last_7_days = sum(1 for ts in parsed if ts >= seven_days_ago)

    shortest = None
    if len(parsed) >= 2:
        shortest = min(parsed[i] - parsed[i - 1] for i in range(1, len(parsed)))

    return {
        "total": total,
        "last_7_days": last_7_days,
        "shortest_gap": format_duration(shortest) if shortest else "N/A",
        "last_event": last_event.strftime("%b %-d, %-I:%M %p") if last_event else "Never",
    }


def generate_hourly_unlock_histogram():
    """Generate SVG chart with 24-hour unlock buckets."""
    parsed = parse_event_timestamps()
    if not parsed:
        return None

    counts = [0] * 24
    for ts in parsed:
        counts[ts.hour] += 1

    max_count = max(counts) or 1
    width = 700
    height = 220
    margin_left = 40
    margin_right = 20
    margin_top = 28
    margin_bottom = 34
    bar_area_width = width - margin_left - margin_right
    bar_area_height = height - margin_top - margin_bottom
    bar_width = bar_area_width / 24

    bars = []
    labels = []
    for hour in range(24):
        count = counts[hour]
        x = margin_left + hour * bar_width
        h = (count / max_count) * bar_area_height if max_count > 0 else 0
        y = margin_top + (bar_area_height - h)
        bars.append(
            f'<rect x="{x:.2f}" y="{y:.2f}" width="{max(bar_width - 2, 2):.2f}" height="{h:.2f}" fill="#d97706" rx="2"/>'
        )
        if hour % 3 == 0:
            labels.append(
                f'<text x="{x + bar_width / 2:.2f}" y="{height - 12}" font-size="9" fill="#94a3b8" text-anchor="middle">{hour:02d}</text>'
            )

    y_grid = []
    for i in range(5):
        y = margin_top + i * (bar_area_height / 4)
        tick_val = int(max_count * (1 - i / 4))
        y_grid.append(
            f'<line x1="{margin_left}" y1="{y:.2f}" x2="{width - margin_right}" y2="{y:.2f}" stroke="#334155" stroke-width="1" opacity="0.5"/>'
        )
        y_grid.append(
            f'<text x="{margin_left - 6}" y="{y + 3:.2f}" font-size="9" fill="#94a3b8" text-anchor="end">{tick_val}</text>'
        )

    return "\n".join(
        [
            f'<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">',
            f'<text x="{width/2:.1f}" y="16" font-size="12" font-weight="600" fill="#e2e8f0" text-anchor="middle">Unlocks by Hour (24h)</text>',
            *y_grid,
            *bars,
            *labels,
            f'<line x1="{margin_left}" y1="{margin_top + bar_area_height:.2f}" x2="{width - margin_right}" y2="{margin_top + bar_area_height:.2f}" stroke="#334155" stroke-width="1"/>',
            "</svg>",
        ]
    )


# =============================================================================
# Chart Generation
# =============================================================================
TZ_DALLAS = ZoneInfo("America/Chicago")


def generate_daily_histogram():
    """
    Generate SVG histogram showing events per day over last 60 days.
    Returns SVG string or None if no data.
    """
    events = load_events()
    if not events:
        return None

    today = datetime.now(TZ_DALLAS)
    days_back = 60
    daily_counts = {i: 0 for i in range(days_back)}

    for event in events:
        ts_str = event.get("timestamp")
        if not ts_str:
            continue
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            ts_dallas = ts.astimezone(TZ_DALLAS)
            days_ago = (today - ts_dallas).days
            if 0 <= days_ago < days_back:
                daily_counts[days_ago] += 1
        except Exception as e:
            logger.debug(f"Failed to parse timestamp: {ts_str}, {e}")
            continue

    max_count = max(daily_counts.values()) if daily_counts else 1
    chart_width = 600
    chart_height = 200
    bar_width = (chart_width - 140) / days_back
    margin_left = 80
    margin_bottom = 30
    margin_top = 30

    svg_parts = [
        f'<svg width="{chart_width}" height="{chart_height}" xmlns="http://www.w3.org/2000/svg">',
        f"</svg>",
    ]

    bars = []
    day_labels = []

    for day_idx in range(days_back):
        # Draw oldest -> newest from left to right.
        days_ago = days_back - 1 - day_idx
        count = daily_counts.get(days_ago, 0)
        x = margin_left + day_idx * bar_width
        if max_count > 0:
            bar_height = (count / max_count) * (
                chart_height - margin_bottom - margin_top
            )
        else:
            bar_height = 0
        y = chart_height - margin_bottom - bar_height

        if count > 0:
            opacity = min(0.3 + (count / max_count) * 0.7, 1)
            bars.append(
                f'<rect x="{x}" y="{y}" width="{bar_width - 1}" height="{bar_height}" '
                f'fill="#d97706" opacity="{opacity}" rx="2"/>'
            )
        else:
            bars.append(
                f'<rect x="{x}" y="{chart_height - margin_bottom - 1}" width="{bar_width - 1}" height="1" '
                f'fill="#334155" opacity="0.8" rx="2"/>'
            )

        if day_idx == 0:
            start_date = today - timedelta(days=59)
            day_labels.append(
                f'<text x="{x + bar_width / 2}" y="{chart_height - 10}" font-size="10" fill="#94a3b8" text-anchor="middle">{start_date.strftime("%b %-d")}</text>'
            )
        elif day_idx == 29:
            day_labels.append(
                f'<text x="{x + bar_width / 2}" y="{chart_height - 10}" font-size="10" fill="#94a3b8" text-anchor="middle">30d ago</text>'
            )
        elif day_idx == 59:
            day_labels.append(
                f'<text x="{x + bar_width / 2}" y="{chart_height - 10}" font-size="10" fill="#94a3b8" text-anchor="middle">Today</text>'
            )

    svg_content = [
        '<svg width="600" height="200" xmlns="http://www.w3.org/2000/svg">',
        f'<text x="300" y="20" font-size="12" font-weight="600" fill="#e2e8f0" text-anchor="middle">Gate Unlocks - Last 60 Days</text>',
    ]

    if max_count > 0:
        y_axis_labels = [
            f'<text x="70" y="{margin_top + i * (chart_height - margin_bottom - margin_top) / 4}" font-size="9" fill="#94a3b8" text-anchor="end">{int(max_count * (1 - i / 4))}</text>'
            for i in range(5)
        ]
        svg_content.extend(y_axis_labels)

    svg_content.extend(bars)
    svg_content.extend(day_labels)
    svg_content.extend(
        [
            '<line x1="80" y1="170" x2="590" y2="170" stroke="#334155" stroke-width="1"/>',
            "</svg>",
        ]
    )

    return "\n".join(svg_content)


def generate_polar_chart():
    """
    Generate SVG polar chart showing hourly distribution of unlock events.
    Returns SVG string or None if no data.
    """
    events = load_events()
    if not events:
        return None

    hourly_counts = {h: 0 for h in range(24)}
    total_events = 0

    for event in events:
        ts_str = event.get("timestamp")
        if not ts_str:
            continue
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            ts_dallas = ts.astimezone(TZ_DALLAS)
            hour = ts_dallas.hour
            hourly_counts[hour] += 1
            total_events += 1
        except Exception as e:
            logger.debug(f"Failed to parse timestamp: {ts_str}, {e}")
            continue

    if total_events == 0:
        return None

    svg_size = 200
    center = svg_size / 2
    outer_radius = 70
    inner_radius = 20
    segment_angle = 360 / 24

    max_count = max(hourly_counts.values())

    svg_parts = [
        f'<svg width="{svg_size}" height="{svg_size}" xmlns="http://www.w3.org/2000/svg">',
    ]

    for hour in range(24):
        count = hourly_counts[hour]

        if max_count > 0:
            outer_r = inner_radius + (count / max_count) * (outer_radius - inner_radius)
        else:
            outer_r = inner_radius

        base_angle_deg = (hour + 18) * segment_angle

        if count > 0:
            opacity = min(0.2 + (count / max_count) * 0.6, 1)
        else:
            opacity = 0.1

        start_x = center
        start_y = center
        end_y = center - outer_r + 5

        svg_parts.append(
            f'<line x1="{start_x}" y1="{start_y}" x2="{start_x}" y2="{end_y}" '
            f'stroke="#d97706" stroke-width="6" stroke-opacity="{opacity}" '
            f'stroke-linecap="round" transform="rotate({base_angle_deg - 90} {center} {center})"/>'
        )

    for hour in range(0, 24, 6):
        if hour == 0:
            label_text = "12am"
        elif hour == 6:
            label_text = "6am"
        elif hour == 12:
            label_text = "12pm"
        elif hour == 18:
            label_text = "6pm"
        else:
            continue

        svg_parts.append(
            f'<text x="{center}" y="{12 + hour // 6 * 50}" font-size="9" fill="#94a3b8" text-anchor="middle">{label_text}</text>'
        )

    svg_parts.extend(
        [
            f'<text x="{center}" y="{center + 5}" font-size="10" font-weight="600" fill="#e2e8f0" text-anchor="middle">Unlock Times</text>',
            "</svg>",
        ]
    )

    return "\n".join(svg_parts)


# Initialize opt-ins for configured numbers (auto-opt-in for initial setup)
def initialize_opt_ins():
    """
    Auto-opt-in numbers from NOTIFY_NUMBERS if they're not already tracked.
    Respects existing opt-out status - will NOT re-opt-in numbers that have opted out.
    """
    opt_ins = load_opt_ins()
    updated = False

    for phone_number in NOTIFY_NUMBERS:
        # Only opt-in if not in the system at all (not if they've opted out)
        if phone_number not in opt_ins:
            opt_in(phone_number, source="initial_config")
            updated = True
            # Send welcome message for new opt-ins
            send_welcome_message(phone_number)
            logger.info(
                f"📋 Auto-opted-in {phone_number} (new number in NOTIFY_NUMBERS)"
            )
        elif opt_ins[phone_number].get("status") == "opted_out":
            logger.info(
                f"⚠️  {phone_number} is in NOTIFY_NUMBERS but is opted out - respecting opt-out status"
            )
        elif opt_ins[phone_number].get("status") == "opted_in":
            logger.debug(f"✅ {phone_number} already opted in")

    if updated:
        logger.info("📋 Initialized opt-ins for configured notification numbers")


def send_welcome_message(phone_number):
    """Send a welcome/opt-in confirmation message to a newly opted-in number."""
    if not telnyx_client or not TELNYX_PHONE_NUMBER:
        return

    welcome_text = (
        "Welcome to Let Food Into Civic gate unlock notifications! "
        "You'll receive alerts when deliveries arrive. "
        "Reply STOP to unsubscribe, HELP for assistance."
    )

    try:
        telnyx_client.messages.send(
            from_=TELNYX_PHONE_NUMBER,
            to=phone_number,
            text=welcome_text,
        )
        logger.info(f"📧 Welcome message sent to {phone_number}")
    except Exception as e:
        logger.error(f"❌ Failed to send welcome message to {phone_number}: {e}")


# Log normalized phone numbers on startup
if NOTIFY_NUMBERS_RAW:
    logger.info(f"📱 Phone number normalization:")
    for raw, normalized in zip(NOTIFY_NUMBERS_RAW, NOTIFY_NUMBERS):
        if raw != normalized:
            logger.info(f"   {raw} → {normalized}")
        else:
            logger.debug(f"   {normalized} (already normalized)")

# Initialize on startup
if NOTIFY_NUMBERS:
    initialize_opt_ins()


# =============================================================================
# SMS Notification
# =============================================================================


def send_sms_notifications(caller: str, timestamp: datetime):
    """
    Send SMS notifications to configured phone numbers.

    Runs in a background thread to not block the webhook response.
    Respects per-user "skip next unlock" state and always resets state after unlock.
    """
    logger.info(
        f"📱 SMS notification function called for caller: {caller} at {timestamp}"
    )

    success_count = 0
    failure_count = 0
    skipped_count = 0

    try:
        if not NOTIFY_NUMBERS:
            logger.warning(
                "⚠️  No notification numbers configured (NOTIFY_NUMBERS is empty)"
            )
            return

        if not TELNYX_PHONE_NUMBER:
            logger.warning(
                "⚠️  No Telnyx phone number configured (TELNYX_PHONE_NUMBER is empty)"
            )
            return

        if not telnyx_client:
            logger.warning("⚠️  Telnyx client not initialized (API key missing)")
            return

        message = "the civic callbox was answered and I did 5s, <3 lfic."
        logger.info(f"📝 SMS message: {message}")
        logger.info(
            f"📋 Sending to {len(NOTIFY_NUMBERS)} recipient(s): {NOTIFY_NUMBERS}"
        )

        for phone_number in NOTIFY_NUMBERS:
            # Check per-user skip-next flag first.
            name = get_name_for_phone(phone_number)
            if is_sms_paused_for_next_unlock(phone_number):
                logger.info(
                    f"⏭️ Skipping SMS for {name.capitalize() if name else phone_number} (skip_next=true)"
                )
                skipped_count += 1
                continue

            # Always check durable opt-in/opt-out record before sending.
            opt_ins = load_opt_ins()
            phone_status = opt_ins.get(phone_number, {}).get("status")

            if phone_status != "opted_in":
                if phone_status == "opted_out":
                    logger.warning(
                        f"🛑 Skipping SMS to {phone_number} - opted out (respecting opt-out status)"
                    )
                else:
                    logger.warning(
                        f"⚠️  Skipping SMS to {phone_number} - not opted in (status: {phone_status or 'unknown'})"
                    )
                failure_count += 1
                continue

            try:
                logger.info(f"📤 Attempting to send SMS to {phone_number}...")
                telnyx_client.messages.send(
                    from_=TELNYX_PHONE_NUMBER,
                    to=phone_number,
                    text=message,
                )
                logger.info(f"✅ SMS successfully sent to {phone_number}")
                success_count += 1
            except Exception as e:
                logger.error(
                    f"❌ Failed to send SMS to {phone_number}: {e}", exc_info=True
                )
                failure_count += 1
    finally:
        # Unlock action happened, so clear all skip-next flags.
        reset_all_sms_pause_state()
        logger.info(
            f"📊 SMS summary: {success_count} succeeded, {failure_count} failed, {skipped_count} skipped out of {len(NOTIFY_NUMBERS)} total"
        )


def send_notifications_async(caller: str):
    """Send notifications in a background thread."""
    thread = threading.Thread(
        target=send_sms_notifications, args=(caller, datetime.now()), daemon=True
    )
    thread.start()


# =============================================================================
# TeXML Generation
# =============================================================================

# URL to the 2-second DTMF tone audio file
DTMF_AUDIO_URL = os.getenv(
    "DTMF_AUDIO_URL", "https://let-food-into-civic.contrived.com/static/dtmf5-2sec.wav"
)


def generate_unlock_texml() -> str:
    """
    Generate TeXML/TwiML response that plays DTMF tones to unlock the gate.

    The call box expects:
    - Tone "5" held for ~2 seconds
    - Pause for 0.5 seconds
    - Repeat 6 times

    We use a pre-recorded DTMF audio file because TwiML's <Play digits>
    only supports short (~100ms) tones. The audio file contains a 2-second
    DTMF "5" tone (770 Hz + 1336 Hz).
    """
    # Build the XML response using audio file for proper duration
    xml_parts = ['<?xml version="1.0" encoding="UTF-8"?>', "<Response>"]

    for i in range(ITERATIONS):
        # Play the DTMF tone audio file
        xml_parts.append(f"    <Play>{DTMF_AUDIO_URL}</Play>")

        # Add pause between iterations (skip pause after last iteration)
        if i < ITERATIONS - 1:
            xml_parts.append(f'    <Pause length="{PAUSE_DURATION}"/>')

    # Hang up after we're done
    xml_parts.append("    <Hangup/>")
    xml_parts.append("</Response>")

    return "\n".join(xml_parts)


# =============================================================================
# Webhook Endpoints
# =============================================================================


@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint for container orchestration."""
    return {
        "status": "healthy",
        "service": "let-food-into-civic",
        "notifications_configured": len(NOTIFY_NUMBERS) > 0,
        "telnyx_configured": bool(TELNYX_API_KEY),
    }, 200


@app.route("/webhook/voice", methods=["POST", "GET"])
def handle_incoming_call():
    """
    Webhook endpoint for incoming voice calls.

    Telnyx will POST to this endpoint when a call comes in.
    We respond with TeXML instructions to play DTMF tones,
    and send SMS notifications.
    """
    # Log the incoming call with full details
    caller = request.values.get("From", request.values.get("from", "unknown"))
    to_number = request.values.get("To", request.values.get("to", "unknown"))
    call_id = request.values.get("CallSid", request.values.get("call_sid", "unknown"))

    logger.info("=" * 60)
    logger.info(f"📞 INCOMING CALL RECEIVED")
    logger.info(f"   Call ID: {call_id}")
    logger.info(f"   From: {caller}")
    logger.info(f"   To: {to_number}")
    logger.info(f"   Timestamp: {datetime.now().isoformat()}")
    logger.info(
        f"🔓 Generating unlock sequence: DTMF tone '{UNLOCK_DIGIT}' x {ITERATIONS} iterations"
    )

    # Record gate unlock event for historical analysis
    event_timestamp = datetime.utcnow().isoformat() + "Z"
    append_event(event_timestamp)

    # Send SMS notifications asynchronously
    logger.info(f"📱 Initiating SMS notification to {len(NOTIFY_NUMBERS)} recipient(s)")
    send_notifications_async(caller)

    # Generate and return the TeXML response
    texml = generate_unlock_texml()
    logger.debug(f"Response TeXML:\n{texml}")
    logger.info(f"✅ TeXML response generated and sent")
    logger.info("=" * 60)

    return Response(texml, mimetype="application/xml")


@app.route("/webhook/sms", methods=["POST", "GET"])
def handle_incoming_sms():
    """
    Webhook endpoint for incoming SMS messages (STOP, HELP, START).

    Telnyx will POST to this endpoint when someone replies to our SMS.
    We handle opt-in/opt-out commands here.

    NOTE: Telnyx sends webhooks for ALL message events (inbound, outbound,
    delivery confirmations, etc.). We only process inbound messages.
    """
    # Log all incoming requests for debugging
    logger.info("=" * 60)
    logger.info(f"📱 SMS WEBHOOK RECEIVED")
    logger.info(f"   Method: {request.method}")
    logger.info(f"   Headers: {dict(request.headers)}")
    logger.info(f"   JSON: {request.get_json()}")
    logger.info(f"   Form: {dict(request.form)}")
    logger.info(f"   Args: {dict(request.args)}")

    # Get message data from Telnyx webhook
    data = request.get_json() or request.form.to_dict() or request.args.to_dict()

    # Check event type and direction - only process inbound messages
    # Telnyx sends webhooks for: message.received, message.sent, message.finalized, etc.
    event_type = data.get("data", {}).get("event_type", "")
    direction = data.get("data", {}).get("payload", {}).get("direction", "")

    # Skip non-inbound messages (outbound confirmations, delivery receipts, etc.)
    if direction == "outbound":
        logger.info(
            f"⏭️  Skipping outbound message event (event_type: {event_type}, direction: {direction})"
        )
        logger.info("=" * 60)
        return jsonify({"status": "skipped", "reason": "outbound message"}), 200

    # Also skip if event type is not message.received (delivery confirmations, etc.)
    if event_type and event_type != "message.received":
        logger.info(
            f"⏭️  Skipping non-received message event (event_type: {event_type})"
        )
        logger.info("=" * 60)
        return jsonify(
            {"status": "skipped", "reason": f"event_type: {event_type}"}
        ), 200

    # Telnyx webhook format
    from_number = data.get("data", {}).get("payload", {}).get("from", {})
    if isinstance(from_number, dict):
        from_number = from_number.get("phone_number", "unknown")
    else:
        from_number = data.get("from", data.get("From", "unknown"))

    to_number = (
        data.get("data", {}).get("payload", {}).get("to", [{}])[0]
        if isinstance(data.get("data", {}).get("payload", {}).get("to", []), list)
        else {}
    )
    if isinstance(to_number, dict):
        to_number = to_number.get("phone_number", "unknown")
    else:
        to_number = data.get("to", data.get("To", "unknown"))

    # Extra safety: skip if from_number is our own Telnyx number (would cause send-to-self error)
    if from_number == TELNYX_PHONE_NUMBER:
        logger.info(f"⏭️  Skipping message from our own number ({from_number})")
        logger.info("=" * 60)
        return jsonify({"status": "skipped", "reason": "message from self"}), 200

    # Get message text - always normalize to uppercase for case-insensitive matching
    message_text = data.get("data", {}).get("payload", {}).get("text", "")
    if not message_text:
        message_text = data.get("text", data.get("Body", ""))
    # Always convert to uppercase for case-insensitive command matching
    message_text = message_text.strip().upper() if message_text else ""

    logger.info("=" * 60)
    logger.info(f"📱 INCOMING SMS RECEIVED")
    logger.info(f"   From: {from_number}")
    logger.info(f"   To: {to_number}")
    logger.info(f"   Message: {message_text}")
    logger.info(f"   Timestamp: {datetime.now().isoformat()}")

    # Handle commands
    response_text = None

    if message_text == "STOP":
        opt_out(from_number, source="sms_reply")
        response_text = "You have been unsubscribed from gate unlock notifications. Reply START to resubscribe."
        logger.info(f"🛑 Processed STOP request from {from_number}")

    elif message_text == "HELP":
        response_text = (
            "Let Food Into Civic: Automatic gate unlock notifications for deliveries. "
            "Very low volume - you'll only get notified when someone uses the callbox. "
            "No action needed - just kick back and enjoy the rare notification! "
            "Reply STOP to unsubscribe."
        )
        logger.info(f"ℹ️  Processed HELP request from {from_number}")

    elif message_text in ["START", "YES", "OPTIN", "SUBSCRIBE"]:
        opt_in(from_number, source="sms_reply")
        response_text = "You have been subscribed to gate unlock notifications. Reply STOP to unsubscribe."
        logger.info(f"✅ Processed START/OPT-IN request from {from_number}")

    else:
        logger.info(f"❓ Unknown message from {from_number}: {message_text}")
        response_text = (
            "Unknown command. Reply STOP to unsubscribe, HELP for assistance."
        )

    # Send response if we have one
    if response_text and telnyx_client and TELNYX_PHONE_NUMBER:
        try:
            telnyx_client.messages.send(
                from_=TELNYX_PHONE_NUMBER,
                to=from_number,
                text=response_text,
            )
            logger.info(f"📤 Sent response to {from_number}")
        except Exception as e:
            logger.error(f"❌ Failed to send response SMS: {e}", exc_info=True)

    logger.info("=" * 60)

    return jsonify({"status": "processed"}), 200


def render_snooze_ui():
    """Render the internal dashboard for home-network clients."""
    state = load_sms_pause_state()
    linda_snoozed = bool(state.get("linda", {}).get("skip_next", False))
    sean_snoozed = bool(state.get("sean", {}).get("skip_next", False))

    def format_phone(phone):
        """Format phone number nicely: +14693059242 -> (469) 305-9242"""
        if phone.startswith("+1") and len(phone) == 12:
            return f"({phone[2:5]}) {phone[5:8]}-{phone[8:]}"
        return phone

    linda_phone = format_phone(NAME_TO_PHONE.get("linda", ""))
    sean_phone = format_phone(NAME_TO_PHONE.get("sean", ""))

    linda_status = "Skip next unlock" if linda_snoozed else "SMS enabled"
    sean_status = "Skip next unlock" if sean_snoozed else "SMS enabled"
    stats = get_event_stats()
    hourly_chart = generate_hourly_unlock_histogram()

    return f'''
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>let-food-into-civic</title>
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
        <link href="https://fonts.googleapis.com/css2?family=Source+Serif+4:opsz,wght@8..60,400;8..60,600&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
        <style>
            * {{ box-sizing: border-box; margin: 0; padding: 0; }}

            :root {{
                --bg: #111827;
                --surface: #1f2937;
                --surface-2: #0f172a;
                --text: #e5e7eb;
                --text-secondary: #cbd5e1;
                --text-muted: #94a3b8;
                --accent: #f59e0b;
                --border: #334155;
                --success: #22c55e;
                --card-shadow: rgba(2, 6, 23, 0.35);
            }}

            body {{
                font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
                background: radial-gradient(circle at top, #1f2937 0%, var(--bg) 62%);
                color: var(--text);
                min-height: 100vh;
                line-height: 1.6;
                font-size: 16px;
            }}

            .container {{
                max-width: 920px;
                margin: 0 auto;
                padding: 48px 24px;
            }}

            header {{
                text-align: center;
                margin-bottom: 40px;
            }}

            .logo {{
                font-size: 2.2rem;
                margin-bottom: 16px;
            }}

            h1 {{
                font-family: 'Source Serif 4', Georgia, serif;
                font-size: 1.75rem;
                font-weight: 600;
                margin-bottom: 8px;
                letter-spacing: -0.02em;
            }}

            .subtitle {{
                color: var(--text-secondary);
                font-size: 0.95rem;
            }}

            .internal-banner {{
                background: rgba(245, 158, 11, 0.12);
                border: 1px solid rgba(245, 158, 11, 0.5);
                padding: 16px 20px;
                margin-bottom: 32px;
                border-radius: 10px;
                font-size: 0.9rem;
                color: #fde68a;
            }}

            .stats-grid {{
                display: grid;
                grid-template-columns: repeat(3, minmax(0, 1fr));
                gap: 12px;
                margin-bottom: 24px;
            }}

            .stat-card {{
                background: var(--surface);
                border: 1px solid var(--border);
                border-radius: 12px;
                padding: 14px 16px;
                box-shadow: 0 8px 24px var(--card-shadow);
            }}

            .stat-label {{
                font-size: 0.78rem;
                text-transform: uppercase;
                letter-spacing: 0.06em;
                color: var(--text-muted);
                margin-bottom: 6px;
            }}

            .stat-value {{
                font-size: 1.35rem;
                font-weight: 600;
                color: var(--text);
            }}

            .team-grid {{
                display: grid;
                grid-template-columns: repeat(2, minmax(0, 1fr));
                gap: 16px;
                margin-bottom: 28px;
            }}

            .recipient-card {{
                background: var(--surface-2);
                border: 1px solid var(--border);
                border-radius: 12px;
                padding: 24px;
                box-shadow: 0 8px 24px var(--card-shadow);
            }}

            .recipient-header {{
                display: flex;
                gap: 14px;
                align-items: flex-start;
            }}

            .avatar {{
                width: 84px;
                height: 84px;
                border-radius: 12px;
                object-fit: cover;
                object-position: center;
                border: 1px solid var(--border);
                flex-shrink: 0;
            }}

            .recipient-name {{
                font-size: 1.25rem;
                font-weight: 600;
            }}

            .recipient-phone {{
                color: var(--text-muted);
                font-size: 0.9rem;
            }}

            .pause-form {{
                margin-top: 14px;
            }}

            .pause-toggle {{
                display: inline-flex;
                align-items: center;
                gap: 10px;
                cursor: pointer;
                color: var(--text-secondary);
                font-size: 0.93rem;
            }}

            .pause-toggle input[type="checkbox"] {{
                width: 18px;
                height: 18px;
                accent-color: var(--accent);
                cursor: pointer;
            }}

            .helper-text {{
                margin-top: 10px;
                color: var(--text-muted);
                font-size: 0.84rem;
            }}

            .status-row {{
                display: flex;
                justify-content: flex-start;
                gap: 8px;
                align-items: center;
                margin-top: 12px;
                padding-top: 12px;
                border-top: 1px solid var(--border);
            }}

            .status-label {{
                font-size: 0.85rem;
                color: var(--text-secondary);
            }}

            .status-value {{
                font-size: 0.85rem;
                font-weight: 500;
            }}

            .status-value.active {{
                color: var(--success);
            }}

            .status-value.snoozed {{
                color: #fbbf24;
            }}

            .charts-section {{
                margin-top: 20px;
            }}

            .charts-section h2 {{
                font-family: \'Source Serif 4\', Georgia, serif;
                font-size: 1.25rem;
                font-weight: 600;
                margin-bottom: 20px;
                text-align: center;
                color: var(--text);
            }}

            .chart-container {{
                margin-bottom: 32px;
                text-align: center;
                background: var(--surface-2);
                border: 1px solid var(--border);
                border-radius: 12px;
                padding: 20px 12px 12px;
                box-shadow: 0 8px 24px var(--card-shadow);
            }}

            .chart-container svg {{
                max-width: 100%;
                height: auto;
            }}

            footer {{
                text-align: center;
                margin-top: 40px;
                color: var(--text-muted);
                font-size: 0.8rem;
            }}

            @media (max-width: 600px) {{
                .stats-grid {{
                    grid-template-columns: 1fr 1fr;
                }}

                .team-grid {{
                    grid-template-columns: 1fr;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <header>
                <div class="logo">🏠</div>
                <h1>let-food-into-civic</h1>
                <p class="subtitle">Internal dashboard for home network controls</p>
            </header>

            <div class="internal-banner">
                You are on the home network. Check a box to skip SMS for the <strong>next unlock only</strong>. After any unlock event, both boxes reset automatically.
            </div>

            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-label">Total Unlocks</div>
                    <div class="stat-value">{stats["total"]}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Last 7 Days</div>
                    <div class="stat-value">{stats["last_7_days"]}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Shortest Gap</div>
                    <div class="stat-value" style="font-size: 1.05rem;">{stats["shortest_gap"]}</div>
                </div>
            </div>

            <div class="team-grid">
                <div class="recipient-card">
                    <div class="recipient-header">
                        <img src="/avatars/linda.png" alt="Linda avatar" class="avatar">
                        <div>
                            <div class="recipient-name">Linda</div>
                            <div class="recipient-phone">{linda_phone}</div>
                            <form method="POST" action="/internal/toggle-sms-pause" class="pause-form">
                                <input type="hidden" name="user" value="linda">
                                <label class="pause-toggle">
                                    <input type="checkbox" name="skip_next" value="true" {"checked" if linda_snoozed else ""} onchange="this.form.submit()">
                                    <span>Skip SMS on next unlock</span>
                                </label>
                            </form>
                            <p class="helper-text">Check to skip SMS notification for the next gate unlock only. Resets automatically after each unlock.</p>
                        </div>
                    </div>
                    <div class="status-row">
                        <span class="status-label">Status</span>
                        <span class="status-value {"snoozed" if linda_snoozed else "active"}">{linda_status}</span>
                    </div>
                </div>

                <div class="recipient-card">
                    <div class="recipient-header">
                        <img src="/avatars/sean.png" alt="Sean avatar" class="avatar">
                        <div>
                            <div class="recipient-name">Sean</div>
                            <div class="recipient-phone">{sean_phone}</div>
                            <form method="POST" action="/internal/toggle-sms-pause" class="pause-form">
                                <input type="hidden" name="user" value="sean">
                                <label class="pause-toggle">
                                    <input type="checkbox" name="skip_next" value="true" {"checked" if sean_snoozed else ""} onchange="this.form.submit()">
                                    <span>Skip SMS on next unlock</span>
                                </label>
                            </form>
                            <p class="helper-text">Check to skip SMS notification for the next gate unlock only. Resets automatically after each unlock.</p>
                        </div>
                    </div>
                    <div class="status-row">
                        <span class="status-label">Status</span>
                        <span class="status-value {"snoozed" if sean_snoozed else "active"}">{sean_status}</span>
                    </div>
                </div>
            </div>

            <div class="charts-section">
                <h2>Fun Team Diagnostics</h2>
                <div class="chart-container">
                    {hourly_chart or "<p style='color: var(--text-muted); font-size: 0.9rem;'>No unlock events yet.</p>"}
                </div>
            </div>

            <footer>
                <p>Let Food Into Civic</p>
                <p>Local network access only</p>
                <p style="margin-top: 8px;">Most recent unlock: {stats["last_event"]}</p>
                <p style="margin-top: 16px;">
                    <a href="/?view=external" style="color: var(--text-muted); text-decoration: none; font-size: 0.85rem; padding: 8px 16px; border: 1px solid var(--border); border-radius: 6px; display: inline-block;">See what visitors see</a>
                </p>
            </footer>
        </div>
    </body>
    </html>
    '''


def render_public_landing_page():
    """Render the public landing page for external visitors."""
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>let-food-into-civic</title>
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
        <link href="https://fonts.googleapis.com/css2?family=Source+Serif+4:opsz,wght@8..60,400;8..60,600&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
        <style>
            * { box-sizing: border-box; margin: 0; padding: 0; }
            
            :root {
                --bg: #fafaf9;
                --bg-alt: #ffffff;
                --text: #1c1917;
                --text-secondary: #57534e;
                --text-muted: #a8a29e;
                --accent: #b45309;
                --accent-light: #fef3c7;
                --border: #e7e5e4;
                --link: #0369a1;
            }
            
            body {
                font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
                background: var(--bg);
                color: var(--text);
                min-height: 100vh;
                line-height: 1.7;
                font-size: 16px;
            }
            
            .container {
                max-width: 680px;
                margin: 0 auto;
                padding: 80px 24px;
            }
            
            header {
                text-align: center;
                margin-bottom: 64px;
                padding-bottom: 48px;
                border-bottom: 1px solid var(--border);
            }
            
            .logo {
                font-size: 2.5rem;
                margin-bottom: 20px;
                display: inline-block;
            }
            
            h1 {
                font-family: 'Source Serif 4', Georgia, serif;
                font-size: 2.25rem;
                font-weight: 600;
                margin-bottom: 12px;
                letter-spacing: -0.02em;
                color: var(--text);
            }
            
            .tagline {
                color: var(--text-secondary);
                font-size: 1.1rem;
            }
            
            .content {
                margin-bottom: 48px;
            }
            
            .content h2 {
                font-family: 'Source Serif 4', Georgia, serif;
                font-size: 1.5rem;
                font-weight: 600;
                margin-bottom: 20px;
                margin-top: 48px;
                color: var(--text);
            }
            
            .content h2:first-child {
                margin-top: 0;
            }
            
            .content p {
                color: var(--text-secondary);
                margin-bottom: 20px;
            }
            
            .content ul {
                color: var(--text-secondary);
                margin-bottom: 20px;
                margin-left: 24px;
            }
            
            .content li {
                margin-bottom: 8px;
            }
            
            .highlight-box {
                background: var(--accent-light);
                border-left: 4px solid var(--accent);
                padding: 20px 24px;
                margin: 32px 0;
                border-radius: 0 8px 8px 0;
            }
            
            .highlight-box p {
                color: var(--text);
                margin-bottom: 0;
            }
            
            .links-section {
                background: var(--bg-alt);
                border: 1px solid var(--border);
                border-radius: 12px;
                padding: 32px;
                margin: 48px 0;
            }
            
            .links-section h3 {
                font-family: 'Source Serif 4', Georgia, serif;
                font-size: 1.1rem;
                font-weight: 600;
                margin-bottom: 20px;
                color: var(--text);
            }
            
            .links-grid {
                display: grid;
                gap: 16px;
            }
            
            .links-grid a {
                display: flex;
                align-items: center;
                gap: 12px;
                padding: 16px 20px;
                background: var(--bg);
                border: 1px solid var(--border);
                border-radius: 8px;
                color: var(--text);
                text-decoration: none;
                transition: all 0.2s;
            }
            
            .links-grid a:hover {
                border-color: var(--accent);
                background: var(--accent-light);
            }
            
            .links-grid a svg {
                width: 24px;
                height: 24px;
                color: var(--accent);
                flex-shrink: 0;
            }
            
            .links-grid .link-content {
                flex: 1;
            }
            
            .links-grid .link-title {
                font-weight: 600;
                margin-bottom: 2px;
            }
            
            .links-grid .link-desc {
                font-size: 0.875rem;
                color: var(--text-muted);
            }
            
            footer {
                text-align: center;
                margin-top: 64px;
                padding-top: 32px;
                border-top: 1px solid var(--border);
                color: var(--text-muted);
                font-size: 0.875rem;
            }
            
            footer a {
                color: var(--text-secondary);
                text-decoration: none;
            }
            
            footer a:hover {
                color: var(--accent);
            }
            
            footer p {
                margin-bottom: 8px;
            }
            
            @media (max-width: 600px) {
                .container {
                    padding: 48px 20px;
                }
                h1 {
                    font-size: 1.75rem;
                }
                .content h2 {
                    font-size: 1.25rem;
                }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <header>
                <div class="logo">🏠</div>
                <h1>Let Food Into Civic</h1>
                <p class="tagline">Home Delivery Notification Service</p>
            </header>
            
            <div class="content">
                <h2>About This Service</h2>
                <p>
                    Welcome to <strong>Let Food Into Civic</strong>, a home notification service 
                    designed and operated by Contrived LLC. This service provides real-time SMS 
                    notifications to household members when deliveries arrive at their residence.
                </p>
                <p>
                    In today's busy world, keeping track of package and food deliveries can be 
                    challenging. Whether you're working from home, managing a household, or simply 
                    want to know when your order has arrived, timely notifications help ensure you 
                    never miss an important delivery.
                </p>
                
                <h2>Who We Serve</h2>
                <p>
                    This is a <strong>private, non-commercial service</strong> created specifically 
                    for personal household use. We provide delivery notifications exclusively to 
                    household members who have explicitly opted in to receive text message alerts. 
                    Our service is not available to the general public and operates solely for 
                    the benefit of registered family members at a single residential address.
                </p>
                
                <div class="highlight-box">
                    <p>
                        <strong>Privacy First:</strong> We take your privacy seriously. Only household 
                        members who have provided explicit consent receive notifications. Your phone 
                        number and personal information are never shared with third parties or used 
                        for marketing purposes.
                    </p>
                </div>
                
                <h2>How Notifications Work</h2>
                <p>
                    When a delivery arrives at the registered address, our system automatically 
                    sends an SMS notification to all opted-in household members. These notifications 
                    include the time of the delivery event so you always know exactly when something 
                    has arrived.
                </p>
                <p>
                    Message frequency varies based on delivery activity at your residence. Most 
                    households can expect to receive between 10-30 messages per month, though this 
                    depends entirely on how many deliveries you receive. Standard message and data 
                    rates from your mobile carrier may apply.
                </p>
                
                <h2>Your Rights &amp; Choices</h2>
                <p>
                    We believe in giving you complete control over your notification preferences. 
                    As a registered user of this service, you have several important rights:
                </p>
                <ul>
                    <li><strong>Opt-Out Anytime:</strong> Simply reply STOP to any message to immediately unsubscribe from all future notifications.</li>
                    <li><strong>Get Help:</strong> Reply HELP to any message for assistance or contact information.</li>
                    <li><strong>Transparency:</strong> We clearly disclose how your information is used in our privacy policy.</li>
                    <li><strong>No Obligations:</strong> Your consent to receive messages is not a condition of any purchase or service.</li>
                </ul>
                
                <h2>About Contrived LLC</h2>
                <p>
                    This service is owned and operated by <strong>Contrived LLC</strong>, a Texas-based 
                    company focused on building practical technology solutions for everyday life. We 
                    created Let Food Into Civic to solve a simple problem: making sure busy families 
                    never miss an important delivery.
                </p>
                <p>
                    For any questions about this service, our company, or how we handle your information, 
                    please don't hesitate to reach out to us at contact@contrived.com.
                </p>
            </div>
            
            <div class="links-section">
                <h3>Important Information</h3>
                <div class="links-grid">
                    <a href="https://let-food-into-civic.contrived.com/sms-consent">
                        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                            <path stroke-linecap="round" stroke-linejoin="round" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
                        </svg>
                        <div class="link-content">
                            <div class="link-title">SMS Consent &amp; Disclosures</div>
                            <div class="link-desc">View our complete SMS messaging terms, CTIA disclosures, and opt-in information</div>
                        </div>
                    </a>
                    <a href="https://contrived.com/privacy">
                        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                            <path stroke-linecap="round" stroke-linejoin="round" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
                        </svg>
                        <div class="link-content">
                            <div class="link-title">Privacy Policy</div>
                            <div class="link-desc">Learn how we collect, use, and protect your personal information</div>
                        </div>
                    </a>
                </div>
            </div>
            
            <footer>
                <p>&copy; 2024 <a href="https://contrived.com">Contrived LLC</a>. All rights reserved.</p>
                <p>A home automation service for private, residential use.</p>
                <p style="margin-top: 16px;">
                    <a href="https://contrived.com/privacy">Privacy Policy</a> ·
                    <a href="https://let-food-into-civic.contrived.com/sms-consent">SMS Terms</a> ·
                    <a href="mailto:contact@contrived.com">Contact Us</a>
                </p>
                <p style="margin-top: 16px;">
                    <a href="/?view=local" style="color: var(--text-muted); text-decoration: none; font-size: 0.8rem; padding: 8px 16px; border: 1px solid var(--border); border-radius: 6px; display: inline-block;">View Local Controls</a>
                </p>
            </footer>
        </div>
    </body>
    </html>
    """


@app.route("/avatars/<filename>", methods=["GET"])
def serve_avatar(filename):
    """Serve static avatar images from /app/art for the internal dashboard."""
    allowed = {"sean.png", "linda.png"}
    if filename not in allowed:
        abort(404)
    if not ART_DIR.exists():
        abort(404)
    return send_from_directory(str(ART_DIR), filename)


@app.route("/", methods=["GET"])
def index():
    """
    Home page - shows snooze UI for local network, public landing page for remote.

    Supports ?view= query parameter to override network routing:
    - ?view=external or ?view=public: always show public landing page
    - ?view=internal or ?view=local: require internal network
    """
    view_override = request.args.get("view", "").lower()
    is_internal = is_internal_network(request)

    # Handle view override
    if view_override in {"internal", "local"}:
        if not is_internal:
            # Remote user trying to access local controls
            return jsonify({"error": "Access denied - internal network only"}), 403
        return render_snooze_ui()
    elif view_override in {"external", "public"}:
        # Anyone can view the public page
        return render_public_landing_page()

    # Default: network-driven routing.
    if is_internal:
        return render_snooze_ui()
    return render_public_landing_page()


@app.route("/status", methods=["GET"])
def status():
    """Internal status page showing configuration."""
    notify_status = (
        f"✅ {len(NOTIFY_NUMBERS)} number(s)" if NOTIFY_NUMBERS else "❌ Not configured"
    )
    telnyx_status = "✅ Configured" if TELNYX_API_KEY else "❌ Not configured"

    return f'''
    <html>
    <head>
        <title>Let Food Into Civic - Status</title>
        <style>
            body {{
                font-family: system-ui, -apple-system, sans-serif;
                max-width: 600px;
                margin: 50px auto;
                padding: 20px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
            }}
            .card {{
                background: white;
                border-radius: 16px;
                padding: 32px;
                box-shadow: 0 20px 40px rgba(0,0,0,0.2);
            }}
            h1 {{ margin-top: 0; }}
            .status {{ 
                background: #f5f5f5; 
                padding: 16px; 
                border-radius: 8px;
                margin: 16px 0;
            }}
            .status p {{ margin: 8px 0; }}
            code {{
                background: #e0e0e0;
                padding: 2px 6px;
                border-radius: 4px;
            }}
        </style>
    </head>
    <body>
        <div class="card">
            <h1>🍕 Let Food Into Civic</h1>
            <p>Automatic call box unlocker for food deliveries!</p>
            <p>When the call box calls, this service answers and plays DTMF tone "{UNLOCK_DIGIT}" 
               to unlock the gate.</p>
            
            <div class="status">
                <p><strong>Service:</strong> ✅ Running</p>
                <p><strong>Telnyx API:</strong> {telnyx_status}</p>
                <p><strong>SMS Notifications:</strong> {notify_status}</p>
            </div>
            
            <p><strong>Webhook URL:</strong> <code>/webhook/voice</code></p>
        </div>
    </body>
    </html>
    '''


@app.route("/sms-consent", methods=["GET"])
def sms_consent():
    """SMS consent disclosure page for toll-free verification with CTIA-required disclosures."""
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>SMS Notification Consent - Let Food Into Civic</title>
        <style>
            * { box-sizing: border-box; margin: 0; padding: 0; }
            body {
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
                line-height: 1.6;
                color: #333;
                background: #f8f9fa;
                padding: 40px 20px;
            }
            .container {
                max-width: 680px;
                margin: 0 auto;
                background: white;
                border-radius: 12px;
                box-shadow: 0 4px 20px rgba(0,0,0,0.08);
                padding: 48px;
            }
            h1 {
                font-size: 1.75rem;
                margin-bottom: 8px;
                color: #1a1a1a;
            }
            .subtitle {
                color: #666;
                margin-bottom: 32px;
                padding-bottom: 24px;
                border-bottom: 1px solid #eee;
            }
            h2 {
                font-size: 1.1rem;
                margin: 24px 0 12px 0;
                color: #1a1a1a;
            }
            p, li {
                color: #444;
                margin-bottom: 12px;
            }
            ul {
                margin-left: 24px;
                margin-bottom: 16px;
            }
            .highlight {
                background: #f0fdf4;
                border-left: 4px solid #22c55e;
                padding: 16px 20px;
                margin: 24px 0;
                border-radius: 0 8px 8px 0;
            }
            .ctia-disclosure {
                background: #fef3c7;
                border: 1px solid #f59e0b;
                padding: 20px;
                margin: 24px 0;
                border-radius: 8px;
            }
            .ctia-disclosure h3 {
                color: #92400e;
                margin-bottom: 12px;
                font-size: 1rem;
            }
            .ctia-disclosure ul {
                margin-bottom: 0;
            }
            .ctia-disclosure li {
                margin-bottom: 8px;
            }
            .example {
                background: #f8f9fa;
                padding: 12px 16px;
                border-radius: 8px;
                font-family: monospace;
                font-size: 0.9rem;
                margin: 12px 0;
            }
            .footer {
                margin-top: 32px;
                padding-top: 24px;
                border-top: 1px solid #eee;
                font-size: 0.85rem;
                color: #888;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>📱 SMS Notification Consent</h1>
            <p class="subtitle">Let Food Into Civic — Delivery Gate Notifications</p>
            
            <h2>Service Description</h2>
            <p>This service provides SMS notifications to household members when the apartment 
               building gate is accessed for deliveries. When a delivery person uses the call 
               box, the system automatically unlocks the gate and sends a notification to 
               registered household members.</p>
            
            <h2>Who Receives Messages</h2>
            <p>Only household family members who have explicitly opted in receive SMS notifications. 
               This is a private, non-commercial service for personal home use.</p>
            
            <div class="highlight">
                <strong>Consent Process:</strong> By providing your mobile phone number and agreeing 
                to receive notifications, you consent to receive automated SMS messages about 
                delivery gate access at the registered address. Consent is not a condition of 
                any purchase.
            </div>
            
            <div class="ctia-disclosure">
                <h3>📋 Important Disclosures (CTIA Compliance)</h3>
                <ul>
                    <li><strong>Message Frequency:</strong> Message frequency varies based on delivery activity. Expect approximately 10-30 messages per month.</li>
                    <li><strong>Message and Data Rates:</strong> Message and data rates may apply. Check with your mobile carrier for details.</li>
                    <li><strong>Opt-Out:</strong> Reply <strong>STOP</strong> to any message to unsubscribe and stop receiving notifications.</li>
                    <li><strong>Help:</strong> Reply <strong>HELP</strong> for assistance or contact the household administrator.</li>
                    <li><strong>Privacy:</strong> Your phone number will not be shared with third parties. See our <a href="https://contrived.com/privacy">Privacy Policy</a> for details.</li>
                </ul>
            </div>
            
            <h2>Message Content</h2>
            <p>Messages are limited to delivery gate access notifications:</p>
            <div class="example">🍕 Gate unlocked at 2:30 PM! Call from: +1 (555) 123-4567</div>
            
            <h2>Opt-Out Instructions</h2>
            <p>You may opt out at any time by:</p>
            <ul>
                <li>Replying <strong>STOP</strong> to any message</li>
                <li>Contacting the household administrator to have your number removed</li>
            </ul>
            <p>After opting out, you will receive a confirmation message and no further notifications.</p>
            
            <h2>Contact &amp; Support</h2>
            <p>For questions about this service:</p>
            <ul>
                <li>Reply <strong>HELP</strong> to any message</li>
                <li>Email: contact@contrived.com</li>
            </ul>
            
            <div class="footer">
                <p>Last updated: December 2024</p>
                <p>This service is for private, personal use only.</p>
            </div>
        </div>
    </body>
    </html>
    """


# =============================================================================
# Admin/Utility Endpoints
# =============================================================================


@app.route("/internal/toggle-sms-pause", methods=["POST"])
def toggle_sms_pause():
    """
    Toggle per-user "skip SMS on next unlock" state.

    POST /internal/toggle-sms-pause
    Body (JSON): {"user": "linda", "skip_next": true}
    Body (Form): user=linda&skip_next=true

    Only accessible from internal network.
    """
    if not is_internal_network(request):
        logger.warning("Blocked SMS pause toggle request from external network")
        return jsonify({"error": "Access denied - internal network only"}), 403

    if request.is_json:
        data = request.get_json() or {}
        user = data.get("user", "").lower()
        skip_next_raw = data.get("skip_next")
    else:
        user = request.form.get("user", "").lower()
        # Unchecked checkbox does not submit any key.
        skip_next_raw = request.form.get("skip_next")

    if isinstance(skip_next_raw, bool):
        skip_next = skip_next_raw
    elif isinstance(skip_next_raw, str):
        skip_next = skip_next_raw.lower() == "true"
    else:
        skip_next = False

    if user not in ["linda", "sean"]:
        return jsonify({"error": 'Invalid user. Must be "linda" or "sean"'}), 400

    state = set_sms_pause_state(user, skip_next)

    logger.info(
        f"{'⏭️' if skip_next else '✅'} {user.capitalize()} skip_next set to {skip_next}"
    )

    if not request.is_json:
        return redirect("/")

    return jsonify(
        {
            "success": True,
            "user": user,
            "skip_next": skip_next,
            "state": state,
        }
    )


@app.route("/admin/test-sms", methods=["POST"])
def test_sms():
    """
    Send a test SMS to verify configuration.

    POST /admin/test-sms
    Body: {"to": "+1XXXXXXXXXX"} (optional, defaults to first NOTIFY_NUMBER)
    """
    if not telnyx_client:
        return jsonify({"error": "Telnyx API key not configured"}), 500

    if not TELNYX_PHONE_NUMBER:
        return jsonify({"error": "Telnyx phone number not configured"}), 500

    data = request.get_json() or {}
    to_number = data.get("to") or (NOTIFY_NUMBERS[0] if NOTIFY_NUMBERS else None)

    if not to_number:
        return jsonify(
            {"error": "No phone number provided and NOTIFY_NUMBERS is empty"}
        ), 400

    try:
        telnyx_client.messages.send(
            from_=TELNYX_PHONE_NUMBER,
            to=to_number,
            text="🧪 Test message from let-food-into-civic! Your SMS notifications are working.",
        )
        logger.info(f"Test SMS sent to {to_number}")
        return jsonify(
            {
                "success": True,
                "to": to_number,
            }
        )
    except Exception as e:
        logger.error(f"Failed to send test SMS: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/admin/call-logs", methods=["GET"])
def get_call_logs():
    """
    Query recent call logs from Telnyx.

    GET /admin/call-logs?limit=10
    """
    if not telnyx_client:
        return jsonify({"error": "Telnyx API key not configured"}), 500

    limit = request.args.get("limit", 10, type=int)

    try:
        # Query call events/CDRs
        calls = telnyx_client.call_events.list(page_size=limit)

        call_list = []
        for call in calls.data:
            call_list.append(
                {
                    "id": getattr(call, "id", "N/A"),
                    "from": getattr(
                        call, "from_", getattr(call, "caller_id_number", "N/A")
                    ),
                    "to": getattr(
                        call, "to", getattr(call, "destination_number", "N/A")
                    ),
                    "type": getattr(call, "event_type", "N/A"),
                    "occurred_at": str(getattr(call, "occurred_at", "N/A")),
                }
            )

        return jsonify({"calls": call_list, "count": len(call_list)})
    except Exception as e:
        logger.error(f"Failed to fetch call logs: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/admin/buy-number", methods=["POST"])
def buy_number():
    """
    Search for available phone numbers.

    POST /admin/buy-number
    Body: {
        "area_code": "415",      # Optional: area code to search
        "country": "US"          # Optional: country code (default: US)
    }
    """
    if not telnyx_client:
        return jsonify({"error": "Telnyx API key not configured"}), 500

    data = request.get_json() or {}
    area_code = data.get("area_code", "214")
    country = data.get("country", "US")

    try:
        # Search for available numbers
        response = telnyx_client.available_phone_numbers.list(
            filter={
                "country_code": country,
                "national_destination_code": area_code,
                "limit": 5,
            }
        )

        if not response.data:
            return jsonify({"error": "No numbers found matching criteria"}), 404

        # Return available numbers for selection
        numbers = []
        for n in response.data:
            location = "Unknown"
            if n.region_information:
                for r in n.region_information:
                    if r.region_type == "rate_center":
                        location = r.region_name
                        break
            numbers.append(
                {
                    "phone_number": n.phone_number,
                    "location": location,
                    "monthly_cost": n.cost_information.monthly_cost
                    if n.cost_information
                    else "N/A",
                }
            )

        return jsonify(
            {
                "available_numbers": numbers,
                "message": 'Use POST /admin/buy-number/confirm with {"phone_number": "..."} to purchase',
            }
        )
    except Exception as e:
        logger.error(f"Failed to search numbers: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/admin/buy-number/confirm", methods=["POST"])
def confirm_buy_number():
    """
    Confirm purchase of a specific phone number.

    POST /admin/buy-number/confirm
    Body: {"phone_number": "+14155551234"}
    """
    if not telnyx_client:
        return jsonify({"error": "Telnyx API key not configured"}), 500

    data = request.get_json() or {}
    phone_number = data.get("phone_number")

    if not phone_number:
        return jsonify({"error": "phone_number is required"}), 400

    try:
        # Order the phone number
        order = telnyx_client.number_orders.create(
            phone_numbers=[{"phone_number": phone_number}]
        )

        logger.info(f"📱 Purchased phone number: {phone_number}")

        return jsonify(
            {
                "success": True,
                "phone_number": phone_number,
                "message": "Number purchased! Remember to set up messaging profile for SMS.",
            }
        )
    except Exception as e:
        logger.error(f"Failed to purchase number: {e}")
        return jsonify({"error": str(e)}), 500


# =============================================================================
# Main Entry Point
# =============================================================================


def main():
    """Main entry point for the service."""
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8080"))
    debug = os.getenv("DEBUG", "false").lower() == "true"

    logger.info("🍕 let-food-into-civic starting up...")
    logger.info(f"Configuration:")
    logger.info(f"  - Unlock digit: {UNLOCK_DIGIT}")
    logger.info(
        f"  - Tone repeats: {TONE_DURATION_REPEATS} (~{TONE_DURATION_REPEATS * 0.25}s)"
    )
    logger.info(f"  - Pause duration: {PAUSE_DURATION}s")
    logger.info(f"  - Iterations: {ITERATIONS}")
    logger.info(
        f"  - Telnyx API: {'✅ Configured' if TELNYX_API_KEY else '❌ Not configured'}"
    )
    logger.info(f"  - Telnyx number: {TELNYX_PHONE_NUMBER or 'Not configured'}")
    logger.info(f"  - Notify numbers: {NOTIFY_NUMBERS or 'None configured'}")
    logger.info(f"  - Listening on: {host}:{port}")

    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    main()
