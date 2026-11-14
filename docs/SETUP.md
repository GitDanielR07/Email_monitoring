# Gmail Push Notifications — Google Cloud Setup

One-time setup so Gmail can notify the monitor instantly. Do everything in the **same Google Cloud project** that owns your Gmail OAuth credentials (the `project_id` inside `config/credentials.json`).

Cost: the Gmail API is free, and Pub/Sub's first 10 GiB/month is free — Gmail notifications are tiny, so normal use stays at $0.

---

## 1. Enable the Pub/Sub API

Console → **APIs & Services → Library** → search **Cloud Pub/Sub API** → **Enable**.
(If the Pub/Sub → Topics page loads without an "Enable" button, it's already on.)

## 2. Create the topic and subscription

1. **Pub/Sub → Topics → Create topic**
2. Topic ID: `gmail-notifications`, keep **Add a default subscription** ticked → **Create**
3. In **Subscriptions**, make sure one named `gmail-notifications-sub` exists with delivery type **Pull**. Create it if the default got a different name.

## 3. Let Gmail publish to the topic

1. Open the `gmail-notifications` topic → **Permissions** panel → **Add principal**
2. Principal: `gmail-api-push@system.gserviceaccount.com`
3. Role: **Pub/Sub Publisher** → **Save**

## 4. Create a service account key (lets the monitor read the subscription)

1. **IAM & Admin → Service Accounts → Create service account**, name e.g. `email-monitor`
2. Role: **Pub/Sub Subscriber** → **Done**
3. Open the account → **Keys → Add key → Create new key → JSON**
4. Save the downloaded file as `config/service-account-key.json`

## 5. Fill in `.env`

```env
GOOGLE_CLOUD_PROJECT=your-project-id
PUBSUB_TOPIC=gmail-notifications
PUBSUB_SUBSCRIPTION=gmail-notifications-sub
GOOGLE_APPLICATION_CREDENTIALS=config/service-account-key.json
DISCORD_MENTION_ID=your_discord_user_id   # optional, for @mentions
```

To find your Discord user ID: Discord settings → Advanced → enable **Developer Mode**, then right-click your name → **Copy User ID**.

## 6. Verify and run

```powershell
.venv\Scripts\python.exe scripts\validate_setup.py
.venv\Scripts\python.exe src\monitor_email_push.py
```

Expected output:

```
✅ Gmail watch setup successful!
✅ Gmail watch is active. Listening for incoming emails...
📬 Subscribing to: projects/<project>/subscriptions/gmail-notifications-sub
```

Send yourself an email from another account — it should appear in Discord within a couple of seconds. Then build the exe for everyday use (see the [README](../README.md#running-it)).

---

## Troubleshooting

| Error / symptom | Cause and fix |
|---|---|
| `GOOGLE_CLOUD_PROJECT not set` | Missing from `.env` |
| `Failed to set up Gmail watch` … permission | Step 3 not done (Gmail can't publish to the topic) |
| `Failed to subscribe` … `403` / credentials | Step 4: key missing, wrong path, or account lacks **Pub/Sub Subscriber** |
| Watch works but nothing posts | Another monitor (e.g. old `monitor_email.exe`) is marking emails read first — close it |
| "Domain restricted sharing" when adding the Gmail principal | An org policy blocks external principals; the project owner must allow it for this project |
