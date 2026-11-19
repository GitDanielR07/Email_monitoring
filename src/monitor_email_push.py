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
from logging.handlers import RotatingFileHandler
import signal
import time
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.cloud import pubsub_v1
from flask import Flask, request
import threading
import requests
from bs4 import BeautifulSoup, NavigableString
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
        # At 10 MB the log is renamed to .log.1 (replacing the previous .log.1)
        # and a fresh file starts, so logs never take more than ~20 MB.
        RotatingFileHandler(
            os.path.join(log_dir, "monitor_email_push.log"),
            maxBytes=10 * 1024 * 1024, backupCount=1, encoding="utf-8",
        ),
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
# Persisted to STATE_FILE so emails that arrive while the app is offline are
# caught up on the next start.
last_history_id = None
# When the cursor was last synced (ms since epoch); used for a date-based
# fallback if Gmail no longer has history that old.
last_sync_ms = None
# Recently forwarded message IDs (bounded), to avoid duplicates across restarts.
processed_ids = []
# Message IDs whose Discord delivery failed; retried on the next sync.
pending_ids = []

STATE_FILE = os.path.join("config", "monitor_state.json")
MAX_REMEMBERED_IDS = 500
WATCH_RENEW_SECONDS = 24 * 60 * 60  # Gmail watches expire after 7 days; renew daily.
CATCH_UP_DELAY_SECONDS = 1.0  # spacing between backlog posts (Discord rate limits)

COLOR_LIVE = 0x00E676    # emerald: arrived while running
COLOR_MISSED = 0xFFB300  # amber: arrived while the monitor was offline


def load_state():
    """Load the saved cursor from disk (no-op if there is none yet)."""
    global last_history_id, last_sync_ms, processed_ids, pending_ids
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            state = json.load(f)
        last_history_id = state.get("history_id")
        last_sync_ms = state.get("last_sync_ms")
        processed_ids = list(state.get("processed_ids", []))[-MAX_REMEMBERED_IDS:]
        pending_ids = list(state.get("pending_ids", []))
        logger.info(f"💾 Loaded saved state (HistoryId: {last_history_id})")
    except FileNotFoundError:
        logger.info("💾 No saved state yet; starting fresh (existing inbox will not be re-sent)")
    except Exception as e:
        logger.warning(f"Could not read {STATE_FILE} ({e}); starting fresh")


def save_state():
    """Write the cursor to disk atomically."""
    state = {
        "history_id": last_history_id,
        "last_sync_ms": last_sync_ms,
        "processed_ids": processed_ids[-MAX_REMEMBERED_IDS:],
        "pending_ids": pending_ids,
    }
    tmp = STATE_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
        os.replace(tmp, STATE_FILE)
    except Exception as e:
        logger.error(f"Failed to save state: {e}")


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


# Invisible characters marketing emails use to pad the inbox preview text.
# Discord renders them as huge blocks of empty space.
_INVISIBLE_CHARS = re.compile(
    "[\u00ad\u034f\u061c\u115f\u1160\u17b4\u17b5\u180e"
    "\u200b-\u200f\u202a-\u202e\u2060-\u206f\u3164\ufeff\uffa0]"
)
_ODD_SPACES = re.compile("[\u00a0\u1680\u2000-\u200a\u202f\u205f\u3000\t]")


# Long tracking links (optionally wrapped in parentheses / angle brackets) add noise.
_LONG_URL = re.compile(r"[(<\[]?\s*https?://\S{50,}\s*[)>\]]?")


def _normalize_text(text):
    """Strip invisible padding and tracking links, normalize spaces, collapse blank lines."""
    text = _INVISIBLE_CHARS.sub("", text)
    text = _ODD_SPACES.sub(" ", text)
    text = _LONG_URL.sub("", text)
    lines = []
    for line in text.splitlines():
        line = re.sub(r" {2,}", " ", line).strip()
        if re.fullmatch(r"[()\[\]<>|*•·\-–—_=.]*", line):
            line = ""  # leftover brackets/separators from removed links
        lines.append(line)
    text = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _decode_part(part):
    data = part.get("body", {}).get("data")
    if not data:
        return ""
    return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")


def _collect_parts(payload, found):
    """Walk the MIME tree and keep the first text/plain and text/html bodies."""
    mime = payload.get("mimeType", "")
    if mime == "text/plain" and "plain" not in found and not payload.get("filename"):
        found["plain"] = _decode_part(payload)
    elif mime == "text/html" and "html" not in found and not payload.get("filename"):
        found["html"] = _decode_part(payload)
    for part in payload.get("parts", []):
        _collect_parts(part, found)


MAX_LINK_URL = 1000  # absurdly long URLs are dropped, the link text is kept

_BLOCK_TAGS = ["p", "div", "tr", "table", "li", "ul", "ol", "h1", "h2", "h3",
               "h4", "h5", "h6", "blockquote", "section", "article", "header",
               "footer", "center", "hr"]


_PRESERVE_WS = re.compile(r"white-space\s*:\s*(pre|pre-wrap|pre-line|break-spaces)", re.I)


def _preserves_newlines(node):
    for parent in node.parents:
        if parent.name in ("pre", "textarea") or _PRESERVE_WS.search(parent.get("style") or ""):
            return True
    return False


_BOLD_TAGS = {"b", "strong", "h1", "h2", "h3", "h4", "h5", "h6"}
_BOLD_STYLE = re.compile(r"font-weight\s*:\s*(bold|bolder|[6-9]00)\b", re.I)
BOLD_OPEN, BOLD_CLOSE = "\x01", "\x02"  # placeholders, turned into ** later
MAX_BOLD_SHARE = 0.6  # if more of the email than this is bold, bold means nothing


def _is_bold(tag):
    return tag.name in _BOLD_TAGS or bool(_BOLD_STYLE.search(tag.get("style") or ""))


def _mark_bold(soup):
    """Wrap bold elements' text in placeholder markers (outermost bold only)."""
    total = len(soup.get_text(strip=True)) or 1
    chosen, chosen_ids = [], set()
    for tag in soup.find_all(True):
        if not _is_bold(tag) or tag.find(_BLOCK_TAGS):
            continue  # not bold, or a whole bold-styled layout block
        if any(id(parent) in chosen_ids for parent in tag.parents):
            continue  # already inside a bold element
        text_len = len(tag.get_text(strip=True))
        if text_len:
            chosen.append((tag, text_len))
            chosen_ids.add(id(tag))
    if sum(n for _, n in chosen) > MAX_BOLD_SHARE * total:
        return  # (nearly) everything is bold: keep it plain
    for tag, _ in chosen:
        tag.insert(0, BOLD_OPEN)
        tag.append(BOLD_CLOSE)


def _apply_bold(text):
    """Turn bold markers into Discord **bold**, per line, with spaces outside the stars."""
    def to_markdown(match):
        lines = []
        for line in match.group(1).split("\n"):
            core = line.strip()
            if core:
                lead = line[:len(line) - len(line.lstrip())]
                trail = line[len(line.rstrip()):]
                lines.append(f"{lead}**{core}**{trail}")
            else:
                lines.append(line)
        return "\n".join(lines)
    text = re.sub(r"\x01([^\x01\x02]*)\x02", to_markdown, text)
    text = text.replace(BOLD_OPEN, "").replace(BOLD_CLOSE, "")
    # Tidy spaces the markers left behind at line edges / between words.
    return "\n".join(re.sub(r" {2,}", " ", line).strip() for line in text.split("\n"))


LINE_BREAK, PARA_BREAK = "\x06", "\x05"
GROUP_OPEN, GROUP_CLOSE = "\x03", "\x04"
_PARAGRAPH_TAGS = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "hr", "blockquote",
                   "ul", "ol", "table"}
MAX_GROUP_SHARE = 0.6   # a "box" covering more of the email than this is just the page wrapper
MIN_GROUP_CHARS = 20
_BG_STYLE = re.compile(r"background(?:-color)?\s*:\s*([^;]+)", re.I)
_NOT_A_BOX = {"#fff", "#ffffff", "white", "transparent", "none", "inherit", "initial", ""}


def _box_color(tag):
    """Background colour that makes this element a visual box/card, or None.

    Borders alone don't count: emails use them for page frames and dividers.
    """
    color = (tag.get("bgcolor") or "").strip().lower()
    match = _BG_STYLE.search(tag.get("style") or "")
    if match:
        color = match.group(1).strip().lower()
    if color.startswith("url(") or "!important" in color:
        color = color.split("!important")[0].strip()
    if not color or color in _NOT_A_BOX or color.startswith("url("):
        return None
    return color


def _mark_groups(soup):
    """Mark visually boxed sections (cards, callouts) so they render as quote blocks.

    Markers carry a colour key so that adjacent boxes with the same background
    (a card built from several tables) merge into one group later.
    """
    total = len(soup.get_text(strip=True)) or 1
    chosen_ids, color_keys = set(), {}
    for tag in soup.find_all(["div", "td", "th", "table", "section"]):
        color = _box_color(tag)
        if not color or not tag.find(["div", "p", "table", "tr", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6"]):
            continue  # no background, or a single-element box such as a button
        if any(id(parent) in chosen_ids for parent in tag.parents):
            continue  # Discord can't nest quotes; keep the outermost box
        text_len = len(tag.get_text(strip=True))
        if MIN_GROUP_CHARS <= text_len <= MAX_GROUP_SHARE * total:
            chosen_ids.add(id(tag))
            key = color_keys.setdefault(color, len(color_keys))
            tag.insert(0, f"{GROUP_OPEN}{key}{GROUP_OPEN}")
            tag.append(GROUP_CLOSE)
            tag.insert_before(PARA_BREAK)
            tag.insert_after(PARA_BREAK)


def _apply_groups(text):
    """Render marked groups as Discord quote blocks, kept tight (no blank lines inside)."""
    # Merge neighbouring groups of the same colour (nothing but whitespace between).
    merge = re.compile(r"(\x03(\d+)\x03[^\x03\x04]*)\x04\s*\x03\2\x03")
    while True:
        merged = merge.sub(lambda m: m.group(1) + "\n", text)
        if merged == text:
            break
        text = merged

    def to_quote(match):
        lines = [line for line in match.group(1).split("\n") if line.strip()]
        if not lines:
            return ""
        if len(lines) == 1:  # a one-liner box reads fine as a normal paragraph
            return "\n\n" + lines[0] + "\n\n"
        return "\n\n" + "\n".join("> " + line for line in lines) + "\n\n"
    text = re.sub(r"\x03\d+\x03(.*?)\x04", to_quote, text, flags=re.S)
    return re.sub(r"[\x03\x04]", "", text)


def _html_to_text(html):
    """Readable text from HTML: paragraphs on their own lines, inline text kept together."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["style", "script", "head", "title", "meta"]):
        tag.decompose()
    # Hidden elements (e.g. the preheader) are not part of the visible email.
    for tag in soup.find_all(style=re.compile(r"display\s*:\s*none|visibility\s*:\s*hidden|max-height\s*:\s*0", re.I)):
        tag.decompose()
    # Source-code line breaks inside a paragraph are just spaces, unless the
    # element preserves them (<pre>, white-space: pre/pre-wrap/break-spaces).
    for node in soup.find_all(string=True):
        if type(node) is not NavigableString:  # comments, doctype, CDATA, etc.
            node.extract()
        elif _preserves_newlines(node):
            node.replace_with(re.sub(r"[ \t\r\f\v]+", " ", str(node)))
        else:
            node.replace_with(re.sub(r"\s+", " ", str(node)))
    _mark_groups(soup)
    _mark_bold(soup)
    # Links/buttons become placeholders, turned into Discord [text](url) links later.
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        text = re.sub(r"\s+", " ", a.get_text(" ")).strip()
        if (text and href.lower().startswith(("https://", "http://"))
                and len(href) <= MAX_LINK_URL and text.rstrip("/") != href.rstrip("/")):
            links.append((text, href))
            a.replace_with(f"\x00{len(links) - 1}\x00")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    for tag in soup.find_all(_BLOCK_TAGS):
        brk = PARA_BREAK if tag.name in _PARAGRAPH_TAGS else LINE_BREAK
        tag.insert_before(brk)
        tag.insert_after(brk)
    text = soup.get_text()
    # Collapse each run of breaks: a paragraph break (or a real <br>/text newline)
    # gives a blank line; layout-only breaks give a single line break.
    text = re.sub(
        r"[\s\x05\x06]*[\x05\x06][\s\x05\x06]*",
        lambda m: "\n\n" if (PARA_BREAK in m.group() or "\n" in m.group()) else "\n",
        text,
    )
    return text, links


def _restore_links(text, links):
    """Swap link placeholders for Discord masked links."""
    def to_markdown(match):
        label, url = links[int(match.group(1))]
        label = _apply_bold(label).strip().replace("[", "(").replace("]", ")")
        return f"[{label}]({url})"
    return re.sub(r"\x00(\d+)\x00", to_markdown, text)


def _px(value):
    match = re.match(r"\s*(\d+)", str(value or ""))
    return int(match.group(1)) if match else None


def extract_main_image(html):
    """Pick the email's main (largest) image URL for the Discord embed, if any."""
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")
    best, best_score = None, 0
    for img in soup.find_all("img"):
        src = (img.get("src") or "").strip()
        if not src.lower().startswith(("https://", "http://")):
            continue  # cid: inline images can't be shown by Discord
        low = src.lower()
        if any(k in low for k in ("track", "pixel", "beacon", "spacer", "/open", "1x1", "blank.gif")):
            continue
        style = img.get("style") or ""
        width = _px(img.get("width")) or _px((re.search(r"(?<![-\w])width\s*:\s*(\d+)px", style) or [None, None])[1])
        height = _px(img.get("height")) or _px((re.search(r"(?<![-\w])height\s*:\s*(\d+)px", style) or [None, None])[1])
        if (width and width < 200) or (height and height < 80):
            continue  # logos, icons, badges, tracking pixels
        score = width or 300
        if score > best_score:
            best, best_score = src, score
    return best


def get_email_content(payload):
    """Return (clean body text, main image URL or None) for a Gmail message payload."""
    found = {}
    _collect_parts(payload, found)
    plain = _normalize_text(found.get("plain", ""))
    html = found.get("html", "")
    html_text = ""
    if html:
        raw_text, links = _html_to_text(html)
        html_text = _restore_links(_apply_groups(_apply_bold(_normalize_text(raw_text))), links)
        html_text = re.sub(r"\n{3,}", "\n\n", html_text).strip()
    # The HTML part is what Gmail shows; plain-text parts are often auto-generated
    # junk (CSS, tracking links, one word per line). Fall back to plain if needed.
    body = html_text or plain
    return clean_email_body(body), extract_main_image(html)


def get_email_body(payload):
    """Extract the cleaned email body text from a message payload."""
    return get_email_content(payload)[0]


def clean_email_body(body):
    """Remove unnecessary text from email body."""
    if not body:
        return body

    lines = body.split('\n')
    cleaned_lines = []
    skip_rest = False
    
    for line in lines:
        # Judge lines by what the reader sees, not by the URLs inside links.
        line_lower = _visible_text(line).lower().strip()

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
        
        # Short "Privacy | Terms | Unsubscribe"-style lines start the footer.
        is_footer_links = "unsubscribe" in line_lower and len(line_lower) < 120
        if is_footer_links or any(marker in line_lower for marker in stop_markers):
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


_MD_LINK = re.compile(r"\[([^\]]*)\]\((https?://[^)\s]+)\)")
DISCORD_DESCRIPTION_LIMIT = 4096


def _visible_text(text):
    """Text as Discord displays it: masked links show only their label."""
    return re.sub(r"^> ", "", _MD_LINK.sub(r"\1", text).replace("**", ""), flags=re.M)


def truncate_body(text, max_visible=1500):
    """Cap the body by *visible* length, cutting only between lines so links stay whole.

    Link URLs don't count toward max_visible, but the raw text must still fit
    Discord's 4096-character description limit.
    """
    raw_limit = DISCORD_DESCRIPTION_LIMIT - 10
    if len(_visible_text(text)) <= max_visible and len(text) <= raw_limit:
        return text
    kept, visible, raw = [], 0, 0
    for line in text.split("\n"):
        line_visible = len(_visible_text(line)) + 1
        if visible + line_visible > max_visible or raw + len(line) + 1 > raw_limit:
            if not kept:  # first line alone is too long: fall back to a plain cut
                kept.append(_visible_text(line)[:max_visible - 3])
            break
        kept.append(line)
        visible += line_visible
        raw += len(line) + 1
    return "\n".join(kept).rstrip() + " …"


def truncate_text(text, max_length=1024):
    """Truncate text to fit Discord embed field limits."""
    if len(text) <= max_length:
        return text
    return text[:max_length-3] + "..."


# ===== Sensitive-email filter =====
# Emails matching these are never forwarded in full: if the Discord channel or
# account is compromised, codes / reset links must not be sitting there.
_SENSITIVE_PATTERNS = [
    r"verification code", r"verify (?:your |my )?(?:email|e-mail|account|identity|sign[- ]?in|login|device)",
    r"(?:confirm|activate) your (?:email|e-mail|account|identity)",
    r"one[- ]time (?:pass(?:word|code)|code|pin|link|login)", r"\botp\b", r"\bpass ?code\b",
    r"security code",
    r"(?:login|log-in|sign[- ]?in|access|authentication|auth|confirmation|recovery|backup|"
    r"activation|2fa|mfa|device|single[- ]use) code",
    r"(?:reset|change|forgot|recover)\w* (?:your )?password", r"password (?:reset|change|recovery)",
    r"two[- ]factor", r"2-step", r"\b2fa\b", r"\bmfa\b", r"multi[- ]factor",
    r"magic (?:sign[- ]?in |login )?link", r"(?:sign[- ]?in|login) link",
    r"account recovery", r"recovery (?:email|phone)",
    r"(?:new|suspicious|unusual|unrecognized) (?:sign[- ]?in|login|log-in|device)",
    r"security alert", r"your (?:code|pin) is",
    # A 4-8 digit number right next to "code"/"PIN"/"OTP" (e.g. "Your code: 482913")
    r"\b(?:code|pin|otp)\b[^0-9\n]{0,30}\b\d{4,8}\b",
    r"\b\d{4,8}\b[^0-9\n]{0,20}\b(?:is your|is the)\b[^\n]{0,20}\b(?:code|pin|otp)\b",
]
_extra = [k.strip() for k in os.getenv("SENSITIVE_KEYWORDS", "").split(",") if k.strip()]
_SENSITIVE_RE = re.compile(
    "|".join(_SENSITIVE_PATTERNS + [re.escape(k) for k in _extra]), re.I
)
COLOR_REDACTED = 0x9E9E9E  # grey


def sensitive_reason(subject, body):
    """Return the phrase that marks this email as sensitive, or None."""
    match = _SENSITIVE_RE.search(f"{subject}\n{_visible_text(body or '')}")
    return match.group(0) if match else None


def send_email_embed(sender, subject, body, date_str, attachments_count=0,
                     received_ms=None, missed=False, image_url=None, redacted=False):
    """Send email as Discord embed.

    received_ms: Gmail's internalDate (when the email reached the mailbox).
    missed: True if it arrived while the monitor was offline.
    redacted: True for security emails; only sender and time are sent.
    """
    if redacted:
        subject = "🔒 Security email (content hidden)"
        body = ("This looks like a **verification code, password reset or sign-in alert**, "
                "so its contents were not sent to Discord.\n\nOpen Gmail to read it. "
                "It has been left **unread**.")
        image_url = None
        attachments_count = 0
    body_truncated = truncate_body(body, 1500) if body else "*(Empty message)*"

    sender_name = sender
    if '<' in sender and '>' in sender:
        sender_name = sender.split('<')[0].strip().strip('"')

    # Prefer Gmail's receive time; fall back to the sender's Date header.
    received = None
    if received_ms:
        received = datetime.fromtimestamp(int(received_ms) / 1000, tz=timezone.utc)
    elif date_str:
        try:
            import email.utils
            received = email.utils.parsedate_to_datetime(date_str)
            if received and received.tzinfo is None:
                received = received.replace(tzinfo=timezone.utc)
        except Exception:
            received = None

    embed_timestamp = (received or datetime.now(timezone.utc)).isoformat()

    embed = {
        "title": truncate_text(subject or "(No Subject)", 256),
        "description": body_truncated,
        "color": COLOR_REDACTED if redacted else (COLOR_MISSED if missed else COLOR_LIVE),
        "timestamp": embed_timestamp,
        "author": {
            "name": truncate_text(sender_name, 256),
            "icon_url": "https://www.gstatic.com/images/branding/product/1x/gmail_2020q4_48dp.png"
        },
        "fields": []
    }
    if image_url:
        embed["image"] = {"url": image_url}
    
    metadata_parts = []
    if missed:
        metadata_parts.append("🕒 **Missed while monitor was offline**")
    if received:
        # Discord renders <t:...> in each viewer's own timezone, plus "x hours ago".
        epoch = int(received.timestamp())
        metadata_parts.append(f"📥 Received <t:{epoch}:F> (<t:{epoch}:R>)")
    if attachments_count > 0:
        metadata_parts.append(f"📎 {attachments_count} attachment{'s' if attachments_count > 1 else ''}")
    
    if metadata_parts:
        embed["fields"].append({
            "name": "​",
            "value": " • ".join(metadata_parts),
            "inline": False
        })
    
    # Add mention if configured
    content = f"<@{DISCORD_MENTION_ID}>" if DISCORD_MENTION_ID else ""
    if missed:
        content = (content + " 📬 Missed while offline").strip()

    payload = {"content": content, "embeds": [embed]}

    for attempt in range(3):
        try:
            resp = requests.post(WEBHOOK_URL, json=payload, timeout=15)
            if resp.status_code in (200, 204):
                return True
            if resp.status_code == 429:  # rate limited: wait as told, then retry
                retry_after = float(resp.json().get("retry_after", 2))
                logger.warning(f"Discord rate limit; retrying in {retry_after:.1f}s")
                time.sleep(retry_after + 0.5)
                continue
            logger.error(f"Discord returned {resp.status_code}: {resp.text[:200]}")
            return False
        except Exception as e:
            logger.error(f"Failed to send Discord embed: {e}")
            time.sleep(2)
    return False


def process_email(message_id, missed=False):
    """Forward one email to Discord. Must be called with gmail_lock held.

    Returns "sent", "skipped" (nothing to do), or "failed" (retry later).
    """
    try:
        service = get_gmail_service()

        try:
            msg_data = service.users().messages().get(
                userId="me",
                id=message_id,
                format="metadata",
                metadataHeaders=["From", "Subject", "Date"]
            ).execute()
        except HttpError as e:
            if e.resp.status == 404:
                logger.info(f"Message {message_id}: no longer exists, skipping")
                return "skipped"
            raise

        labels = msg_data.get("labelIds", [])
        if "TRASH" in labels or "SPAM" in labels:
            logger.info(f"Message {message_id}: in Trash/Spam, skipping")
            return "skipped"
        # Live emails that are already read were handled elsewhere (or by you).
        # Missed emails are always forwarded, even if you read them meanwhile.
        if not missed and "UNREAD" not in labels:
            logger.info(f"Message {message_id}: Already read, skipping")
            return "skipped"

        headers = msg_data["payload"]["headers"]
        sender = next((h["value"] for h in headers if h["name"] == "From"), "Unknown Sender")
        subject = next((h["value"] for h in headers if h["name"] == "Subject"), "(No Subject)")
        date_str = next((h["value"] for h in headers if h["name"] == "Date"), "")
        received_ms = msg_data.get("internalDate")

        # Get full message for body
        full_msg_data = service.users().messages().get(
            userId="me",
            id=message_id,
            format="full"
        ).execute()

        body, image_url = get_email_content(full_msg_data["payload"])
        reason = sensitive_reason(subject, body)

        tag = "📬 MISSED EMAIL" if missed else "🚀 NEW EMAIL"
        logger.info(f"{tag} - From: {sender}")
        if reason:
            # Don't write the subject either: it often contains the code itself.
            logger.info(f"   🔒 Sensitive (matched '{reason[:40]}'); content hidden, left unread")
        else:
            logger.info(f"   Subject: {subject}")

        attachments_count = 0
        if "parts" in full_msg_data["payload"]:
            for part in full_msg_data["payload"]["parts"]:
                if part.get("filename") and part["filename"] != "":
                    attachments_count += 1

        # Send to Discord; leave the email unread if delivery fails.
        if not send_email_embed(sender, subject, body, date_str, attachments_count,
                                received_ms=received_ms, missed=missed,
                                image_url=image_url, redacted=bool(reason)):
            logger.error(f"   ❌ Failed to send to Discord (will retry)")
            return "failed"
        logger.info(f"   ✅ Sent to Discord")

        # Security emails stay unread so you notice them in Gmail.
        if "UNREAD" in labels and not reason:
            service.users().messages().modify(
                userId="me",
                id=message_id,
                body={"removeLabelIds": ["UNREAD"]}
            ).execute()
        return "sent"

    except Exception as e:
        logger.error(f"Error processing email {message_id}: {e}")
        return "failed"


def _inbox_ids_from_history(start_history_id):
    """IDs added to INBOX since start_history_id (oldest first), plus the new cursor."""
    service = get_gmail_service()
    ids, page_token = [], None
    while True:
        resp = service.users().history().list(
            userId="me",
            startHistoryId=start_history_id,
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
            return ids, resp.get("historyId")


def _inbox_ids_since_time(since_ms):
    """Fallback when history is too old: search INBOX by date (oldest first)."""
    service = get_gmail_service()
    # 60s overlap so nothing at the boundary is missed; duplicates are filtered later.
    after = max(0, int(since_ms / 1000) - 60)
    ids, page_token = [], None
    while True:
        resp = service.users().messages().list(
            userId="me", q=f"in:inbox after:{after}", pageToken=page_token
        ).execute()
        ids.extend(m["id"] for m in resp.get("messages", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    ids.reverse()  # messages.list returns newest first
    current = service.users().getProfile(userId="me").execute().get("historyId")
    return ids, current


def sync_inbox(missed=False, notification_history_id=None):
    """Forward every INBOX email added since the saved cursor, then save the cursor.

    Used both for live notifications and for catching up after downtime
    (missed=True). Must be called with gmail_lock held.
    """
    global last_history_id, last_sync_ms, processed_ids, pending_ids

    if last_history_id is None:
        # First run ever: start from "now" rather than dumping the whole inbox.
        last_history_id = notification_history_id
        last_sync_ms = int(time.time() * 1000)
        save_state()
        return

    try:
        new_ids, new_history_id = _inbox_ids_from_history(last_history_id)
    except HttpError as e:
        if e.resp.status != 404 or not last_sync_ms:
            logger.error(f"History lookup failed: {e}")
            return
        logger.warning("Saved history is too old for Gmail; searching inbox by date instead")
        new_ids, new_history_id = _inbox_ids_since_time(last_sync_ms)

    queue = [i for i in pending_ids + new_ids if i not in processed_ids]
    queue = list(dict.fromkeys(queue))  # dedupe, keep order
    if missed and queue:
        logger.info(f"📬 Catching up on {len(queue)} email(s) received while offline")

    still_pending = []
    for idx, msg_id in enumerate(queue):
        result = process_email(msg_id, missed=missed or msg_id in pending_ids)
        if result == "failed":
            still_pending.append(msg_id)
        else:
            processed_ids.append(msg_id)
        if missed and idx < len(queue) - 1:
            time.sleep(CATCH_UP_DELAY_SECONDS)

    processed_ids = processed_ids[-MAX_REMEMBERED_IDS:]
    pending_ids = still_pending
    if new_history_id:
        last_history_id = new_history_id
    last_sync_ms = int(time.time() * 1000)
    save_state()


def handle_pubsub_message(message):
    """Handle incoming Pub/Sub message from Gmail."""
    try:
        data = json.loads(message.data.decode('utf-8'))

        # Gmail watch notifications contain emailAddress and historyId
        if "emailAddress" in data and "historyId" in data:
            history_id = data["historyId"]
            logger.info(f"📧 Gmail notification received (HistoryId: {history_id})")

            with gmail_lock:
                sync_inbox(missed=False, notification_history_id=history_id)
        else:
            logger.warning(f"Unexpected message format: {data}")

    except Exception as e:
        logger.error(f"Error handling Pub/Sub message: {e}")
    finally:
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
        
        global last_history_id, last_sync_ms

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
            # First run ever (no saved state): start from now so the existing
            # inbox is not re-sent.
            if last_history_id is None:
                last_history_id = result.get("historyId")
                last_sync_ms = int(time.time() * 1000)
                save_state()

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
    
    load_state()

    # Setup Gmail watch
    if not setup_gmail_watch():
        logger.error("Failed to setup Gmail watch!")
        return 1

    # Forward anything that arrived while the monitor was offline.
    with gmail_lock:
        sync_inbox(missed=True)
    
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
