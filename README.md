# 📧 Email Monitor to Discord

Forwards new Gmail messages to a Discord channel **the moment they arrive**, using Gmail push notifications (Google Cloud Pub/Sub). Each email is posted as a clean embed and can @mention you so your phone pings.

## Project structure

```
email_checker/
├── monitor_email_push.exe     # Built app (created by build.py, not committed)
├── build.py                   # Builds the exe
├── requirements.txt
├── .env / .env.example        # Your settings (.env is never committed)
├── src/
│   ├── monitor_email_push.py  # The monitor (real-time, push-based)
│   └── legacy/                # Old 5-minute polling monitor and helpers
├── scripts/
│   ├── validate_setup.py      # Checks .env, keys and packages
│   └── delete_read_emails.py  # Optional: bulk-delete read, unstarred mail
├── packaging/
│   └── monitor_email_push.spec  # PyInstaller config used by build.py
├── docs/
│   ├── SETUP.md               # Google Cloud / Pub/Sub setup, step by step
│   └── ARCHITECTURE.md        # How the pieces fit together
├── config/                    # credentials.json, token.json, service-account-key.json (not committed)
├── assets/                    # App icon
└── logs/                      # monitor_email_push.log (not committed)
```

## First-time setup

1. **Install dependencies** (inside the project's virtual environment):
   ```powershell
   python -m venv .venv
   .venv\Scripts\python.exe -m pip install -r requirements.txt
   ```
2. **Gmail API OAuth credentials** → save as `config/credentials.json`
   (Google Cloud Console → APIs & Services → Credentials → OAuth client ID → Desktop app).
3. **Pub/Sub topic, subscription and service account** → follow [docs/SETUP.md](docs/SETUP.md).
4. **Settings** → copy `.env.example` to `.env` and fill it in.
5. **Check everything:**
   ```powershell
   .venv\Scripts\python.exe scripts\validate_setup.py
   ```
6. **First run** opens a browser to authorize Gmail; this creates `config/token.json`.

## Running it

### Option A — the exe (recommended)

```powershell
.venv\Scripts\python.exe build.py     # build (or rebuild after code changes)
.\monitor_email_push.exe              # or just double-click it
```

The exe has **no window**; it runs in the background. To confirm it's alive:

- open http://localhost:5000/health, or
- read `logs\monitor_email_push.log`.

**Stop it:** Task Manager → `monitor_email_push.exe` → End task, or
```powershell
taskkill /IM monitor_email_push.exe /F
```

**Start automatically with Windows:** press `Win + R`, type `shell:startup`, and put a shortcut to `monitor_email_push.exe` in that folder.

> Only run **one** copy at a time, and don't run the old `monitor_email.exe` alongside it — both mark emails as read and will compete.

### Option B — straight from Python (for development)

```powershell
.venv\Scripts\python.exe src\monitor_email_push.py
```

Logs print to the terminal; `Ctrl + C` stops it.

## Behaviour

- Forwards every new Inbox email as it arrives (green embed).
- **Catches up after downtime:** it saves its place in `config/monitor_state.json`. On the next start, emails that arrived while it was off are sent oldest-first as **amber embeds labelled "Missed while offline"**. These are sent even if you've already read them.
- Every embed shows when Gmail **received** the email, in each viewer's own timezone (e.g. "November 15, 2026 5:40 AM (2 hours ago)").
- The very first run starts from "now"; it does not dump your existing inbox. Delete `config/monitor_state.json` to reset to that.
- Marks an email as read **only after** Discord accepts it; failed sends are retried on the next sync.
- **Security emails are never forwarded.** Verification codes, password resets, sign-in/security alerts, 2FA and email-confirmation messages appear in Discord only as a grey "🔒 Security email (content hidden)" notice: sender and time, no subject, body, links or image. They stay **unread** in Gmail, and the log doesn't record their subject. Add your own trigger phrases with `SENSITIVE_KEYWORDS=phrase one,phrase two` in `.env`.
- Renews the Gmail watch every 24 hours (Gmail expires watches after 7 days).
- Restarts the Pub/Sub listener automatically if it drops.

## Customization

In `src/monitor_email_push.py`, `send_email_embed()` controls the embed: color (`0x00E676`), icon, and fields.

## Troubleshooting

| Problem | Fix |
|---|---|
| Nothing posts to Discord | Check `logs\monitor_email_push.log`; make sure only one monitor is running |
| `GOOGLE_CLOUD_PROJECT not set` / permission errors | Re-check `.env` and [docs/SETUP.md](docs/SETUP.md) step 3–4 |
| Gmail auth fails | Delete `config\token.json` and run again to re-authorize |
| Exe starts then disappears | Run the Python version (Option B) to see the error |

## Security

Never commit `.env`, `config/` (OAuth credentials, token, service-account key), or your Discord webhook URL. `.gitignore` already excludes them.

## License

MIT
