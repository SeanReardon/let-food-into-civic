# lfic — let-food-into-civic

lfic answers apartment call-box requests with one second of DTMF 5 followed by
Hangup, and coordinates household notifications through Relay. The application
owns voice behavior; nginx forwards it and returns ordinary upstream failures.
There is no nginx-generated successful fallback call response.

## Service integration

The application repo owns code, runtime-secret schemas, image production and the
intended Compose definition. Homelab-infra owns the host integration and records
its current lifecycle, routes and exceptions in `service/let-food-into-civic.md`.
Read [AGENTS](AGENTS.md) and the infra `docs/service-alignment.md` for cross-repo work.

The host runtime is `let-food-into-civic-runtime.service`, updated by
`civic-release-update.timer`. The updater discovers signed main releases from
`build_and_push.yml` and its `let-food-into-civic-digests` artifact. It prepares
all images and this repo's Compose at that exact source revision before stopping
the old release. Systemd owns foreground Compose; container restart policies are
disabled. Startup uses the cached accepted release. See the infra service record
for installed adoption status and any transition still in progress.

The current producer is [Dockerfile](Dockerfile). `Dockerfile.canonical` and
migration helpers are historical inputs, not the ordinary release path.
[Compose](docker-compose.yml) declares UID/GID 2004, loopback 8042 → 8080,
private persistent mounts, protected Vault bootstrap, external private networks,
bounded logs and a read-only root filesystem. Its production telemetry names the
service, instance, exact image, source revision and successful workflow.

The updater supplies `LFIC_IMAGE`, `RELEASE_REVISION` and
`RELEASE_WORKFLOW_RUN_URL` from verified release metadata. Supply those nonsecret
values when running `docker compose config --quiet` locally. Config validation
does not start containers. Application publication does not itself install host
units; both repositories' adoption paths must be completed.

Sean can SSH as `let-food-into-civic`, access `/home/let-food-into-civic`, and use
`sudo /usr/local/sbin/service-container shell` or
`sudo /usr/local/sbin/service-container logs 100`. These operate only the declared
service, using UID/GID 2004 for its shell; general Docker administration remains
with Sean's administrator account.

## Credentials

Concordia/Vault owns application secrets at `secret/let-food-into-civic/config`.
The runtime reads its KV v2 API path `secret/data/let-food-into-civic/config`.
The deployed bootstrap is `/etc/let-food-into-civic/vault-bootstrap.json`, owned
by root:2004 with mode 0440, mounted read-only at `/run/secrets/civic-vault.json`.
`src.bootstrap` reads the AppRole pair before the visa entrypoint/transponder and
Gunicorn start. A missing or invalid configured Vault read fails startup.

Relay mode requires the configured notification numbers, service phone number,
Relay endpoint/key/account, and Telnyx verification public key in Vault. lfic
uses the explicit Relay `civic` sender. It does not need a Telnyx API key to send
through Relay; `telnyx_configured=false` in health is expected in this mode.
`CIVIC_RELAY_API_URL=http://relay-api:8000` overrides only the nonsecret route.

The generic infra home `.env` bootstrap remains the target convention; this
protected-file arrangement is a documented installed exception. Do not create a
competing credential copy merely to normalize paths. `.env.example` contains
legacy direct-Telnyx development examples and is not production configuration.
Old provisioning helpers require source/host reconciliation before use; they are
not a fresh-host setup procedure.

## Voice, notification and state contract

- Voice XML plays `src/static/dtmf5-1sec-half.wav` once, then `<Hangup/>`.
  The original two-second asset is preserved. Legacy tone-loop settings do not
  change this sequence. Actual gate operation requires a user-initiated call.
- Notifications require a fresh Telnyx signature and provider call ID. Unsigned
  probes produce XML without sending. Startup auto-opt-in remains disabled.
- Local consent and snooze checks precede dispatch. Relay's recipient-scoped
  opt-out lookup must succeed before a thread/message is created. There is no
  fallback to direct Telnyx or a full opt-out list.
- Durable claims prevent repeat dispatch for a provider call. Dispatch is
  at-most-once, not guaranteed delivery; a crash after claim can lose a message.
  Relay acceptance and handset delivery are distinct evidence.
- Persistent data is `/app/data`. Application logs go to stdout, retained by
  Docker's bounded log driver (two 10-MiB files). Read them through the scoped
  log command. The private `/app/data/logs` bind preserves historical files;
  the application no longer appends a duplicate unbounded `app.log`. Cache is
  reserved and currently unused; it needs no application mount.

## Interfaces and safe checks

Public ingress provides voice handling, health, consent text and selected static
assets. Public `/status`, `/admin/` and `/internal/` are intentionally denied;
SMS webhooks are disabled here because Relay owns ingress. The owning nginx
configuration is linked from the infra service record.

`GET /health` reports process/configuration readiness. It does not send, call,
query phone activity or exercise the gate. Do not use `/admin/test-sms`, number
purchase endpoints or live webhooks as generic deployment checks.

Install [requirements](requirements.txt) in a development virtual environment and run:

```bash
python -m unittest discover -s tests -v
```

Tests use synthetic credentials, mocked transports and disposable state. No
production credentials are needed. Use these tests for voice XML, signature/age,
consent/deduplication and notification-failure behavior. Scope any real provider
exercise separately. The `/sms-consent` copy is compliance-sensitive; change it
only as part of the requested product work.
