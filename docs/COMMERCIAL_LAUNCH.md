# Commercial launch gate

## Implemented in the repository

- Voice processing consent, withdrawal and local recent-search deletion.
- Stale arrival-data warning and last-successful-data behavior.
- Per-IP rate limits, in-process concurrency guards and restart-persistent
  single-instance daily cost guards.
- Retry, timeout, response-size validation and external API circuit breakers.
- Privacy-safe request IDs, local runtime counters and optional alert webhook.
- HTTPS, CSP, strict host handling, cross-site request blocking and security headers.
- Bandit, pip-audit, npm audit, CodeQL, unit, build and browser E2E checks.
- Pinned direct dependencies, automated deployment, health recovery and rollback path.

## Owner actions required before unrestricted public launch

These items require an AWS account decision, a paid/managed product, legal owner
information or real users. They cannot be truthfully completed by a code change.

- Put CloudFront or an Application Load Balancer and AWS WAF in front of the app.
  Configure managed rules, provider-side quotas and AWS Budget alarms.
- Remove the single-EC2 failure point with at least two instances and shared
  Redis-backed rate limits/cache, or formally accept single-instance availability.
- Store and rotate provider keys with AWS Secrets Manager or Parameter Store and
  use a least-privilege instance/deployment role.
- Add the real alert webhook as the GitHub Actions secret
  `BITBOX_ALERT_WEBHOOK_URL`; deployment installs it on EC2 automatically. Add
  paging notifications for the scheduled external uptime workflow, 5xx rate
  and latency. Ensure the monitor workflow is merged to the default branch so
  GitHub actually schedules it.
- Replace generic in-app privacy text with the operator's legal name, contact,
  provider retention terms and counsel-reviewed privacy policy.
- Run field tests with wheelchair users, older adults and screen-reader users;
  record pass/fail evidence for arrival accuracy, audio, glare and touch targets.
- Confirm an HTTPS endpoint or compensating control for the Seoul bus provider's
  HTTP-only interface, and rotate that provider key on a schedule.
- Register `https://3-144-238-75.sslip.io` as a JavaScript SDK web domain in
  Kakao Developers. Until registration, the UI intentionally shows the route
  sequence fallback instead of a blank map.
- Define and test RTO/RPO, incident ownership and restoration from a fresh EC2
  instance before advertising an availability commitment.

The service is not commercially approved until every applicable owner action has
an accountable person, evidence and an acceptance date.
