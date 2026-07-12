# AGENTS.md

## What This Project Does

**let-food-into-civic** is a home automation service that automatically unlocks an apartment call box for food deliveries. When a delivery person dials the Telnyx phone number from the call box, the service answers and plays DTMF tone "5" repeatedly to unlock the gate, then sends SMS notifications to household members.

## Project Structure

```
src/
  main.py          # Flask app with all endpoints and business logic
  static/          # DTMF audio and internal dashboard assets
art/               # Avatar and art assets served by the app
scripts/claudia/   # Claudia agent metadata (PRD, progress)
schema/            # Public JSON schema routes served by the app
schemas/           # Local JSON schema files used by the repo
```

## Key Technologies

- **Flask** - Web framework handling webhooks
- **Telnyx** - Telephony provider for voice calls and SMS
- **TeXML/TwiML** - XML-based response format for call handling
- **Docker** - Container deployment

## Running the Project

```bash
# Local development
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # Edit with your Telnyx credentials
python -m src.main

# Docker
docker compose up -d
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `TELNYX_LET_FOOD_INTO_CIVIC_KEY` | Yes | Telnyx API key |
| `TELNYX_PHONE_NUMBER` | Yes | Toll-free number for SMS (E.164 format) |
| `NOTIFY_NUMBERS` | No | Comma-separated phone numbers to notify |
| `UNLOCK_DIGIT` | No | DTMF digit (default: "5") |
| `TONE_DURATION_REPEATS` | No | 250 ms slices per tone burst (default: `8`) |
| `PAUSE_DURATION` | No | Pause between bursts in seconds (default: `0.5`) |
| `ITERATIONS` | No | Number of tone bursts per unlock sequence (default: `3`) |

## API Endpoints

- `GET /` - Public landing page, or internal snooze dashboard on trusted networks
- `POST /webhook/voice` - Telnyx voice webhook (answers calls, plays DTMF)
- `POST /webhook/sms` - Telnyx SMS webhook (handles STOP/HELP/START)
- `GET /health` - Container health check
- `GET /status` - Simple runtime status page
- `GET /sms-consent` - CTIA-compliant consent page for toll-free verification
- `POST /internal/toggle-sms-pause` - Internal snooze toggle for next unlock
- `POST /admin/test-sms` - Send test SMS
- `GET /admin/call-logs` - Query recent Telnyx call activity
- `POST /admin/buy-number` - Search for available Telnyx numbers
- `POST /admin/buy-number/confirm` - Purchase a searched number

## Important Patterns

1. **Phone number normalization**: All configured numbers are normalized to E.164 on startup.
2. **Opt-in/opt-out**: CTIA-compliant consent state is persisted under `/app/data/opt-in-flow/`.
3. **Async SMS**: Notifications are sent in background threads so voice webhooks return immediately.
4. **Pre-recorded DTMF**: The unlock flow plays `src/static/dtmf5-2sec.wav` instead of short `<Play digits>` tones.
5. **Network-aware UI**: `/` serves the internal snooze dashboard only for requests marked as internal by nginx or local-network detection.

## Testing

```bash
# Test webhook locally
curl -X POST http://localhost:8080/webhook/voice -d "From=+15551234567"

# Test SMS
curl -X POST http://localhost:8080/admin/test-sms
```

## Do Not Modify

- `src/static/dtmf5-2sec.wav` - Pre-recorded DTMF tone file
- Toll-free verification compliance text in `/sms-consent` without careful review

## Deploy Auth Responsibilities

- Deployment auth is infra-owned in `homelab-infra` and read at runtime from Vault.
- Canonical deploy-auth path for this repo: `secret/homelab/deploy-auth/let-food-into-civic`.
- The deploy PAT from that path is used for both HTTPS git fetch and GHCR image pulls.
- This repo continues to own only its application secret schema/policies in Vault.
- Do not rely on persistent deployment creds in `~/.docker/config.json` or `~/.git-credentials`.
