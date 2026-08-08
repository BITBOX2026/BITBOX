# BITBOX Operations Runbook

## Service objectives

- Public HTTPS and `/health`: available during normal operation.
- `/ready`: returns `200` only after application startup validation succeeds.
- Bus arrival board: refreshes every 15 seconds and keeps the last successful data on transient failure.
- Route requests: backend timeout 30 seconds, browser timeout 35 seconds, proxy timeout 40 seconds.

## Monitoring

Monitor these endpoints from outside EC2 at one-minute intervals:

- `GET https://<domain>/health`
- `GET https://<domain>/ready`
- `GET https://<domain>/`

Alert after two consecutive failures. Application logs are available through
`journalctl -u bitbox-backend.service`; Nginx JSON access and error logs are in
`/var/log/nginx/bitbox_access.log` and `/var/log/nginx/bitbox_error.log` and are
retained for 14 rotations.

The local `bitbox-healthcheck.timer` checks `/ready` every minute. Three
consecutive failures restart the backend and write an event to the system log.
This is self-recovery, not external uptime monitoring; an independent monitor
must still alert when the whole instance or network is unavailable.

For a Slack-compatible alert webhook, add the HTTPS URL as the repository
Actions secret `BITBOX_ALERT_WEBHOOK_URL`. The deployment writes it to
`/etc/bitbox/monitoring.env` with mode `600`. The local healthcheck sends an
alert after three failures before restarting the backend. Keep this value out
of Git and rotate the webhook if it is exposed.

Local runtime counters, paid-request usage and external circuit states are
available only from EC2 with `curl http://127.0.0.1:8001/internal/status`.
Nginx returns `404` for every external `/internal/` request.

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
least 14 days of TLS certificate validity. A failed public-boundary check fails
the deployment run even when the EC2-local check passed.

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

## Capacity and scaling

Run a non-billable liveness smoke test with:

```bash
python scripts/load_smoke.py --url https://<domain>/health --requests 500 --concurrency 50
```

The current deployment is one EC2 instance. Before claiming high availability,
add at least two instances behind an Application Load Balancer, shared Redis for
distributed rate limits/cache, managed monitoring, and automated instance health
replacement. Provider quotas and billing alerts must be configured independently.

The in-process daily limits are emergency cost guards, not billing controls. They
reset on process restart and are not shared across instances. Use API Gateway/WAF
and provider-side hard quotas before horizontal scaling.
