# Gmail Push Notifications Setup Guide

This guide will help you set up real-time Gmail push notifications for instant email alerts to Discord.

## Prerequisites

- Google Cloud Project (already created)
- Gmail API already enabled
- Service account credentials (optional, or use existing OAuth credentials)
- Python packages installed: `google-cloud-pubsub`, `flask`

---

## Step 1: Create Google Cloud Pub/Sub Topic

### 1.1 Go to Google Cloud Console
- Navigate to: https://console.cloud.google.com
- Select your project from the dropdown

### 1.2 Enable Pub/Sub API
- Go to **APIs & Services** > **Library**
- Search for **"Cloud Pub/Sub API"**
- Click it and press **Enable** button

### 1.3 Create a Pub/Sub Topic
- Go to **Pub/Sub** > **Topics**
- Click **Create Topic**
- Topic ID: `gmail-notifications`
- Click **Create Topic**

### 1.4 Create a Subscription
- Open the topic you created (`gmail-notifications`)
- Click **Create Subscription**
- Subscription ID: `gmail-notifications-sub`
- Delivery Type: **Pull** (keep default)
- Click **Create Subscription**

---

## Step 2: Get Your Google Cloud Project ID

1. Go to **Settings** (gear icon in top-right) > **Project Settings**
2. Find and copy your **Project ID** (looks like: `my-project-12345`)
3. Save this - you'll need it soon

---

## Step 3: Create a Service Account (Optional but Recommended)

### Why? Service accounts allow Pub/Sub to push notifications without user authentication.

1. Go to **APIs & Services** > **Credentials**
2. Click **Create Credentials** > **Service Account**
3. Fill in:
   - Service account name: `gmail-push-notifications`
   - Service account ID: (auto-fill)
   - Click **Create and Continue**
4. Grant roles:
   - Click **Continue** (roles are optional for local setup)
   - Click **Done**

### 4.1 Create a Key
1. Click on the service account you just created
2. Go to **Keys** tab
3. Click **Add Key** > **Create new key**
4. Key type: **JSON**
5. Click **Create**
6. A JSON file downloads automatically
7. Save it to your project folder as: `service-account-key.json`

---

## Step 4: Configure Your .env File

Add these variables to your `.env` file:

```env
# Existing variables (keep these)
DISCORD_WEBHOOK_EMAIL=your_discord_webhook_url
DISCORD_MENTION_ID=your_discord_id_for_mentions
STUDENT_EMAIL=your_email@gmail.com
GMAIL_CREDENTIALS_FILE=config/credentials.json
GMAIL_TOKEN_FILE=config/token.json

# NEW: Push Notification Variables
GOOGLE_CLOUD_PROJECT=your-project-id-12345
PUBSUB_TOPIC=gmail-notifications
PUBSUB_SUBSCRIPTION=gmail-notifications-sub
GOOGLE_APPLICATION_CREDENTIALS=./service-account-key.json
```

Replace:
- `your-project-id-12345` with your actual Project ID from Step 2

---

## Step 5: Allow Gmail API to Use Pub/Sub

The Gmail API needs permission to publish to your Pub/Sub topic.

### 5.1 Get Your Gmail API Service Account Email
1. Go to **APIs & Services** > **Credentials**
2. Find your Gmail API credentials (should be "Desktop application" type)
3. If you don't see it, you may use your personal Google account instead

### 5.2 Grant Permissions to Pub/Sub Topic
1. Go to **Pub/Sub** > **Topics** > **gmail-notifications**
2. Click **Permissions** (or **Show Info** > **Permissions**)
3. Click **Add Principal** or **Grant Access**
4. Add:
   - **Principal:** `gmail-api-push@system.gserviceaccount.com` (Gmail's system account)
   - **Role:** `Pub/Sub Publisher`
5. Click **Save**

> Note: Gmail uses a system service account to push notifications

---

## Step 6: Test the Setup

### 6.1 Run the Push Notification Monitor
```bash
cd D:\VScode\email_checker
python monitor_email_push.py
```

You should see:
```
======================================================================
Gmail Push Notification Monitor
======================================================================
📧 Email: your_email@gmail.com
🔔 Discord Webhook: Configured
☁️  Google Cloud Project: your-project-id-12345
📬 Pub/Sub Topic: gmail-notifications
======================================================================
🔔 Setting up Gmail watch on: projects/your-project-id/topics/gmail-notifications
✅ Gmail watch setup successful!
📬 Subscribing to: projects/your-project-id/subscriptions/gmail-notifications-sub
✅ Gmail watch is active. Listening for incoming emails...
```

### 6.2 Test with an Email
1. Send an email to your Gmail account from another email address
2. Check your Discord channel - you should get an instant notification! ⚡

---

## Step 7: Troubleshooting

### Problem: "GOOGLE_CLOUD_PROJECT not set"
- **Solution:** Make sure you added `GOOGLE_CLOUD_PROJECT` to your `.env` file with the correct Project ID

### Problem: "Permission denied" errors
- **Solution:** 
  1. Check that Gmail API service account has access to Pub/Sub topic
  2. Verify your Project ID is correct
  3. Re-check Pub/Sub topic permissions

### Problem: No emails arriving
- **Solution:**
  1. Check your Discord webhook URL is correct
  2. Verify `monitor_email_push.py` is running
  3. Check logs in `logs/monitor_email_push.log`
  4. Send test email to your account

### Problem: "google-cloud-pubsub not found"
- **Solution:** Run:
  ```bash
  pip install google-cloud-pubsub flask
  ```

---

## Step 8: Production Setup

For production use (not local testing):

1. **Use a VM or Server:** Deploy on a cloud VM (Google Cloud, AWS, etc.) instead of your local machine
2. **Enable Pub/Sub Subscription Manager:** Set up a background process to keep the subscriber running
3. **Add Error Handling:** The code already includes logging; configure log rotation
4. **Security:** Use secrets manager instead of plain `.env` files
5. **Monitoring:** Set up alerts for failed notifications

---

## FAQ

**Q: Will this drain my battery/disk space?**
A: No, push notifications are very efficient. They only trigger when emails arrive.

**Q: Can I switch back to 10-minute checks?**
A: Yes, just run `monitor_email.py` instead of `monitor_email_push.py`

**Q: What's the difference between the two monitors?**
- `monitor_email.py` - Checks every 10 minutes (polling)
- `monitor_email_push.py` - Real-time via Pub/Sub (pushing)

**Q: Do I need to keep the Flask server running?**
A: Yes, it provides a health check endpoint. You can comment it out if not needed.

---

## Next Steps

1. Complete all steps above
2. Run: `python monitor_email_push.py`
3. Test by sending an email
4. Keep the terminal running or set up as a Windows service

Need help? Check the logs: `logs/monitor_email_push.log`
