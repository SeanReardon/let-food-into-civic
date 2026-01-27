# Snooze Notifications for Next Event

## Problem

Sometimes one household member is asleep but we still want deliveries accepted. Currently, both Linda and Sean get notified every time the gate unlocks. We need a way for either person to **snooze** notifications for the sleeping party—but only for the **next** event. After that event occurs, snooze automatically resets.

## Solution

Add a simple "snooze" interface that's only accessible from inside the local network. When accessed locally, the homepage shows two recipients with snooze toggles. When accessed remotely, show the existing public landing page (no change).

## Requirements

### 1. Network Detection

Detect whether the request originates from the local/homelab network:
- Check `request.remote_addr` or `X-Forwarded-For` header
- Local network ranges: `192.168.x.x`, `10.x.x.x`, `172.16.x.x - 172.31.x.x`
- Also treat `127.0.0.1` and `::1` as local
- If local → show the snooze interface
- If remote → show existing public landing page (no change to current behavior)

### 2. Recipient Display

Show two recipients in a simple, clean interface:

| Name | Phone | Snooze |
|------|-------|--------|
| Linda | (469) 305-9242 | 🔔 |
| Sean | (214) 909-0499 | 🔔 |

**Pattern matching:** The phone numbers in `NOTIFY_NUMBERS` env var may be formatted differently (e.g., `+12149090499`). Normalize and match against these known numbers:
- Linda: `469-305-9242` → normalized: `+14693059242`
- Sean: `214-909-0499` → normalized: `+12149090499`

Display Linda on top, Sean on bottom. Use their names, not just phone numbers.

### 3. Snooze Toggle Behavior

Each recipient has a snooze toggle:
- **Not snoozed (default):** 🔔 Will receive notification on next event
- **Snoozed:** 😴 Will NOT receive notification on next event

Clicking a toggle immediately persists the state (no submit button needed—use JS fetch or form auto-submit).

### 4. Persistent Snooze File

Store snooze state in a durable file: `/app/data/snooze.json`

Format:
```json
{"linda": false, "sean": false}
```

- `false` = NOT snoozed (will receive notification)
- `true` = snoozed (will skip next notification)

On startup, if file doesn't exist, create it with both NOT snoozed.

### 5. Notification Logic Changes

Modify `send_sms_notifications()` to:
1. Read the `snooze.json` file
2. For each recipient, check if they're snoozed
3. Only send SMS to non-snoozed recipients
4. Log snoozed recipients: "😴 Skipping Linda (snoozed)"
5. **After sending (regardless of success/failure), reset all snooze states to `false`**
6. Write the reset state back to the file

This ensures snooze is always "just for the next event."

### 6. UI Design

Keep it simple and mobile-friendly (often accessed from phones):

```
┌─────────────────────────────────────┐
│  🏠 Let Food Into Civic             │
│  Notification Snooze                │
│                                     │
│  ┌─────────────────────────────┐   │
│  │ 🔔  Linda                    │   │
│  │     (469) 305-9242          │   │
│  │     [Snooze]                │   │
│  └─────────────────────────────┘   │
│                                     │
│  ┌─────────────────────────────┐   │
│  │ 🔔  Sean                     │   │
│  │     (214) 909-0499          │   │
│  │     [Snooze]                │   │
│  └─────────────────────────────┘   │
│                                     │
│  😴 = skip next event only          │
│  Auto-resets after gate unlocks     │
│                                     │
└─────────────────────────────────────┘
```

When snoozed, show 😴 instead of 🔔 and toggle button changes to [Wake].

- Large tap targets for toggles
- Clear indication that this only affects the NEXT event
- Show current state when page loads

### 7. API Endpoint

```
POST /admin/snooze
Body: {"recipient": "linda", "snoozed": true}
Response: {"success": true, "linda": true, "sean": false}
```

Only accessible from local network (403 if remote).

## Files to Modify

- `src/main.py`:
  - Add network detection helper function
  - Modify `/` route to conditionally show snooze UI
  - Add `/admin/snooze` endpoint
  - Modify `send_sms_notifications()` to check and reset snooze state
  - Add snooze file read/write helpers

## Out of Scope

- Authentication (network location is the only gate)
- History/logging of snooze events
- Multiple snooze events (just next one)
- Scheduled snooze times

## Testing

1. Access from local network → see snooze UI
2. Access from remote → see public landing page
3. Snooze Linda → verify `snooze.json` shows `{"linda": true, "sean": false}`
4. Trigger a gate unlock → verify only Sean gets SMS
5. Verify both snooze states reset to false after event
6. Refresh page → both should show 🔔 (not snoozed)
