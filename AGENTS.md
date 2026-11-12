# lfic — let-food-into-civic

## Purpose and behavior

lfic handles apartment call-box deliveries. A voice request returns TeXML that
plays `dtmf5-1sec-half.wav` once, then hangs up. Authenticated fresh Telnyx
requests with a provider call ID may trigger household SMS through Relay's
`civic` sender. Relay owns SMS ingress, transport and provider sessions.

Consent, snooze state, event history and durable notification claims live under
`/app/data`. Notification dispatch is at-most-once: retries do not replay a claimed
call, and a crash after claiming can lose its notification. Voice responses must
remain available when notification authentication, persistence or transport fails.
Startup must not automatically enroll or message recipients.

## Source and infrastructure

This repo owns application code, Dockerfiles, desired Compose configuration,
image CI and the runtime Vault secret schema. Homelab-infra owns host placement,
accounts, nginx/TLS, lifecycle/update units, protected bootstrap delivery and
updater credentials.

Use the infra checkout named by the task, defaulting to `~/dev/homelab-infra`.
Read its AGENTS, README adoption status and `service/let-food-into-civic.md`.
For alignment work, follow `docs/service-alignment.md` and the updated
`contrived-dev-make-service` skill. Candidate source is not proof of live adoption.
Compare local HEAD, published main and installed revision before diagnosing drift.

Dallas uses `let-food-into-civic-runtime.service` and
`civic-release-update.service`/`.timer`. Homelab's shared runtime prepares this
repo's Compose at the signed image's exact source revision and systemd owns its
foreground process. Compose has no independent restart policy and never pulls
at startup. Check the infra service record for installed adoption status before
operating it; do not start a second owner beside an existing deployment.

## Credentials and state

Application settings come from Vault `secret/let-food-into-civic/config`.
`CIVIC_VAULT_CONFIG_PATH=secret/data/let-food-into-civic/config` enables that read.
The installed bootstrap exception uses a protected root-owned JSON file selected
by `CIVIC_VAULT_BOOTSTRAP_FILE`; `src.bootstrap` supplies its AppRole pair before
invoking the visa entrypoint. Preserve that delivery until deliberately migrated.
`CIVIC_RELAY_API_URL` may override the nonsecret internal route; the key remains
in Vault. A configured Vault read failure fails startup without stale fallback.

Updater auth is infra-owned at `secret/homelab/deploy-auth/let-food-into-civic`,
separate from application credentials. No persistent git/Docker credential files
or application business secrets belong in source or copied service-home env files.

## Code and validation

- `src/main.py`: Flask routes, voice response, state and notification coordination.
- `src/bootstrap.py`, `src/runtime_config.py`: private bootstrap and Vault loading.
- `src/relay_sms.py`, `src/voice_notifications.py`: Relay access, signature checks
  and durable call deduplication.
- `Dockerfile`, `.github/workflows/build_and_push.yml`: current image producer;
  main publishes signed immutable digests for infra adoption.
- `tests/`: synthetic credentials, disposable state and mocked provider calls.

Run `python -m unittest discover -s tests -v` in an environment with requirements
installed. Use the Flask test client/mocked transport for webhook tests. Production
`/health` is a safe readiness probe; it does not prove handset delivery or that a
physical gate opened. Calls, SMS, provider mutations and gate actions are not
implicit deployment checks. Public `/status`/admin/internal routes are deliberately
blocked by infra; SMS ingress belongs to Relay.

Preserve `src/static/dtmf5-2sec.wav`, the original audio asset. The derived
one-second asset and consent copy should change only for an explicit product task.
Legacy tone-loop environment settings do not alter the current fixed voice sequence.
