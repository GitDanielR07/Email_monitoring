"""
Script to automatically delete emails that are marked as read,
while skipping starred emails.
"""

import os
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from dotenv import load_dotenv

# Run from the project root so .env and config/ resolve.
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ===== Load environment variables =====
load_dotenv()
CREDENTIALS_FILE = os.getenv("GMAIL_CREDENTIALS_FILE", os.path.join("config", "credentials.json"))
TOKEN_FILE = os.getenv("GMAIL_TOKEN_FILE", os.path.join("config", "token.json"))

# ===== Gmail API setup =====
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]


def get_service():
    """Authenticate with Gmail API."""
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


def delete_read_emails(dry_run=True, max_results=50):
    """
    Delete read emails while skipping starred emails.
    
    Args:
        dry_run: If True, only show what would be deleted without actually deleting
        max_results: Maximum number of emails to process
    
    Returns:
        Dictionary with statistics
    """
    service = get_service()
    
    # Query: emails (read or unread, not starred) from 2018-2024
    # '-is:starred' excludes starred emails
    # 'before:2025-01-01 after:2017-12-31' filters for 2018-2024
    query = '-is:starred before:2025-01-01 after:2017-12-31'
    
    print(f"[SEARCH] Searching for emails (read/unread) from 2018-2024...")
    
    total_deleted = 0
    total_skipped = 0
    all_messages = []
    page_token = None
    
    # Paginate through results (Gmail API returns max 500 per request)
    while len(all_messages) < max_results:
        remaining = max_results - len(all_messages)
        batch_size = min(500, remaining)  # Gmail API max is 500
        
        results = service.users().messages().list(
            userId="me",
            q=query,
            maxResults=batch_size,
            pageToken=page_token
        ).execute()
        
        messages = results.get("messages", [])
        if not messages:
            break
        
        all_messages.extend(messages)
        page_token = results.get("nextPageToken")
        
        if not page_token:
            break
    
    if not all_messages:
        print("[OK] No emails found (or all emails are starred).")
        return {"total": 0, "deleted": 0, "skipped": 0}
    
    print(f"[FOUND] {len(all_messages)} emails to delete\n")
    
    deleted_count = 0
    skipped_count = 0
    
    for idx, msg in enumerate(all_messages, 1):
        # Fetch email metadata
        msg_data = service.users().messages().get(
            userId="me",
            id=msg["id"],
            format="metadata",
            metadataHeaders=["From", "Subject", "Date"]
        ).execute()
        
        headers = msg_data["payload"]["headers"]
        sender = next((h["value"] for h in headers if h["name"] == "From"), "Unknown")
        subject = next((h["value"] for h in headers if h["name"] == "Subject"), "(No Subject)")
        date = next((h["value"] for h in headers if h["name"] == "Date"), "Unknown")
        
        # Check if starred (has STARRED label)
        labels = msg_data.get("labelIds", [])
        is_starred = "STARRED" in labels
        
        if is_starred:
            print(f"[STAR] [{idx}/{len(all_messages)}] SKIPPED (starred): {subject[:60]}")
            skipped_count += 1
            continue
        
        # Show email info
        try:
            print(f"[DEL] [{idx}/{len(all_messages)}] {subject[:60]}")
            print(f"   From: {sender[:60]}")
            print(f"   Date: {date}")
        except UnicodeEncodeError:
            # Handle special characters in subject
            print(f"[DEL] [{idx}/{len(all_messages)}] [Special characters in subject]")
            print(f"   From: {sender[:60]}"[:60])
            print(f"   Date: {date}")
        
        if not dry_run:
            # Delete the email by moving to trash
            service.users().messages().trash(userId="me", id=msg["id"]).execute()
            print(f"   [OK] Deleted")
            deleted_count += 1
        else:
            print(f"   [DRY RUN - Not deleted]")
            deleted_count += 1
        
        print()
    
    # Summary
    print("=" * 60)
    print(f"[SUMMARY]")
    print(f"   Total processed: {len(all_messages)}")
    print(f"   {'Would delete' if dry_run else 'Deleted'}: {deleted_count}")
    print(f"   Skipped (starred): {skipped_count}")
    if dry_run:
        print(f"   (DRY RUN MODE - no emails were actually deleted)")
    print("=" * 60)
    
    return {
        "total": len(all_messages),
        "deleted": deleted_count,
        "skipped": skipped_count,
        "dry_run": dry_run
    }


if __name__ == "__main__":
    import sys
    
    # Check for command line arguments
    dry_run = True  # Default to dry run for safety
    max_results = 3100
    
    # Parse all arguments
    for i, arg in enumerate(sys.argv[1:], 1):
        if arg.lower() == "--confirm":
            dry_run = False
            print("[CONFIRMATION] Emails WILL be deleted!")
        elif arg.lower() == "--max" and i < len(sys.argv) - 1:
            try:
                max_results = int(sys.argv[i + 1])
                print(f"[LIMIT] Processing up to {max_results} emails")
            except (ValueError, IndexError):
                print(f"[ERROR] Invalid number: {sys.argv[i + 1] if i < len(sys.argv) - 1 else 'missing'}")
                sys.exit(1)
        elif arg.lower() == "--help":
            print("Usage: python delete_read_emails.py [options]")
            print("\nOptions:")
            print("  (no args)           - DRY RUN: show what would be deleted (500 emails)")
            print("  --max <number>      - Limit to specific number of emails (e.g., --max 10)")
            print("  --confirm           - ACTUALLY DELETE read emails (skip starred)")
            print("  --help              - Show this help message")
            print("\nExamples:")
            print("  python delete_read_emails.py --max 10      (preview 10 emails)")
            print("  python delete_read_emails.py --max 100 --confirm  (delete 100 emails)")
            sys.exit(0)
    
    if dry_run:
        print("[DRYRUN] DRY RUN MODE - No emails will be deleted")
        print("   To actually delete emails, run: python delete_read_emails.py --confirm\n")
    
    delete_read_emails(dry_run=dry_run, max_results=max_results)
