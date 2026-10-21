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

## Canonical Latitude SMS restoration

The prepared application supports `SMS_TRANSPORT=relay`, selecting the existing
Relay `civic` SMS account explicitly. Relay keeps inbound SMS ownership; the
Civic SMS route is disabled in this mode. The original notification text,
recipient opt-in records, snooze behavior, and six-tone unlock XML are retained.
Relay opt-outs are checked before sending, and correlation IDs deduplicate sends
per provider call and recipient. Telnyx's toll-free STOP/START blocking remains
provider-owned; Relay's optional global auto-reply setting is not changed.

Relay notification triggers require a fresh Telnyx Ed25519 signature and a
provider call ID. Unsigned probes return the gate XML without sending messages.
A durable call claim prevents retries from consuming a snooze and then texting.
Dispatch is at-most-once: a process crash after claiming a call can lose that
notification. Relay acceptance is logged separately from handset delivery.
Notification authentication, persistence, or transport errors do not change the
unlock XML. Canonical nginx retains the fixed response as its upstream-error
fallback; it must not be switched until candidate configuration is verified.

Configuration comes from `secret/let-food-into-civic/config` when
`CIVIC_VAULT_CONFIG_PATH=secret/data/let-food-into-civic/config` is set. The
`src.bootstrap` entrypoint reads a protected root-owned bootstrap file specified
by `CIVIC_VAULT_BOOTSTRAP_FILE`, then invokes the existing visa entrypoint.
The app fails startup if configured Vault retrieval fails rather than silently
using stale credentials. No application secrets are written to `.env`.
`CIVIC_AUTO_OPT_IN` now defaults to false: starting/restarting never enrolls or
texts a new recipient. Existing consent records are preserved.

To provision only the scoped Vault config and protected bootstrap, run in a
private terminal from this repository:

```sh
/home/seanr/dev/let-food-into-civic/scripts/ops/setup-civic-vault.sh
```

After SSH to `seanr@seanr-super-server`, run the command directly in your
interactive terminal. Only the existing Vault administrator token is requested;
all other credentials are recovered automatically. `--check` validates local
prerequisites without reading credentials or making network requests. The wrapper
rejects piped input/output and credential arguments, disables shell tracing/core
dumps, and the helper refuses to prompt if terminal echo cannot be disabled.

The helper prompts invisibly for an existing Vault administrator token, reads
only Civic's recovered configuration, confirms the Relay sender, preserves the
existing AppRole policies, grants the additional config read, and verifies it.
It does not deploy, restart services, change provider settings, send messages, or
make calls. Administrator material stays in memory and encrypted SSH stdin;
only the intended AppRole bootstrap is saved with root:2004 / 0440 custody.

`Dockerfile.canonical` builds on the accepted local visa image. Before building,
verify its parent ID against infra's Civic acceptance receipt. Publish reviewed
source first; admit the new image through the canonical lifecycle and repin its
envelope/fingerprint. Do not use legacy Compose/updaters or rerun migration
helpers. See `homelab-infra/latitude/leaf-lifecycle/civic/README.md` for host wiring.

Offline checks (synthetic credentials and mocked transport, no sends):

```sh
venv/bin/python -m unittest discover -s tests -v
```

A production send/call test requires Sean's separate approval. Configuration,
health, and offline tests alone do not establish handset delivery.

Canonical host wiring sets `CIVIC_RELAY_API_URL=http://relay-api:8000` on the
private shared network. This non-secret endpoint override takes precedence over
the stored URL; the Relay API key still comes exclusively from Vault.

### Recipient-scoped Relay consent lookup

The Relay SMS client uses authenticated `POST /sms/opt-outs/check` with the
one recipient. It validates the returned recipient and strict boolean before creating a thread or submitting a message.
Failures or mismatched/malformed responses stop that recipient's notification;
there is no fallback to direct Telnyx or the full opt-out list. Local opt-in and
snooze checks still apply. The lookup uses existing Relay API-key authentication; it does not grant SMS dispatch. Roll out the compatible Relay
endpoint before this client. Existing call deduplication remains at-most-once;
failed historical notifications are not automatically replayed.

### Short gate tone (October 2026)

The voice response plays `dtmf5-1sec-half.wav` once (one second total), then
executes Telnyx `<Hangup/>`. The versioned asset preserves DTMF 5 (770 + 1336 Hz)
at 0.5 sample amplitude, approximately -6.02 dB; this is not a guarantee of half
perceived loudness at the call box. The original two-second WAV remains intact.
Legacy `ITERATIONS`, `PAUSE_DURATION`, `TONE_DURATION_REPEATS`, `UNLOCK_DIGIT` and
`DTMF_AUDIO_URL` settings do not change this fixed voice sequence. A playback
error proceeds to Hangup via `continueOnError="true"`. No extra hangup API calls
or audio retries are issued. SMS notification behavior is unchanged.

Regenerate the derived asset with `python scripts/build_short_tone.py`. Offline
checks verify duration, gain, fades, exact verb order and notification dedup.
Actual gate detection and perceived volume require a user-initiated call.
