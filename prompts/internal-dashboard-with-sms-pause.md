# Feature: Internal Dashboard with Per-User SMS Pause

## Context

This is "Let Food Into Civic" - a personal homelab service that automatically unlocks our apartment call box for deliveries. When the call box rings, it answers, plays DTMF "5" to unlock the gate, and sends SMS notifications to household members (Sean and Linda).

The nginx reverse proxy now passes `X-Internal-Network: true` for LAN clients and `X-Internal-Network: false` for external requests. The container should serve different content based on this header.

## Team Members

| Name  | Phone Number   |
|-------|----------------|
| Sean  | +12149090499   |
| Linda | +14693059242   |

## Art Assets

- `./art/sean.png` (607x516 PNG)
- `./art/linda.png` (461x389 PNG)

Crop both images to center-focused squares of equal size (use the smaller dimension as the crop size) so they display uniformly as team member avatars.

## Feature Requirements

### 1. Internal Dashboard (when X-Internal-Network: true)

When a request comes from the home network, the `/` route should show an internal dashboard with:

#### A. Fun Team Diagnostics

Display interesting stats about unlock actions:
- Total number of unlock actions performed (parse from logs or maintain a simple counter file in `/app/data`)
- A histogram of unlock events by hour of day (24-hour buckets)
- The shortest time between two consecutive unlock actions (format nicely, e.g., "2 minutes 34 seconds")

Keep it playful - this is a silly but helpful home automation project.

#### B. Team Member Cards

Show a card for each team member (Sean and Linda) with:
- Their avatar image (cropped art from ./art/, served from /static/)
- Their name
- A checkbox showing "Skip SMS on next unlock" state

**SMS Skip Logic:**
- Anyone on the home network can check/uncheck the "skip next SMS" box for EITHER user
- When checked, that user will NOT receive an SMS on the NEXT unlock action only
- As soon as an unlock action occurs, BOTH checkboxes reset to unchecked (meaning the next action WILL send SMS to both)
- The default state is unchecked (SMS enabled)
- Store this state in a JSON file at `/app/data/sms-pause-state.json`

Include clear helper text explaining: "Check to skip SMS notification for the next gate unlock only. Resets automatically after each unlock."

#### C. "View External Page" Link

At the bottom, include a link/button labeled something like "See what visitors see" that renders the existing public landing page content (the current index page). This could be:
- A query param like `?view=external`
- Or a route like `/external`

### 2. External View (when X-Internal-Network: false)

The existing public landing page should remain unchanged. External visitors see the same Contrived LLC marketing/compliance page that exists today.

### 3. Styling

- Match the existing site's aesthetic (warm colors, Source Serif 4 / Inter fonts, clean cards)
- The internal dashboard should feel "cozy" and "behind the scenes" - maybe a slightly different background tint or a subtle banner indicating "You're on the home network"
- Keep it responsive and mobile-friendly

### 4. Implementation Details

#### Files to Modify
- `src/main.py`: Add internal network detection, new dashboard route logic, SMS pause state management, integrate pause logic into `send_sms_notifications()`

#### Files to Create
- Cropped avatar images in `src/static/` (sean-avatar.png, linda-avatar.png)
- Or handle cropping/sizing via CSS if easier

#### Data Files (in /app/data/)
- `sms-pause-state.json`: Track per-user SMS pause state
- Optionally `unlock-stats.json`: Track unlock count and timestamps for diagnostics

#### Detecting Internal Network
```python
is_internal = request.headers.get("X-Internal-Network") == "true"
```

#### SMS Pause State Schema
```json
{
  "sean": {"skip_next": false, "phone": "+12149090499"},
  "linda": {"skip_next": false, "phone": "+14693059242"}
}
```

When an unlock happens:
1. Check each user's skip_next flag before sending SMS
2. If skip_next is true, skip that user's SMS
3. Reset BOTH users' skip_next to false (regardless of what triggered)
4. Log the skip for auditability

### 5. API Endpoints for Toggle

Add a simple endpoint for the checkbox toggle:
```
POST /internal/toggle-sms-pause
Content-Type: application/json
{"user": "sean", "skip_next": true}
```

This endpoint should:
- Only work when X-Internal-Network: true (return 403 otherwise)
- Update the pause state
- Return the new state

The dashboard can use fetch() to toggle without full page reload, or use a form POST with redirect - either is fine.

### 6. Diagnostics Data

For the histogram and stats:
- Option A: Parse the existing app.log file in /app/data/logs/ for "INCOMING CALL RECEIVED" entries
- Option B: Maintain a separate unlock-events.jsonl file with timestamps

Either approach works. Keep it simple - this is a personal project.

### 7. Testing

After implementing:
- Verify external requests still see the public page
- Verify internal requests (or requests with X-Internal-Network: true header) see the dashboard
- Verify toggle works and persists
- Verify SMS is skipped appropriately and state resets after unlock

## Constraints

- Keep it simple - this is a 2-person household project
- Don't over-engineer
- Use existing Flask patterns from the codebase
- No new dependencies if possible (existing deps: Flask, telnyx, python-dotenv, gunicorn, gevent)
