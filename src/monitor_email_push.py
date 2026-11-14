"""
Gmail Push Notification Monitor
Receives real-time notifications from Gmail via Google Cloud Pub/Sub
and forwards emails to Discord immediately upon arrival.
"""

import os
import sys
import json
import base64
import logging
import signal
import time
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from google.cloud import pubsub_v1
from flask import Flask, request
import threading
import requests
from bs4 import BeautifulSoup
import re

# Run from the project root so .env, config/ and logs/ resolve no matter where
# this was launched from (startup, shortcut, another folder). The built .exe
# lives in the project root; the script lives in src/.
if getattr(sys, "frozen", False):
    os.chdir(os.path.dirname(sys.executable))
else:
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ===== Load environment variables =====
load_dotenv(os.path.join(os.getcwd(), ".env"))
WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_EMAIL")
DISCORD_MENTION_ID = os.getenv("DISCORD_MENTION_ID")
STUDENT_EMAIL = os.getenv("STUDENT_EMAIL")
CREDENTIALS_FILE = os.getenv("GMAIL_CREDENTIALS_FILE", os.path.join("config", "credentials.json"))
TOKEN_FILE = os.getenv("GMAIL_TOKEN_FILE", os.path.join("config", "token.json"))

# Pub/Sub Configuration
GOOGLE_CLOUD_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT")
PUBSUB_TOPIC = os.getenv("PUBSUB_TOPIC", "gmail-notifications")
PUBSUB_SUBSCRIPTION = os.getenv("PUBSUB_SUBSCRIPTION", "gmail-notifications-sub")

# ===== Logging setup =====
log_dir = "logs"
os.makedirs(log_dir, exist_ok=True)
# Emoji in log messages crash the default Windows console/file encoding (cp1252).
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(log_dir, "monitor_email_push.log"), encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ===== Gmail API setup =====
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

# Flask app for webhook
app = Flask(__name__)

# Global Gmail service
gmail_service = None
subscriber = None
subscription_path = None

# The Gmail client (httplib2) is not thread-safe, and Pub/Sub delivers callbacks
# on a thread pool. All Gmail access goes through this lock.
gmail_lock = threading.Lock()

# Gmail history cursor: only messages added after this point are forwarded.
last_history_id = None
# Message IDs already forwarded, to avoid duplicates from overlapping notifications.
processed_ids = set()

WATCH_RENEW_SECONDS = 24 * 60 * 60  # Gmail watches expire after 7 days; renew daily.


def _remove_token_file():
    """Remove token file to force re-authentication."""
    try:
        os.remove(TOKEN_FILE)
    except FileNotFoundError:
        pass


def get_gmail_service():
    """Authenticate and get Gmail service."""
    global gmail_service
    if gmail_service:
        return gmail_service
    
    creds = None
    if os.path.exists(TOKEN_FILE):
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        except Exception:
            _remove_token_file()
            creds = None
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as exc:
                message = str(exc).lower()
                if "invalid_grant" in message or "expired or revoked" in message:
                    _remove_token_file()
                    creds = None
                else:
                    raise
        
        if not creds:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        
        with open(TOKEN_FILE, "w") as token:
            token.write(creds.to_json())
    
    gmail_service = build("gmail", "v1", credentials=creds)
    return gmail_service


def get_email_body(payload):
    """Extract email body from message payload."""
    body = ""
    
    if "parts" in payload:
        for part in payload["parts"]:
            if part["mimeType"] == "text/plain":
                if "data" in part["body"]:
                    body = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="ignore")
                    break
            elif part["mimeType"] == "text/html" and not body:
                if "data" in part["body"]:
                    html = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="ignore")
                    soup = BeautifulSoup(html, "html.parser")
                    body = soup.get_text(separator="\n", strip=True)
            elif "parts" in part:
                nested_body = get_email_body(part)
                if nested_body and not body:
                    body = nested_body
    else:
        if "body" in payload and "data" in payload["body"]:
            data = payload["body"]["data"]
            decoded = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
            if payload["mimeType"] == "text/html":
                soup = BeautifulSoup(decoded, "html.parser")
                body = soup.get_text(separator="\n", strip=True)
            else:
                body = decoded
    
    return clean_email_body(body.strip())


def clean_email_body(body):
    """Remove unnecessary text from email body."""
    if not body:
        return body

    lines = body.split('\n')
    cleaned_lines = []
    skip_rest = False
    
    for line in lines:
        line_lower = line.lower().strip()
        
        if skip_rest:
            continue
        
        stop_markers = [
            "google llc",
            "this email was sent to you because",
            "you can unsubscribe",
            "if you don't want to receive emails like this",
            "disclaimer:",
            "may be confidential and are intended solely",
            "the views expressed in this email"
        ]
        
        if any(marker in line_lower for marker in stop_markers):
            skip_rest = True
            continue
        
        skip_markers = [
            "notification settings",
            "https://accounts.google.com",
            "https://classroom.google.com",
            "see details",
            "change your settings",
            "unsubscribe or change",
            "posted on",
            "new announcement",
            "new assignment"
        ]
        
        if re.match(r'^[A-Z]{2,4}-\d+-\d+-[A-Z0-9]+$', line.strip()):
            continue
        
        if any(marker in line_lower for marker in skip_markers):
            continue
        
        if not cleaned_lines and not line.strip():
            continue
        
        cleaned_lines.append(line)
    
    result = '\n'.join(cleaned_lines)
    result = re.sub(r'\n{3,}', '\n\n', result)
    return result.strip()


def truncate_text(text, max_length=1024):
    """Truncate text to fit Discord embed field limits."""
    if len(text) <= max_length:
        return text
    return text[:max_length-3] + "..."


def send_email_embed(sender, subject, body, date_str, attachments_count=0):
    """Send email as Discord embed."""
    body_truncated = truncate_text(body, 2000) if body else "*(Empty message)*"
    
    sender_name = sender
    if '<' in sender and '>' in sender:
        sender_name = sender.split('<')[0].strip().strip('"')
    
    date_display = None
    parsed = None
    ph_tz = timezone(timedelta(hours=8))
    
    if date_str:
        try:
            import email.utils
            parsed = email.utils.parsedate_to_datetime(date_str)
            if parsed:
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                parsed_ph = parsed.astimezone(ph_tz)
                date_display = parsed_ph.strftime("%B %d, %Y at %I:%M %p")
        except Exception as e:
            date_display = date_str.split(' (')[0] if '(' in date_str else date_str
    
    if parsed:
        embed_timestamp = parsed.isoformat()
    else:
        embed_timestamp = datetime.now(timezone.utc).isoformat()
    
    embed = {
        "title": truncate_text(subject or "(No Subject)", 256),
        "description": body_truncated,
        "color": 0x00E676,
        "timestamp": embed_timestamp,
        "author": {
            "name": truncate_text(sender_name, 256),
            "icon_url": "https://www.gstatic.com/images/branding/product/1x/gmail_2020q4_48dp.png"
        },
        "fields": []
    }
    
    metadata_parts = []
    if date_display:
        metadata_parts.append(f"📅 {date_display}")
    if attachments_count > 0:
        metadata_parts.append(f"📎 {attachments_count} attachment{'s' if attachments_count > 1 else ''}")
    
    if metadata_parts:
        embed["fields"].append({
            "name": "​",
            "value": " • ".join(metadata_parts),
            "inline": False
        })
    
    # Add mention if configured
    content = ""
    if DISCORD_MENTION_ID:
        content = f"<@{DISCORD_MENTION_ID}>"
    
    payload = {"content": content, "embeds": [embed]}
    
    try:
        resp = requests.post(WEBHOOK_URL, json=payload)
        return resp.status_code in (200, 204)
    except Exception as e:
        logger.error(f"Failed to send Discord embed: {e}")
        return False


def process_email_notification(message_id):
    """Process a single email when notification arrives."""
    try:
        service = get_gmail_service()
        
        msg_data = service.users().messages().get(
            userId="me",
            id=message_id,
            format="metadata",
            metadataHeaders=["From", "Subject", "Date"]
        ).execute()
        
        labels = msg_data.get("labelIds", [])
        if "UNREAD" not in labels:
            logger.info(f"Message {message_id}: Already read, skipping")
            return
        
        headers = msg_data["payload"]["headers"]
        sender = next((h["value"] for h in headers if h["name"] == "From"), "Unknown Sender")
        subject = next((h["value"] for h in headers if h["name"] == "Subject"), "(No Subject)")
        date_str = next((h["value"] for h in headers if h["name"] == "Date"), "")
        
        logger.info(f"🚀 NEW EMAIL - From: {sender}")
        logger.info(f"   Subject: {subject}")
        
        # Get full message for body
        full_msg_data = service.users().messages().get(
            userId="me",
            id=message_id,
            format="full"
        ).execute()
        
        body = get_email_body(full_msg_data["payload"])
        
        attachments_count = 0
        if "parts" in full_msg_data["payload"]:
            for part in full_msg_data["payload"]["parts"]:
                if part.get("filename") and part["filename"] != "":
                    attachments_count += 1
        
        # Send to Discord; leave the email unread if delivery fails.
        if send_email_embed(sender, subject, body, date_str, attachments_count):
            logger.info(f"   ✅ Sent to Discord")
        else:
            logger.error(f"   ❌ Failed to send to Discord (left unread)")
            return

        # Mark as read
        service.users().messages().modify(
            userId="me",
            id=message_id,
            body={"removeLabelIds": ["UNREAD"]}
        ).execute()
        
    except Exception as e:
        logger.error(f"Error processing email {message_id}: {e}")


def fetch_new_inbox_message_ids(notification_history_id):
    """Return IDs of messages added to INBOX since the last processed history ID.

    Must be called with gmail_lock held.
    """
    global last_history_id
    if last_history_id is None:
        last_history_id = notification_history_id
        return []

    service = get_gmail_service()
    ids = []
    page_token = None
    try:
        while True:
            resp = service.users().history().list(
                userId="me",
                startHistoryId=last_history_id,
                historyTypes=["messageAdded"],
                labelId="INBOX",
                pageToken=page_token,
            ).execute()
            for record in resp.get("history", []):
                for added in record.get("messagesAdded", []):
                    msg_id = added["message"]["id"]
                    if msg_id not in ids:
                        ids.append(msg_id)
            page_token = resp.get("nextPageToken")
            if not page_token:
                last_history_id = resp.get("historyId", notification_history_id)
                break
    except Exception as e:
        # A 404 means the cursor is too old; resync to the latest point.
        logger.warning(f"History lookup failed ({e}); resyncing cursor")
        last_history_id = notification_history_id
    return ids


def handle_pubsub_message(message):
    """Handle incoming Pub/Sub message from Gmail."""
    try:
        # Decode the message
        data = json.loads(message.data.decode('utf-8'))
        
        # Gmail watch notifications contain emailAddress and historyId
        if "emailAddress" in data and "historyId" in data:
            email = data["emailAddress"]
            history_id = data["historyId"]
            
            logger.info(f"📧 Gmail notification received (HistoryId: {history_id})")

            with gmail_lock:
                for msg_id in fetch_new_inbox_message_ids(history_id):
                    if msg_id in processed_ids:
                        continue
                    processed_ids.add(msg_id)
                    process_email_notification(msg_id)

            message.ack()
        else:
            logger.warning(f"Unexpected message format: {data}")
            message.ack()
            
    except Exception as e:
        logger.error(f"Error handling Pub/Sub message: {e}")
        message.ack()


def subscribe_to_notifications():
    """Subscribe to Gmail push notifications via Pub/Sub."""
    try:
        global subscriber, subscription_path
        
        if not GOOGLE_CLOUD_PROJECT:
            logger.error("❌ GOOGLE_CLOUD_PROJECT not set in .env file")
            return False
        
        subscriber = pubsub_v1.SubscriberClient()
        subscription_path = subscriber.subscription_path(GOOGLE_CLOUD_PROJECT, PUBSUB_SUBSCRIPTION)

        logger.info(f"📬 Subscribing to: {subscription_path}")

        # One notification at a time; the handler serializes Gmail access anyway.
        flow_control = pubsub_v1.types.FlowControl(max_messages=1)
        streaming_pull_future = subscriber.subscribe(
            subscription_path, callback=handle_pubsub_message, flow_control=flow_control
        )

        # Keep the subscriber alive
        try:
            streaming_pull_future.result()
        except KeyboardInterrupt:
            streaming_pull_future.cancel()
            logger.info("Subscriber stopped")

        return True
        
    except Exception as e:
        logger.error(f"Failed to subscribe to notifications: {e}")
        return False


def setup_gmail_watch():
    """Set up Gmail watch on INBOX to send notifications to Pub/Sub."""
    try:
        if not GOOGLE_CLOUD_PROJECT:
            logger.error("❌ GOOGLE_CLOUD_PROJECT not set in .env file")
            return False
        
        global last_history_id

        # Create the watch request
        watch_request = {
            "topicName": f"projects/{GOOGLE_CLOUD_PROJECT}/topics/{PUBSUB_TOPIC}"
        }
        
        logger.info(f"🔔 Setting up Gmail watch on: {watch_request['topicName']}")
        
        with gmail_lock:
            result = get_gmail_service().users().watch(
                userId="me",
                body=watch_request
            ).execute()
            # Seed the cursor on first start so the existing inbox is not re-sent.
            if last_history_id is None:
                last_history_id = result.get("historyId")

        logger.info(f"✅ Gmail watch setup successful!")
        logger.info(f"   Expiration: {result.get('expiration', 'Unknown')}")
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to set up Gmail watch: {e}")
        return False


@app.route('/')
def index():
    """Health check endpoint."""
    return {
        "status": "running",
        "service": "Gmail Push Notification Monitor",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@app.route('/health')
def health():
    """Health check endpoint."""
    return {"status": "healthy"}


def main():
    """Main entry point."""
    print("=" * 70)
    print("Gmail Push Notification Monitor")
    print("=" * 70)
    print(f"📧 Email: {STUDENT_EMAIL}")
    print(f"🔔 Discord Webhook: {'Configured' if WEBHOOK_URL else 'Not configured'}")
    print(f"☁️  Google Cloud Project: {GOOGLE_CLOUD_PROJECT}")
    print(f"📬 Pub/Sub Topic: {PUBSUB_TOPIC}")
    print("=" * 70)
    
    # Setup Gmail watch
    if not setup_gmail_watch():
        logger.error("Failed to setup Gmail watch!")
        return 1
    
    logger.info("✅ Gmail watch is active. Listening for incoming emails...")
    
    # Start Pub/Sub subscription in a separate thread; restart it if it dies.
    def run_subscriber():
        while True:
            subscribe_to_notifications()
            logger.warning("Subscriber stopped unexpectedly; restarting in 30s")
            time.sleep(30)

    def renew_watch():
        while True:
            time.sleep(WATCH_RENEW_SECONDS)
            logger.info("🔁 Renewing Gmail watch")
            setup_gmail_watch()

    threading.Thread(target=run_subscriber, daemon=True).start()
    threading.Thread(target=renew_watch, daemon=True).start()
    
    # Start Flask app
    logger.info("🌐 Starting health check server on http://localhost:5000")
    app.run(host='localhost', port=5000, debug=False)


if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code if exit_code else 0)
    except KeyboardInterrupt:
        logger.info("\n⏹️  Shutting down...")
        sys.exit(0)
