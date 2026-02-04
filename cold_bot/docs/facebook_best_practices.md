# Facebook Marketplace Scraping Best Practices

This project is intended for low-volume, ethical, and compliant usage. Facebook prohibits automated scraping in its ToS; use at your own risk and prefer public data only.

## Access & Session
- Prefer **manual login** in a normal browser session.
- If automation is used, avoid automating credentials.
- Use **logged-in user sessions** if absolutely necessary and you have permission.

## Rate Limits
- Keep volumes low: **8–12 requests/minute max**.
- Add randomized delays (3–12 seconds) between actions.
- Avoid rapid or repeated page refreshes.

## Behavior Mimicry
- Use human-like scrolling and pauses.
- Randomize viewport sizes and user agents.
- Avoid headless mode for high-block pages.

## Proxies & IP
- Consider residential proxies if blocked.
- Keep a stable IP when logged in to avoid suspicious activity.

## Data Ethics
- Use public listings only.
- Avoid private data, DMs, or account scraping without consent.
- Provide opt-out messaging and avoid spam.

## Operational Safety
- Log all actions for auditability.
- Implement max actions per hour.
- Stop scanning if detection or blocks are observed.
