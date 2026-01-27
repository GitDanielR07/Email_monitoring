# 📧 Email Monitor to Discord

Automated Gmail monitor that forwards allowed emails (e.g., Classroom/Drive/Docs notices) to Discord with clean embeds.

## ✨ Features

- 🎯 **Smart Filtering** - Only monitors emails from Google Classroom/Docs/Drive/Calendar/Meet and a small allowed list you can edit

- 💎 **Clean Discord Embeds** - Beautiful, human-readable format with:
  - Gmail icon and sender name
  - Clean date formatting
  - Automatic content cleanup (removes footers, disclaimers, metadata)
  - Attachment indicators
  - Bright emerald green accent color

- ⚡ **Auto-Processing** - Marks emails as read after forwarding
- 🔄 **Continuous Monitoring** - Checks every 5 minutes (configurable)
- 📱 **Full Content** - Reads and forwards complete email body

## 📋 Prerequisites

- Python 3.8+
- Gmail account
- Discord webhook URL
- Google Cloud project with Gmail API enabled

## 🚀 Setup Instructions

### 1. Clone the Repository

```bash
git clone https://github.com/sora598/Email_monitoring.git
cd Email_monitoring
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

Or install manually:
```bash
pip install google-auth-oauthlib google-auth-httplib2 google-api-python-client python-dotenv requests beautifulsoup4
```

### 3. Set Up Gmail API

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or select existing)
3. Enable the **Gmail API**:
   - Go to "APIs & Services" > "Library"
   - Search for "Gmail API"
   - Click "Enable"
4. Create OAuth 2.0 credentials:
   - Go to "APIs & Services" > "Credentials"
   - Click "Create Credentials" > "OAuth client ID"
   - Choose "Desktop app"
   - Download the credentials
5. Save the downloaded file as `config/credentials.json` (create the `config` folder if missing)

### 4. Create Discord Webhook

1. Open your Discord server
2. Go to Server Settings > Integrations > Webhooks
3. Click "New Webhook"
4. Configure webhook (name, channel, icon)
5. Copy the webhook URL

### 5. Configure Environment Variables

Create a `.env` file in the project directory:

```env
# Discord Webhook
DISCORD_WEBHOOK_EMAIL=https://discord.com/api/webhooks/xxx/yyy

# Gmail address to monitor
STUDENT_EMAIL=your_email@example.com

# Gmail API credentials (optional - defaults shown)
GMAIL_CREDENTIALS_FILE=config/credentials.json
GMAIL_TOKEN_FILE=config/token.json
```

**Example:**
```env
DISCORD_WEBHOOK_EMAIL=https://discord.com/api/webhooks/123/abc
STUDENT_EMAIL=your_email@example.com
GMAIL_CREDENTIALS_FILE=config/credentials.json
GMAIL_TOKEN_FILE=config/token.json
```

### 6. First Run - Authorize Gmail Access

```bash
python monitor_email.py
```

On first run:
1. A browser window will open
2. Sign in to your Gmail account
3. Grant the requested permissions
4. The `config/token.json` file will be created automatically

## 📂 File Structure

```
email_checker/
├── monitor_email.py           # Main email monitor (run this!)
├── email_standalone.py        # Alternative CLI runner
├── email_helper.py            # Email processing helpers
├── delete_read_emails.py      # Utility to clean read mail
├── utils.py                   # Utility functions
├── build.py                   # Build helper (PyInstaller)
├── monitor_email.spec         # PyInstaller spec file
├── monitor_email.exe          # Built executable (Windows)
├── config/
│   ├── credentials.json       # Gmail API credentials (not committed)
│   └── token.json            # OAuth token (auto-generated, not committed)
├── logs/                      # Runtime logs (ignored)
├── assets/                    # Icons and resources
├── build/                     # Build artifacts (ignored)
├── requirements.txt
├── .env
└── README.md
```

## 🎮 Usage

### Run the Monitor (Python)

```bash
python monitor_email.py
```

### Run the Monitor (Executable)

For Windows, you can run the pre-built executable:
```bash
.\monitor_email.exe
```

The monitor will:
- ✅ Check for new emails every 5 minutes
- ✅ Display which emails are processed or skipped
- ✅ Send allowed emails to Discord as embeds
- ✅ Mark forwarded emails as read
- ✅ Show timestamps in your local timezone

### Stop the Monitor

Press `Ctrl + C` to stop the monitor gracefully. You'll see:
```
⚠️  Shutdown signal received...
✋ Stopping email monitor gracefully...
✅ Email monitor stopped. Goodbye!
```

## 🔧 Customization

### Add More Allowed Senders

Edit `monitor_email.py` or `email_helper.py`, find the `is_allowed_sender()` function:

```python
# Add to google_domains list for Google services
google_domains = [
    "classroom.google.com",
    "docs.google.com",
    # Add more...
]

# Add to slu_emails list for specific addresses
slu_emails = [
    "info@slu.edu.ph",
    "support@myvirtuallearning.org",
    # Add more...
]
```

### Change Check Interval

In `monitor_email.py`, adjust the helper that computes the next run (default 5 minutes) or the sleep in `run_standalone()`.

### Customize Embed Appearance

Edit `send_email_embed()` function to change:
- **Color**: Change `0x00E676` (emerald green) to any hex color
- **Icon**: Change `icon_url` to different image
- **Fields**: Add/remove metadata fields

## 📝 Helper Scripts

- `email_helper.py` - Email processing helpers
- `delete_read_emails.py` - Delete read emails (use with caution)
- `build.py` - Rebuilds `monitor_email.exe` via PyInstaller

## 🔒 Security Notes

- **Never commit** `credentials.json`, `token.json`, or `.env` files
- Keep your Discord webhook URL private
- The `.gitignore` file is configured to exclude sensitive files
- Use environment variables for all sensitive data

## 🐛 Troubleshooting

### "No module named 'requests'" error
```bash
pip install -r requirements.txt
```

### Gmail authentication fails
1. Delete `token.json`
2. Run the script again to re-authenticate
3. Make sure Gmail API is enabled in Google Cloud Console

### Emails not being forwarded
- Check that the sender is in the allowed list
- Verify the Discord webhook URL is correct
- Check console output for "SKIPPED" messages

### Rate limit errors
- Google has API quotas - if you hit them, wait and try again
- Default check interval (10 minutes) should be safe

## 📄 License

MIT License - Feel free to use and modify!

## 🤝 Contributing

Contributions welcome! Feel free to:
- Report bugs
- Suggest features
- Submit pull requests

## 👤 Author

Created for personal email-to-Discord monitoring.

## 📞 Support

For issues or questions, please open an issue on GitHub.
