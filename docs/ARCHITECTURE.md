# Gmail Push Notifications - Architecture Overview

## How It Works

```
┌─────────────────────────────────────────────────────────────────┐
│                          NEW EMAIL ARRIVES                      │
└────────────────────────────────┬────────────────────────────────┘
                                 │
                                 ▼
                    ┌────────────────────────┐
                    │   Gmail Inbox Gets    │
                    │    New Message        │
                    └────────────┬───────────┘
                                 │
                                 ▼
                    ┌────────────────────────────────┐
                    │  Gmail API Triggers Watch      │
                    │  Notification                 │
                    └────────────┬───────────────────┘
                                 │
                                 ▼
            ┌────────────────────────────────────────────┐
            │  Google Cloud Pub/Sub Topic                │
            │  (gmail-notifications)                     │
            │  Receives notification from Gmail          │
            └────────────┬───────────────────────────────┘
                         │
                         ▼
         ┌──────────────────────────────────────────────┐
         │  Your Computer (monitor_email_push.py)       │
         │  • Subscribed to Pub/Sub topic              │
         │  • Receives notification instantly          │
         │  • Pulls full email from Gmail API          │
         │  • Cleans up email body                     │
         │  • Creates Discord embed                    │
         └────────┬─────────────────────────────────────┘
                  │
                  ▼
         ┌──────────────────────────┐
         │  Discord Webhook URL    │
         │  Posts message to       │
         │  your Discord channel   │
         └──────────┬──────────────┘
                    │
                    ▼
         ┌──────────────────────────┐
         │  Your Discord Server     │
         │  📧 Email notification!  │
         └──────────────────────────┘
         
         Meanwhile:
         
         ▼────────────────────────────────▼
         Gmail API marks email as read
         in your Gmail inbox
```

---

## File Structure

```
email_checker/
│
├── Core Scripts (Pick ONE to run):
│   ├── monitor_email.py              (Old: checks every 10 min)
│   └── monitor_email_push.py          (New: real-time) ⭐
│
├── Utilities:
│   ├── validate_setup.py              (Check your setup)
│   ├── email_helper.py                (Email processing)
│   └── utils.py                       (Helper functions)
│
├── Configuration:
│   ├── .env                           (Your secrets)
│   ├── requirements.txt               (Python packages)
│   └── config/
│       ├── credentials.json           (Gmail OAuth)
│       └── token.json                 (Gmail token)
│
├── Documentation (READ THESE):
│   ├── START_HERE.md                  (Quick guide) ⭐
│   ├── PUSH_NOTIFICATION_SETUP.md    (Detailed steps)
│   ├── QUICK_START.md                (Checklist)
│   └── SETUP_COMPLETE.md             (Overview)
│
├── Build:
│   ├── build.py                       (Build to exe)
│   ├── monitor_email.exe              (Pre-built exe)
│   └── monitor_email.spec             (PyInstaller config)
│
└── Logs:
    └── logs/
        ├── monitor_email.log          (Old monitor logs)
        └── monitor_email_push.log     (New monitor logs)
```

---

## Components Explained

### 1. **Gmail API Watch** 
   - Registers with Gmail to watch your INBOX
   - When new email arrives, Gmail notifies us

### 2. **Google Cloud Pub/Sub**
   - Acts as a message broker between Gmail and your computer
   - Gmail publishes notifications to the topic
   - Your script subscribes to receive them

### 3. **monitor_email_push.py**
   - Listens for notifications from Pub/Sub
   - Fetches full email from Gmail API
   - Processes and cleans the email
   - Sends to Discord webhook

### 4. **Discord Webhook**
   - Your endpoint to post messages to Discord
   - Receives formatted email embeds
   - Posts to your channel instantly

---

## Data Flow Timeline

```
0ms     ➜ Someone sends you an email
        
1-2ms   ➜ Email reaches Gmail servers
        
3-5ms   ➜ Gmail API detects new message
        
5-10ms  ➜ Gmail publishes to Pub/Sub topic
        
10-50ms ➜ Pub/Sub delivers notification to your PC
        
50-100ms ➜ Your script receives notification
        
100-200ms ➜ Script fetches full email from Gmail
        
200-300ms ➜ Script processes and cleans email
        
300-400ms ➜ Script posts to Discord
        
400-500ms ➜ You see the notification! ⚡

TOTAL: ~0.5 seconds from send to Discord!
```

---

## Environment Variables Needed

```env
# Existing (you already have these):
DISCORD_WEBHOOK_EMAIL=https://discord.com/api/webhooks/...
STUDENT_EMAIL=your_email@gmail.com
GMAIL_CREDENTIALS_FILE=config/credentials.json
GMAIL_TOKEN_FILE=config/token.json

# New (add these for push notifications):
GOOGLE_CLOUD_PROJECT=your-project-id-12345
PUBSUB_TOPIC=gmail-notifications
PUBSUB_SUBSCRIPTION=gmail-notifications-sub

# Optional:
GOOGLE_APPLICATION_CREDENTIALS=./service-account-key.json
DISCORD_MENTION_ID=your_discord_user_id
```

---

## Comparison: Polling vs Push

### OLD WAY (Polling) - monitor_email.py
```
10:00 ➜ Check Gmail  ➜ No new emails
10:10 ➜ Check Gmail  ➜ No new emails
10:20 ➜ Check Gmail  ➜ 3 new emails! Send to Discord
       ➜ Delay: ~10 minutes before Discord notification
```

### NEW WAY (Push) - monitor_email_push.py
```
10:00 ➜ Gmail has new email
       ➜ Pub/Sub sends notification
       ➜ Your script receives instantly
       ➜ Posts to Discord ~0.5 seconds later
       ➜ Delay: <1 second ⚡
```

---

## Security Considerations

1. **Your Discord Webhook**
   - Keep in `.env` (never commit)
   - Can only post to your channel
   - Can be regenerated anytime

2. **Gmail Credentials**
   - Stored in `config/credentials.json`
   - Never commit to GitHub
   - Scoped to only read/modify emails

3. **Google Cloud Project**
   - You control all access
   - Can revoke at any time
   - Costs: Pub/Sub is free for first 10GB/month

---

## Troubleshooting Guide

| Issue | Solution |
|-------|----------|
| No emails showing | Check Discord webhook URL, verify Project ID |
| "Permission denied" | Set Pub/Sub permissions (see START_HERE.md) |
| Script won't start | Run: `pip install google-cloud-pubsub flask` |
| Old emails showing | This is normal - first run loads recent emails |
| Nothing happens | Check logs: `logs/monitor_email_push.log` |

---

## Next Steps

1. ✅ Read: `START_HERE.md`
2. ✅ Follow: 5-step setup guide
3. ✅ Run: `python monitor_email_push.py`
4. ✅ Test: Send yourself an email
5. ✅ Celebrate: Instant Discord notifications! 🎉

---

**Architecture Question?** This overview covers the complete flow!  
**Ready to implement?** Open `START_HERE.md` now! 🚀
