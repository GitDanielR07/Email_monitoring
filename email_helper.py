import os
import sys

# Avoid shadowing the stdlib 'email' package when this file is named email.py
if '' in sys.path:
    sys.path.remove('')
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR in sys.path:
    sys.path.remove(CURRENT_DIR)

import time
import requests
import base64
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from bs4 import BeautifulSoup
import re

# ===== Load environment variables =====
load_dotenv()
WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_EMAIL")
STUDENT_EMAIL = os.getenv("STUDENT_EMAIL")
CREDENTIALS_FILE = os.getenv("GMAIL_CREDENTIALS_FILE", "credentials.json")
TOKEN_FILE = os.getenv("GMAIL_TOKEN_FILE", "token.json")

# ===== Gmail API setup =====
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

def get_service():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as token:
            token.write(creds.to_json())
    return build("gmail", "v1", credentials=creds)

def is_allowed_sender(sender, subject):
    """Check if email is from allowed sources."""
    sender_lower = sender.lower()
    subject_lower = subject.lower()
    
    # Google services
    google_domains = [
        "classroom.google.com",
        "docs.google.com",
        "drive.google.com",
        "calendar.google.com",
        "meet.google.com",
        "@google.com",
        "no-reply@accounts.google.com",
        "googleclassroom-noreply@google.com"
    ]
    
    # SLU specific emails
    slu_emails = [
        "info@slu.edu.ph",
        "support@myvirtuallearning.org"
    ]
    
    # Check Google services
    for domain in google_domains:
        if domain in sender_lower:
            return True
    
    # Check SLU emails
    for email in slu_emails:
        if email in sender_lower:
            return True
    
    # Check if it's a Google Classroom notification in subject
    if "google classroom" in subject_lower or "classroom" in subject_lower:
        return True
    
    # Check for Google Docs/Drive sharing invitations
    if any(keyword in subject_lower for keyword in ["shared", "invited you", "google docs", "google drive"]):
        if any(domain in sender_lower for domain in ["@google.com", "docs.google.com", "drive.google.com"]):
            return True
    
    return False

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
                # Recursively check nested parts
                nested_body = get_email_body(part)
                if nested_body and not body:
                    body = nested_body
    else:
        # Single part message
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
    
    # Split into lines for processing
    lines = body.split('\n')
    cleaned_lines = []
    skip_rest = False
    skip_count = 0
    
    for line in lines:
        line_lower = line.lower().strip()
        
        # Skip if we've hit a stop marker
        if skip_rest:
            continue
        
        # Stop markers - everything after these should be removed
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
        
        # Skip lines to remove
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
        
        # Skip Google Classroom course codes (e.g., CIS-2-9478-IT325)
        if re.match(r'^[A-Z]{2,4}-\d+-\d+-[A-Z0-9]+$', line.strip()):
            continue
        
        if any(marker in line_lower for marker in skip_markers):
            continue
        
        # Skip empty lines at the start
        if not cleaned_lines and not line.strip():
            continue
        
        cleaned_lines.append(line)
    
    # Join and clean up excessive whitespace
    result = '\n'.join(cleaned_lines)
    result = re.sub(r'\n{3,}', '\n\n', result)  # Max 2 consecutive newlines
    return result.strip()

def truncate_text(text, max_length=1024):
    """Truncate text to fit Discord embed field limits."""
    if len(text) <= max_length:
        return text
    return text[:max_length-3] + "..."

def send_email_embed(sender, subject, body, date_str, attachments_count=0):
    """Send email as Discord embed."""
    # Truncate body for Discord limits (already cleaned)
    body_truncated = truncate_text(body, 2000) if body else "*(Empty message)*"
    
    # Extract clean sender name (remove email address from display)
    sender_name = sender
    if '<' in sender and '>' in sender:
        sender_name = sender.split('<')[0].strip().strip('"')
    
    # Format date more cleanly if available
    date_display = None
    parsed = None
    ph_tz = timezone(timedelta(hours=8))  # PH timezone is UTC+8
    
    if date_str:
        try:
            # Try to parse and format date (remove timezone for cleaner look)
            import email.utils
            parsed = email.utils.parsedate_to_datetime(date_str)
            if parsed:
                # For display, convert to PH timezone
                if parsed.tzinfo is None:
                    # If no timezone, assume UTC
                    parsed = parsed.replace(tzinfo=timezone.utc)
                parsed_ph = parsed.astimezone(ph_tz)
                date_display = parsed_ph.strftime("%B %d, %Y at %I:%M %p")
        except Exception as e:
            date_display = date_str.split(' (')[0] if '(' in date_str else date_str
    
    # Use the email's actual timestamp for the embed (not current time)
    if parsed:
        # Keep the parsed datetime as-is with its timezone info for the embed
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
    
    # Add metadata in a single clean field
    metadata_parts = []
    if date_display:
        metadata_parts.append(f"📅 {date_display}")
    if attachments_count > 0:
        metadata_parts.append(f"📎 {attachments_count} attachment{'s' if attachments_count > 1 else ''}")
    
    if metadata_parts:
        embed["fields"].append({
            "name": "​",  # Invisible character for spacing
            "value": " • ".join(metadata_parts),
            "inline": False
        })
    
    payload = {"embeds": [embed]}
    
    try:
        resp = requests.post(WEBHOOK_URL, json=payload)
        return resp.status_code in (200, 204)
    except Exception as e:
        print(f"❌ Failed to send Discord embed: {e}")
        return False

def check_email_fast():
    service = get_service()

    query = 'is:unread'
    results = service.users().messages().list(
        userId="me", labelIds=["INBOX"], q=query, maxResults=10
    ).execute()

    messages = results.get("messages", [])
    if not messages:
        print("📭 No new emails.")
        return

    for msg in messages:
        # Fetch full message with body
        msg_data = service.users().messages().get(
            userId="me",
            id=msg["id"],
            format="full"
        ).execute()

        headers = msg_data["payload"]["headers"]
        sender = next((h["value"] for h in headers if h["name"] == "From"), "Unknown Sender")
        to_email = next((h["value"] for h in headers if h["name"] == "To"), "")
        subject = next((h["value"] for h in headers if h["name"] == "Subject"), "(No Subject)")
        date_str = next((h["value"] for h in headers if h["name"] == "Date"), "")

        # Log email being checked

        # Check if email is from allowed sources
        if is_allowed_sender(sender, subject):
            # Extract email body
            body = get_email_body(msg_data["payload"])
            
            # Count attachments
            attachments_count = 0
            if "parts" in msg_data["payload"]:
                for part in msg_data["payload"]["parts"]:
                    if part.get("filename") and part["filename"] != "":
                        attachments_count += 1
            
            # Send via Discord embed
            send_email_embed(sender, subject, body, date_str, attachments_count)

            # Mark as read
            service.users().messages().modify(
                userId="me",
                id=msg["id"],
                body={"removeLabelIds": ["UNREAD"]}
            ).execute()

def get_seconds_until_next_10min():
    """Calculate seconds until next 10-minute mark (00, 10, 20, 30, 40, 50)."""
    now = datetime.now()
    next_minute = (now.minute // 10 + 1) * 10
    next_hour, next_day, next_month, next_year = now.hour, now.day, now.month, now.year

    if next_minute == 60:
        next_minute = 0
        next_hour += 1
        if next_hour == 24:
            next_hour = 0
            from calendar import monthrange
            if now.day == monthrange(now.year, now.month)[1]:
                next_day, next_month = 1, now.month + 1 if now.month < 12 else 1
                if next_month == 1:
                    next_year += 1
            else:
                next_day += 1

    next_time = datetime(next_year, next_month, next_day, next_hour, next_minute, 0)
    return (next_time - now).total_seconds(), next_time

def run_standalone():
    """Run email monitor in standalone mode with 10-minute intervals."""
    print("📧 Starting Email Monitor")
    print(f"🕓 Current Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📬 Monitoring email: {STUDENT_EMAIL}")
    print(f"🔔 Discord webhook: {'Configured' if WEBHOOK_URL else 'Not configured'}\n")

    while True:
        print(f"⏰ Running email check at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        try:
            check_email_fast()
        except Exception as e:
            print(f"❌ Error checking email: {e}")
        
        wait_sec, next_run = get_seconds_until_next_10min()
        print(f"💤 Waiting {int(wait_sec) + 30}s until next check at {next_run.strftime('%H:%M:%S')}...\n")
        time.sleep(wait_sec + 30)

if __name__ == "__main__":
    run_standalone()
