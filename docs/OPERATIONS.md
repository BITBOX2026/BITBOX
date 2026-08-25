# BITBOX Operations Runbook

## Service objectives

- Public HTTPS and `/health`: available during normal operation.
- `/ready`: returns `200` only after startup validation succeeds and no monitored
  external-provider circuit is open.
- Bus arrival board: refreshes every 15 seconds and keeps the last successful data on transient failure.
- Route requests: backend timeout 30 seconds, browser timeout 35 seconds, proxy timeout 40 seconds.

## Monitoring

Monitor these endpoints from outside EC2:

- `GET https://<domain>/health`
- `GET https://<domain>/ready`
- `GET https://<domain>/`

The `Production Monitor` GitHub Actions workflow checks them every 15 minutes
after that workflow exists on the repository default branch. A scheduled
workflow present only on a non-default branch does not run. GitHub records a
failed run, but an actual paging notification still requires repository or
organization Actions notifications. Application logs are available through
`journalctl -u bitbox-backend.service`; Nginx JSON access and error logs are in
`/var/log/nginx/bitbox_access.log` and `/var/log/nginx/bitbox_error.log` and are
retained for 14 rotations.

`/ready` is circuit-based rather than an active paid-provider probe. It can stay
ready until traffic observes a provider failure. Each deployment therefore runs
one bounded real request against the bus board, place suggestions and bus-only
route, while the 15-minute scheduled monitor remains non-billable.

The local `bitbox-healthcheck.timer` checks `/health` and `/ready` every minute.
Three consecutive liveness (`/health`) failures restart the backend. Three
consecutive readiness failures send an alert and log the external-dependency
degradation without restarting a healthy process. This local check cannot
detect a whole-instance or network outage.

For a Slack-compatible alert webhook, add the HTTPS URL as the repository
Actions secret `BITBOX_ALERT_WEBHOOK_URL`. The deployment writes it to
`/etc/bitbox/monitoring.env` with mode `600`. The local healthcheck sends an
alert after three failures. Keep this value out of Git and rotate the webhook
if it is exposed.

Local runtime counters, paid-request usage and external circuit states are
available only from EC2 with `curl http://127.0.0.1:8001/internal/status`.
Nginx returns `404` for every external `/internal/` request.

Production stores daily paid-request counts in
`/var/lib/bitbox/usage.sqlite3`, so those limits survive application restarts on
the single EC2 instance. Active concurrency, runtime metrics, circuit state and
cache state remain process-local. SQLite is not a distributed counter and must
be replaced by a shared store before running multiple application instances.

The runtime snapshot also aggregates privacy-safe counts for safety decision
levels (`verified`, `confirm`, `retry`), pipeline intent and provider source.
These counters never store transcripts, destinations, bus numbers or audio.
They are process-local and reset on restart, so export snapshots externally
before using them in a longitudinal report.

## Incident checks

```bash
sudo systemctl status bitbox-backend.service nginx certbot.timer
sudo journalctl -u bitbox-backend.service --since "15 minutes ago" --no-pager
sudo tail -n 100 /var/log/nginx/bitbox_error.log
curl --fail http://127.0.0.1:8001/ready
sudo nginx -t
```

Use the `X-Request-ID` response header to correlate a user-visible failure with
application and Nginx logs. Logs intentionally exclude transcripts, destination
queries, uploaded filenames, API keys, and audio content.

## Deployment and rollback

Only `merge-frontend-backend` triggers deployment. CI must pass backend tests,
frontend tests, type checking, build, E2E, and a concurrent health smoke test.
Frontend assets are written to a commit-specific release directory and switched
through `/var/www/bitbox-current` atomically.

After activation, CI also checks the public HTTPS path, `/health`, `/ready`,
required security headers, external blocking of `/internal/status`, and at
least 14 days of TLS certificate validity. `/health` and `/ready` must expose
the exact deployed Git commit in `release_sha`, preventing a stale process from
being mistaken for a successful deployment. The deployment also verifies one
real response from each transit integration and checks that route segment time
equals total time. A failed public-boundary check fails the deployment run even
when the EC2-local check passed.

Direct backend dependencies and frontend packages are pinned to tested versions.
Dependabot proposes reviewed upgrades; do not loosen production version pins
without passing the full security, unit, build and E2E pipeline.

To restore an earlier frontend release, point `/var/www/bitbox-current` to a
known release under `/var/www/bitbox-releases` and reload Nginx. Backend rollback
uses a reviewed revert commit on the deployment branch; do not edit production
source files directly.

## Privacy and retention

- Audio is held in memory for request processing and is not written to local storage.
- Audio is transmitted to OpenAI for STT/TTS processing.
- Destination text is sent to Kakao and ODsay as required for routing.
- Publish a privacy policy and obtain any required consent before public launch.
- Define provider-side retention and regional processing settings with the service owner.
- Replace the in-app generic notice with the operator's legal name, contact,
  provider retention terms and final counsel-reviewed policy before public launch.
- Shared-kiosk route history is cleared on home, after 90 seconds of inactivity,
  and on page startup. Voice consent is cleared when the active kiosk session
  ends through home or inactivity.

## Capacity and scaling

Run a non-billable liveness smoke test with:

```bash
python scripts/load_smoke.py --url https://<domain>/health --requests 500 --concurrency 50
```

The current deployment is one EC2 instance. Before claiming high availability,
add at least two instances behind an Application Load Balancer, shared Redis for
distributed rate limits/cache, managed monitoring, and automated instance health
replacement. Provider quotas and billing alerts must be configured independently.

The SQLite-backed daily limits are emergency single-instance cost guards, not
billing controls, and are not shared across instances. Use API Gateway/WAF and
provider-side hard quotas before horizontal scaling.
