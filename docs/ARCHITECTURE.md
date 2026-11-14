# Architecture

```
 New email lands in Gmail INBOX
              │
              ▼
 Gmail watch ──publishes──▶ Pub/Sub topic: gmail-notifications
                                   │
                                   ▼
                     Pub/Sub subscription: gmail-notifications-sub (pull)
                                   │  streaming pull, one message at a time
                                   ▼
            monitor_email_push (src/monitor_email_push.py or the exe)
              1. history.list(startHistoryId=last seen) → IDs added to INBOX
              2. fetch each message, clean the body
              3. POST embed to Discord webhook (with optional @mention)
              4. on success, mark the email as read in Gmail
```

## Components

| Piece | Role |
|---|---|
| **Gmail watch** (`users.watch`) | Tells Gmail to publish a notification to the topic whenever the mailbox changes. Expires after 7 days; the monitor renews it every 24 h. |
| **Pub/Sub topic + subscription** | Message broker between Gmail and your PC. Gmail publishes via `gmail-api-push@system.gserviceaccount.com`; the monitor pulls using the service account key. |
| **History cursor** | A notification only says "something changed" plus a `historyId`. The monitor keeps the last `historyId` it handled and asks Gmail what was added to the INBOX since then, so only genuinely new mail is forwarded. |
| **Discord webhook** | Receives the formatted embed. |
| **Health endpoint** | Flask on `http://localhost:5000/health`, handy for checking the windowless exe is alive. |

## Concurrency

The Gmail client (httplib2) is not thread-safe, while Pub/Sub delivers callbacks on a thread pool. The monitor therefore limits delivery to one message at a time (`FlowControl(max_messages=1)`) and guards every Gmail call with a lock. Without this, concurrent requests corrupt the shared connection (SSL errors, crashes).

## Push vs. the legacy poller

| | `src/legacy/monitor_email.py` | `src/monitor_email_push.py` |
|---|---|---|
| Trigger | Checks every 5 minutes | Gmail notifies on arrival |
| Delay | Up to 5 minutes | ~1–2 seconds |
| Filtering | Allowed-sender list only | All new INBOX mail |
| Needs Google Cloud Pub/Sub | No | Yes ([SETUP.md](SETUP.md)) |

## Files and settings

- `.env` — webhook, mention ID, Gmail paths, Pub/Sub names (see `.env.example`)
- `config/credentials.json` — Gmail OAuth client
- `config/token.json` — Gmail OAuth token (created on first run)
- `config/service-account-key.json` — Pub/Sub subscriber key
- `logs/monitor_email_push.log` — runtime log
