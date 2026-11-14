# 🚀 Gmail Push Notifications - Your Setup Instructions

**STATUS:** Ready to use! Follow the steps below. ⚡

---

## 📝 What You Need To Do

### Step 1️⃣ : Add Environment Variables (2 minutes)

Edit your `.env` file and add these three lines:

```env
GOOGLE_CLOUD_PROJECT=your-project-id-12345
PUBSUB_TOPIC=gmail-notifications
PUBSUB_SUBSCRIPTION=gmail-notifications-sub
```

**Where to find your Project ID:**
1. Go to https://console.cloud.google.com
2. Click the Settings gear icon (top-right)
3. Click "Project Settings"
4. Copy the "Project ID" field

---

### Step 2️⃣ : Create Pub/Sub Topic (3 minutes)

1. Go to https://console.cloud.google.com
2. Go to **Pub/Sub** > **Topics**
3. Click **Create Topic**
4. Topic ID: `gmail-notifications`
5. Click **Create**
6. Click on your new topic
7. Click **Create Subscription**
   - Subscription ID: `gmail-notifications-sub`
   - Delivery Type: **Pull**
   - Click **Create**

---

### Step 3️⃣ : Set Permissions (2 minutes)

1. Go to your Pub/Sub Topic: `gmail-notifications`
2. Click **Permissions** tab
3. Click **Grant Access** or **Add Principal**
4. Principal: `gmail-api-push@system.gserviceaccount.com`
5. Role: **Pub/Sub Publisher**
6. Click **Save**

---

### Step 4️⃣ : Run the Monitor (1 minute)

Open terminal and run:

```bash
cd D:\VScode\email_checker
python monitor_email_push.py
```

**Expected output:**
```
✅ Gmail watch setup successful!
✅ Gmail watch is active. Listening for incoming emails...
🌐 Starting health check server on http://localhost:5000
```

---

### Step 5️⃣ : Test It! (1 minute)

1. Send yourself an email from another account
2. Check your Discord channel
3. You should see the email **instantly!** ⚡

---

## 🔍 Verify Your Setup

Run this to check if everything is configured correctly:

```bash
python validate_setup.py
```

It will show:
- ✅ or ❌ for each environment variable
- ✅ or ❌ for required files
- ✅ or ❌ for Python packages

---

## ❓ Something Not Working?

### "I don't see the GOOGLE_CLOUD_PROJECT in the console"
→ You might be in the wrong Google account. Make sure you're logged into the account with the Google Cloud project.

### "No emails showing up"
→ Run `python validate_setup.py` to check everything  
→ Check the logs: `logs/monitor_email_push.log`  
→ Make sure your Discord webhook URL is correct

### "Permission denied when running the script"
→ Verify Pub/Sub permissions are set correctly (Step 3)  
→ Make sure you're using the right Google account

### "Module not found: google.cloud.pubsub_v1"
→ Run: `pip install google-cloud-pubsub flask`

---

## 📚 Full Documentation

- **Full Setup Guide:** `PUSH_NOTIFICATION_SETUP.md` (detailed, step-by-step)
- **Quick Reference:** `QUICK_START.md` (checklist format)
- **Overview:** `SETUP_COMPLETE.md` (comparison and info)

---

## 🎯 Key Points

| Item | Details |
|------|---------|
| **Script to Run** | `python monitor_email_push.py` |
| **Speed** | Instant (vs 10 min with old script) |
| **Keep Running** | Yes, keep terminal open |
| **Old Script** | `python monitor_email.py` (still works) |
| **Logs** | `logs/monitor_email_push.log` |

---

## ✨ That's It!

Once you complete these 5 steps, you're done! 🎉

The monitor will:
- ✅ Listen for new emails 24/7
- ✅ Send them to Discord instantly
- ✅ Mark them as read automatically
- ✅ Log everything for troubleshooting

---

**Questions?** Check the detailed guides linked above!  
**Ready?** Follow the 5 steps above and you're all set! 🚀
