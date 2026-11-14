# Gmail Push Notifications - Quick Setup Checklist

## ✅ Quick Start (5-10 minutes)

### Google Cloud Console Setup:
- [ ] Go to https://console.cloud.google.com
- [ ] Select your project
- [ ] Enable "Cloud Pub/Sub API" (APIs & Services > Library)
- [ ] Create Topic: `gmail-notifications` (Pub/Sub > Topics > Create)
- [ ] Create Subscription: `gmail-notifications-sub` (open topic > Create Subscription)
- [ ] Copy your **Project ID** from Settings (top-right gear icon)

### Local Setup:
- [ ] Add to `.env`:
  ```
  GOOGLE_CLOUD_PROJECT=your-project-id-here
  PUBSUB_TOPIC=gmail-notifications
  PUBSUB_SUBSCRIPTION=gmail-notifications-sub
  ```
- [ ] Run: `pip install -q google-cloud-pubsub flask`
- [ ] Run: `python monitor_email_push.py`

### Permission Setup:
- [ ] Go to Pub/Sub Topic: `gmail-notifications`
- [ ] Add Permission: `gmail-api-push@system.gserviceaccount.com` > Role: `Pub/Sub Publisher`

### Test:
- [ ] Verify script shows: `✅ Gmail watch setup successful!`
- [ ] Send test email to your account
- [ ] Check Discord for instant notification 🎉

---

## 📋 Files Created

| File | Purpose |
|------|---------|
| `monitor_email_push.py` | Real-time push notification monitor |
| `PUSH_NOTIFICATION_SETUP.md` | Detailed setup guide (THIS FILE) |
| `requirements.txt` | Updated with Pub/Sub + Flask |

---

## 🚀 Running Your Monitor

```bash
# Real-time (instant notifications) ⚡
python monitor_email_push.py

# Old way (10-min checks)
python monitor_email.py
```

---

## 🔧 Troubleshooting

**Script won't start?**
```bash
pip install google-cloud-pubsub flask
```

**No emails showing up?**
1. Check Discord webhook in `.env`
2. Check Project ID matches
3. Look at: `logs/monitor_email_push.log`
4. Send yourself a test email

**"Permission denied"?**
1. Verify Pub/Sub topic permissions are set
2. Make sure Gmail API service account has Publisher role

---

## 📚 Need More Help?

See full guide: `PUSH_NOTIFICATION_SETUP.md`

Questions? Check the detailed setup guide for troubleshooting section!
