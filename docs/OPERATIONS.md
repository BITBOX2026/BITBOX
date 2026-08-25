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

### Alert channel

`bitbox-healthcheck` restarts the backend after three consecutive liveness
failures and reports readiness degradation without restarting. Both paths, and
the deployment rollback, call `send_alert`.

`send_alert` posts to `BITBOX_ALERT_WEBHOOK_URL`. **When that repository secret is
not set, no notification leaves the host.** The scripts then write to the system
journal instead of failing silently, and the deployment run adds a GitHub
Actions warning annotation so the gap is visible on every deploy.

Check whether alerting is configured:

```bash
sudo test -f /etc/bitbox/monitoring.env && echo configured || echo 'NOT configured'
sudo journalctl -t bitbox-healthcheck -t bitbox-rollback --since '-7d' --no-pager
```

Enable it with a Slack-compatible webhook, a standard Discord incoming webhook,
or your own HTTPS receiver. The scripts send `{"content":"..."}` to a standard
Discord URL and `{"text":"..."}` to other receivers. Alert delivery failures are
written to the system journal instead of being discarded:

```bash
gh secret set BITBOX_ALERT_WEBHOOK_URL --repo BITBOX2026/BITBOX
# then redeploy so the value reaches /etc/bitbox/monitoring.env
```

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
real response from each transit integration and checks that the guided segment
times never exceed the displayed total. The provider total can legitimately be
larger because it includes waiting for the bus, so an exact-equality check would
fail deployments on healthy data; the backend guarantees the upper bound. A
failed public-boundary check rolls the marked release back and still fails the
deployment run, even when the EC2-local check passed.

Direct backend dependencies and frontend packages are pinned to tested versions.
Dependabot proposes reviewed upgrades; do not loosen production version pins
without passing the full security, unit, build and E2E pipeline.

### Automatic rollback

When either the post-activation health loop or the public production smoke fails,
the deployment rolls the marked release back instead of leaving it live.
`deploy/rollback.sh` restores the
previous release directory through `/var/www/bitbox-current`, checks the backend
work tree out at the commit recorded in `/etc/bitbox/previous_release_sha`,
rewrites `RELEASE_SHA` in `/etc/bitbox/bitbox.env` so `/health` reports what is
actually running, restarts the services, and requires `/health.release_sha` to
match the rollback commit. A missing frontend release, malformed commit,
dependency restoration failure, or release mismatch makes rollback fail loudly. The
deployment run still fails, so a red run always means "look at this", never
"production is silently broken".

The rollback path is exercised on every CI run by `deploy/rollback_test.sh`
(wrapped by `tests/test_rollback_script.py`), which stubs `systemctl`, `curl` and
`pip` and runs the real script against a temporary repository. It covers a
healthy rollback, a rollback whose backend never recovers, a malformed commit
value, a missing previous release, and a host with no alert webhook.

To roll back manually:

```bash
sudo BITBOX_ROLLBACK_TO_SHA=<40-character commit>      BITBOX_ROLLBACK_TO_RELEASE=/var/www/bitbox-releases/<commit>      bash /home/ubuntu/BITBOX/deploy/rollback.sh
```

Only the immediately previous release is guaranteed to still exist; the cleanup
step keeps it even when it is older than the 14-day retention window. Do not
edit production source files directly.

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

## Kiosk device checks

The kiosk browser, not the server, decides whether Korean is readable and audible.
Run these once on every new device before treating it as working.

```bash
fc-list :lang=ko | head          # 비어 있어도 앱이 글꼴을 번들하므로 화면은 정상입니다
aplay -l                         # 스피커
arecord -l                       # 마이크
```

In the kiosk browser console at the production origin:

```js
window.isSecureContext                                   // getUserMedia 전제, true 여야 함
speechSynthesis.getVoices().filter(v => v.lang.startsWith('ko'))   // 비어 있으면 서버 음성으로 대체됩니다
['audio/webm;codecs=opus','audio/mp4'].filter(t => MediaRecorder.isTypeSupported(t))
navigator.permissions.query({name:'microphone'}).then(r => console.log(r.state))
```

An empty Korean voice list is expected on a minimal Linux image and is handled:
the app falls back to `POST /api/speech`. Watch that endpoint's volume after
deploying to such a device, because every announcement that would have been free
now costs a synthesis call until the cache warms.

Launch flags that matter for unattended operation:

```bash
chromium-browser --kiosk https://<domain>   --autoplay-policy=no-user-gesture-required   --use-fake-ui-for-media-stream   --noerrdialogs --disable-session-crashed-bubble
```

`--use-fake-ui-for-media-stream` auto-accepts the microphone prompt. For a
long-lived install prefer a Chromium policy (`AudioCaptureAllowedUrls`) scoped to
the production origin instead of a blanket flag.

## Single-host recovery

Everything runs on one EC2 instance: Nginx, the Uvicorn backend, the SQLite
usage counter, and the TLS certificate. That host is a single point of failure
and losing it takes the kiosk offline. There is no automatic failover; recovery
is a rebuild. Rehearse it before relying on it.

State that must survive the instance:

| Path | Contents | Recoverable from |
| --- | --- | --- |
| `/etc/bitbox/bitbox.env` | API keys, `RELEASE_SHA`, station defaults | GitHub Actions secrets (redeploy regenerates it) |
| `/etc/letsencrypt/` | TLS certificate and private key | Certbot reissues on a fresh host |
| `/var/lib/bitbox/usage.sqlite3` | Daily paid-request counters | Not recoverable; resets the daily budget |
| `/var/www/bitbox-releases/` | Built frontend releases | Rebuilt by a deployment |
| `/home/ubuntu/BITBOX` | Deployment work tree | `git clone` |

Rebuild procedure:

1. Launch a fresh Ubuntu instance and allow inbound `80/443` in the security
   group.
2. Point `BITBOX_SERVER_NAME` at the new address, and update the `EC2_HOST`
   secret. The deployment refuses to request a certificate when the name does
   not resolve to the host, so DNS must settle first.
3. `git clone` the repository to `/home/ubuntu/BITBOX` and create `.venv`.
4. Re-run the `Deploy merged app to EC2` workflow. It installs Nginx, Certbot and
   rsync, issues the certificate, writes `/etc/bitbox/bitbox.env` from secrets,
   installs the systemd units and timers, and verifies the public boundary.
5. Confirm `release_sha` on `/health` matches the deployed commit, and that
   `certbot.timer` and `bitbox-healthcheck.timer` are active.

The daily usage counter starts from zero on the new host, so paid-provider spend
for that day is effectively reset. Reduce `VOICE_DAILY_REQUEST_LIMIT` for the
remainder of the day if that matters.

Until a second instance exists, treat the recovery time objective as "manual
rebuild", not "minutes".

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
