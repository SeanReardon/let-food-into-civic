# let-food-into-civic

`let-food-into-civic` answers an apartment call box via Telnyx, plays a repeated DTMF unlock tone, and sends SMS notifications to configured household members. It also includes a CTIA-compliant SMS consent page and an internal snooze dashboard for temporarily skipping the next notification.

## Quick start

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m src.main
```

Docker:

```bash
docker compose up -d
```

The container listens on port `8080`. The checked-in `docker-compose.yml` binds it to `127.0.0.1:8042`.

## Configuration

Required environment variables:

- `TELNYX_LET_FOOD_INTO_CIVIC_KEY`: Telnyx API key
- `TELNYX_PHONE_NUMBER`: Telnyx number used for voice webhooks and outbound SMS

Common optional variables:

- `NOTIFY_NUMBERS`: comma-separated E.164 phone numbers to notify
- `UNLOCK_DIGIT`: DTMF digit to play, default `5`
- `TONE_DURATION_REPEATS`: 250 ms slices per tone burst, default `8`
- `PAUSE_DURATION`: pause between bursts in seconds, default `0.5`
- `ITERATIONS`: number of burst repetitions per unlock, default `3`
- `LOG_LEVEL`: logging level, default `INFO`

## Endpoints

- `GET /`: public landing page, or internal snooze dashboard when accessed from the trusted network
- `GET /health`: health check
- `GET /status`: simple configuration/status page
- `POST /webhook/voice`: incoming voice webhook that records the event, sends notifications, and returns TeXML
- `POST /webhook/sms`: inbound SMS webhook for `STOP`, `HELP`, and `START`
- `GET /sms-consent`: CTIA-compliant consent and disclosure page
- `POST /internal/toggle-sms-pause`: internal control for skipping the next SMS per user
- `POST /admin/test-sms`: send a test SMS
- `GET /admin/call-logs`: fetch recent Telnyx call events
- `POST /admin/buy-number`: search available Telnyx numbers
- `POST /admin/buy-number/confirm`: purchase a number returned by the search endpoint

## Development notes

- The app persists logs, opt-in records, event history, and snooze state under `/app/data`.
- `src/static/dtmf5-2sec.wav` is the unlock tone asset; do not replace it casually.
- The consent copy in `/sms-consent` is compliance-sensitive and should only be edited deliberately.

## Related docs

- See [AGENTS.md](AGENTS.md) for agent-oriented repository guidance.
