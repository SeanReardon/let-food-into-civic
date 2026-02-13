# CLAUDE.md

## What This Project Does

**let-food-into-civic** is a home automation service that automatically unlocks an apartment call box for food deliveries. When a delivery person dials the Telnyx phone number from the call box, the service answers and plays DTMF tone "5" repeatedly to unlock the gate, then sends SMS notifications to household members.

## Project Structure

```
src/
  main.py          # Flask app with all endpoints and business logic
static/
  dtmf5-2sec.wav   # Pre-recorded DTMF tone file
scripts/claudia/   # Claudia agent metadata (PRD, progress)
schemas/           # JSON schemas for Claudia
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

## API Endpoints

- `POST /webhook/voice` - Telnyx voice webhook (answers calls, plays DTMF)
- `POST /webhook/sms` - Telnyx SMS webhook (handles STOP/HELP/START)
- `GET /health` - Container health check
- `GET /sms-consent` - CTIA-compliant consent page for toll-free verification
- `POST /admin/test-sms` - Send test SMS

## Important Patterns

1. **Phone number normalization**: All numbers are normalized to E.164 format on startup
2. **Opt-in/opt-out**: CTIA-compliant system tracks consent in `/app/data/opt-in-flow/`
3. **Async SMS**: Notifications are sent in background threads to avoid blocking webhook responses
4. **Pre-recorded DTMF**: Uses audio file instead of `<Play digits>` because TwiML only supports short tones

## Testing

```bash
# Test webhook locally
curl -X POST http://localhost:8080/webhook/voice -d "From=+15551234567"

# Test SMS
curl -X POST http://localhost:8080/admin/test-sms
```

## Do Not Modify

- `static/dtmf5-2sec.wav` - Pre-recorded DTMF tone file
- Toll-free verification compliance text in `/sms-consent` without careful review

## Deploy Auth Responsibilities

- Deployment auth is infra-owned in `homelab-infra` and read at runtime from Vault.
- Canonical deploy-auth path for this repo: `secret/homelab/deploy-auth/let-food-into-civic`.
- The deploy PAT from that path is used for both HTTPS git fetch and GHCR image pulls.
- This repo continues to own only its application secret schema/policies in Vault.
- Do not rely on persistent deployment creds in `~/.docker/config.json` or `~/.git-credentials`.

