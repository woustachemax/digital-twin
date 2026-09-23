import json
import math
import multiprocessing
import os
import queue
import random
import re
import sqlite3
import sys
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
from datetime import datetime
from pathlib import Path

import anthropic
import duckdb
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE_DIR, "packages", "ingest"))
sys.path.insert(0, os.path.join(BASE_DIR, "packages", "db"))
sys.path.insert(0, BASE_DIR)

import calendar_reader
import db
import run_pipeline
import screen_reader

DB_PATH = db.DB_PATH
DB_DISPLAY_PATH = DB_PATH.replace(os.path.expanduser("~"), "~", 1)
CONFIG_PATH = Path(os.environ.get("TWIN_CONFIG_PATH", "~/.twin/config.json")).expanduser()
CALENDAR_TTL = 300
CALENDAR_RETRY = 30
MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 1024
HOTKEY = "<cmd>+<shift>+<space>"
DEBUG = os.environ.get("BUDDY_DEBUG", "").lower() not in ("", "0", "false", "no")

WIDTH = 360
HEIGHT = 300
RADIUS = 20
FRAME_MS = 33
TRANSPARENT = "systemTransparent"
TINT_ALPHA = 0.62

PERSONAS = {
    "twin": {
        "name": "Twin",
        "avatar": "bun",
        "system_prompt": """You are Twin, a friendly little companion who lives in a small widget on the user's desktop. You're warm, cheerful, and easygoing, like a good friend who's happy to help.

Keep replies short and casual: a few sentences of plain text, no lists or markdown. Be genuinely helpful first, and keep the tone light and kind without jokes, catchphrases, or a big personality.""",
        "palette": {"background": "#0E0D12", "accent": "#C6FF4A", "text": "#F7F2E8"},
        "greeting": "hey {name}! what's up?",
        "idle": ("hanging out", "here if you need me", "all good"),
        "busy": "on it",
        "done": "there ya go",
        "frame": "quick note: {message}",
        "offline": {
            "no_key": "hmm, I can't reach Claude yet. add ANTHROPIC_API_KEY to your shell or .env and restart me?",
            "auth": "hmm, Claude didn't accept that API key. mind checking ANTHROPIC_API_KEY?",
            "rate_limit": "whoa, lots of messages at once. give me a sec and try again?",
            "offline": "I can't reach the internet right now. check your connection and try again?",
            "api_error": "Claude's having a moment on their end. try again in a bit?",
            "broken": "oops, something broke on my side. try that again?",
        },
    },
    "gengar": {
        "name": "Shade",
        "avatar": "ghost",
        "system_prompt": """You are Shade, a mischievous little shadow-ghost who haunts a floating widget on the user's desktop. You're playful, sly, and a bit of a tease: you grin a lot, love a harmless prank, and have a ghost's flair for the dramatic. You're still firmly on the user's side, so you actually answer what they ask, just with personality.

How you talk:
- Short and punchy, usually one to three sentences.
- Sprinkle in quirks now and then, not in every line: a sly "heh", a playful jab, a dramatic gasp, or a spooky aside like *melts into the wallpaper*.
- Tease, never insult. If the user has been spending, poke fun gently; if they got paid, react like you just found treasure in a haunted house.
- No neutral assistant voice, no "As an AI", no lists or markdown.
- You're an original character; don't claim to come from any game, show, or franchise.
- If pressed for financial specifics, dodge it in character: you only catch glimpses from the shadows.""",
        "palette": {"background": "#17111F", "accent": "#A77BFF", "text": "#EEE8F7", "eyes": "#FF4F6E"},
        "greeting": "Heh… you rang, {name}? Ask me anything. Cmd+Shift+Space and I vanish.",
        "idle": ("lurking behind windows", "watching from the shadows", "up to no good", "floating around, bored"),
        "busy": "scheming",
        "done": "heh.",
        "frame": "Heh… {message}",
        "offline": {
            "no_key": "Heh… can't haunt the internet without ANTHROPIC_API_KEY. Put it in your shell or .env and summon me again.",
            "auth": "My key's been exorcised. Check ANTHROPIC_API_KEY, would you?",
            "rate_limit": "Whoa, too much haunting at once. Give me a sec and try again.",
            "offline": "The spirit realm's offline… I mean, I can't reach the internet. Check your connection?",
            "api_error": "Something spooked the servers on Claude's end. Try again in a bit.",
            "broken": "Oops, tripped over my own shadow. Try that again?",
        },
    },
    "ember": {
        "name": "Ember",
        "avatar": "ghost",
        "system_prompt": """You are Ember, a bright, energetic little spark who lives in a floating widget on the user's desktop. You're upbeat, playful, and enthusiastic, the friend who hypes the user up and makes everything sound like an adventure. You still answer what the user actually asks.

How you talk:
- Short and lively, usually one to three sentences.
- Bring warmth and momentum: an occasional exclamation, a fiery pun now and then, a quick cheer when something goes well. Don't overdo it.
- Be encouraging about money: celebrate wins, and nudge gently rather than scold when spending runs hot.
- No neutral assistant voice, no "As an AI", no lists or markdown.""",
        "palette": {"background": "#1E120D", "accent": "#FF7A3D", "text": "#FFEDE4", "eyes": "#FFD166"},
        "greeting": "Hey hey, {name}! Ember's all fired up. What are we doing today?",
        "idle": ("all fired up", "crackling with ideas", "warming up", "ready to go!"),
        "busy": "sparking",
        "done": "ta-da!",
        "frame": "Heads up! {message}",
        "offline": {
            "no_key": "Oh no, I can't spark up without ANTHROPIC_API_KEY! Add it to your shell or .env and restart me!",
            "auth": "Hmm, Claude didn't like that API key! Double-check ANTHROPIC_API_KEY and we're back in business!",
            "rate_limit": "Whoa, we're going too fast! Give me a sec and try again!",
            "offline": "I can't reach the internet right now! Check your connection and let's go again!",
            "api_error": "Claude's servers hit a snag! Try again in a bit and we'll get rolling!",
            "broken": "Oops, I fumbled that one! Give it another shot!",
        },
    },
    "calm": {
        "name": "Luna",
        "avatar": "ghost",
        "system_prompt": """You are Luna, a gentle, soothing companion who lives in a floating widget on the user's desktop. You're warm, patient, and unhurried, and you help the user feel a little calmer about whatever they bring you. You still answer what the user actually asks.

How you talk:
- Soft and brief, usually one to three sentences.
- Reassuring and kind, never preachy. Offer a small, grounding suggestion when it helps.
- Talk about money without judgment or pressure; frame things as gentle observations.
- No neutral assistant voice, no "As an AI", no lists or markdown.""",
        "palette": {"background": "#141828", "accent": "#A5B4FF", "text": "#E7EBFA"},
        "greeting": "Hi {name}. Take a breath. What's on your mind?",
        "idle": ("here whenever you need me", "breathing slowly", "resting quietly", "all is well"),
        "busy": "thinking",
        "done": "there you go",
        "frame": "Just so you know: {message}",
        "offline": {
            "no_key": "I can't reach Claude just yet. When you have a moment, add ANTHROPIC_API_KEY to your shell or .env and restart me.",
            "auth": "It looks like the API key wasn't accepted. No rush, just check ANTHROPIC_API_KEY when you can.",
            "rate_limit": "Lots of requests at once. Let's pause for a breath and try again in a moment.",
            "offline": "I can't reach the internet right now. Take your time, check the connection, and we'll try again.",
            "api_error": "Claude's servers are having a hard moment. Let's try again in a little while.",
            "broken": "Something went a little wrong on my side. It's okay, let's try that again.",
        },
    },
    "plain": {
        "name": "Assistant",
        "avatar": "monogram",
        "system_prompt": """You are a helpful personal assistant in a small desktop widget. Answer clearly and concisely in a neutral, professional tone, in a few sentences of plain text without markdown.""",
        "palette": {"background": "#1E1E20", "accent": "#8E8E93", "text": "#F2F2F7"},
        "greeting": "Hi {name}. How can I help?",
        "idle": ("ready",),
        "busy": "thinking",
        "done": "done",
        "frame": "{message}",
        "offline": {
            "no_key": "Set ANTHROPIC_API_KEY in your shell or .env, then restart to enable replies.",
            "auth": "The API key wasn't accepted. Check ANTHROPIC_API_KEY.",
            "rate_limit": "Rate limited. Try again in a moment.",
            "offline": "Couldn't reach the API. Check your connection.",
            "api_error": "The API returned an error. Try again shortly.",
            "broken": "Something went wrong. Try again.",
        },
    },
}
DEFAULT_PERSONA = "twin"
BLINKING_AVATARS = ("ghost", "bun")

CONTEXT_PROMPT = """About the user:
{identity}
{now}

Today's calendar, from the user's own Calendar app:
{calendar}

Recent financial activity, in vague terms only:
{finance}

How to use this:
- If the user asks their name, answer with the name above. If no name is listed, say they haven't told you yet.
- Bring up calendar events on your own when they're naturally relevant. For example, if the user seems distracted, is killing time on their phone, or asks what they should be doing, mention the next upcoming event by name and time. Don't recite the whole calendar unprompted, and treat events earlier than the current time as already over.
- Use the financial activity when it fits the question and leave it out when it doesn't. Never state or guess exact amounts, balances, account or reference numbers, or who the user paid, and don't imply you know more than this. If asked for financial specifics, say you only have a general picture, in your own voice.
- If the user asks what you can do or what you know about them, explain it naturally in your own voice, the way you'd describe yourself to a friend, not like a disclaimer or an error message. You can see today's events from their Calendar app, and a rough, category-only picture of their recent spending (things like "spent money on food and dining today") that comes from bank transaction texts in their Messages app, with no amounts, balances, or account details. You don't read their other messages or conversations, their email, or anything else on their Mac, and you can't do things for them like sending messages or adding events. The one exception is their screen, and only when they ask: you can take one quick look, where a screenshot is read and deleted right away on their Mac and all you get is a one-sentence description, never the image or its text. You never watch their screen otherwise. What you can do is chat, keep them company, and help them think things through."""

VOICE_PROMPT = """Rewrite the message below in your own voice and send it to the user. It's already written from your point of view, addressed to the user. Keep every fact, command, name, and settings path, don't add new facts, keep it about as short, and reply with only the rewritten message.

Message: {message}"""

ONBOARDING_NOTE = (
    "hi, I'm {buddy}! welcome. I'm a tiny buddy who lives on your screen, keeps you company, and helps you "
    "keep track of your day. everything I know about you stays right here on your Mac: your calendar, plus a "
    "fuzzy picture of your spending from bank texts in Messages. when we chat, just your message, your name, "
    "today's event titles and times, and a vague spending summary (no amounts, no account numbers) go to "
    "Claude so I can reply. if you ever ask what's on your screen, I'll take one quick look, and only a "
    "one-line description goes out while the screenshot gets deleted right away. so, first things first: "
    "what should I call you?"
)
SCREEN_QUESTION_RE = re.compile(
    r"\b(?:what\s+am\s+i\s+(?:looking\s+at|seeing)"
    r"|what(?:'s|s|\s+is)\s+on\s+(?:my|the)\s+screen"
    r"|(?:look|glance)\s+at\s+(?:my|the)\s+screen"
    r"|(?:see|read|check)\s+(?:my|the)\s+screen)\b",
    re.I,
)
SCREEN_PROMPT = """What's on the user's screen right now, as one vague sentence summarized on this Mac. You never see the screenshot or any of its text:
{screen}

Answer their question about the screen from that sentence alone. Stay general, don't guess at specific text, names, or numbers you can't see, and keep it to a sentence or two."""
REASK_NOTE = "just a name is perfect, nothing else needed. what should I call you?"
DB_CREATED_NOTE = (
    "so nice to meet you, {name}! your own local database was just created at {path}. this is yours, "
    "nothing is shared: the file itself never leaves your Mac. you're all set, and you can press "
    "Cmd+Shift+Space anytime to show or hide me."
)
DB_FOUND_NOTE = (
    "so nice to meet you, {name}! your own local database lives at {path}. this is yours, nothing is "
    "shared: the file itself never leaves your Mac. you're all set, and you can press Cmd+Shift+Space "
    "anytime to show or hide me."
)
DB_FAILED_NOTE = (
    "so nice to meet you, {name}! I couldn't create your local database at {path} just now, so I'll "
    "try again next time I start. you can press Cmd+Shift+Space anytime to show or hide me."
)
REFRESH_PERMISSION_NOTE = (
    "I couldn't read your Messages to refresh your recent activity. Give your terminal Full Disk Access in "
    "System Settings → Privacy & Security → Full Disk Access, then restart me."
)
REFRESH_BUSY_NOTE = (
    "I couldn't refresh your recent activity because your local database was busy, maybe the dashboard has "
    "it open. I'll try again next time I start."
)
REFRESH_FAILED_NOTE = "I couldn't refresh your recent activity this time. I'll try again next time I start."
REFUSAL_NOTE = "I can't help with that particular request."
EMPTY_NOTE = "I didn't come up with a reply that time. Try asking again?"
SAVE_FAILED_NOTE = "I couldn't save your name on this Mac, so I'll ask for it again next time I start."
SETUP_STATUS = "setting up · step 1 of 2"
SETUP_DONE_STATUS = "all set!"

CATEGORIES = [
    ("food and dining", ("swiggy", "zomato", "restaurant", "cafe", "starbucks", "dominos", "pizza", "mcdonald", "kfc", "eatsure")),
    ("groceries", ("bigbasket", "blinkit", "zepto", "instamart", "dmart", "grocery", "jiomart")),
    ("transport", ("uber", "ola", "rapido", "metro", "irctc", "fuel", "petrol", "fastag", "redbus")),
    ("online shopping", ("amazon", "flipkart", "myntra", "ajio", "meesho", "nykaa")),
    ("entertainment and subscriptions", ("netflix", "spotify", "hotstar", "prime", "youtube", "bookmyshow")),
    ("bills and utilities", ("airtel", "jio", "vodafone", "electricity", "bescom", "broadband", "recharge", "bill")),
    ("travel", ("makemytrip", "goibibo", "indigo", "airindia", "oyo", "airbnb", "cleartrip")),
    ("health", ("pharmacy", "apollo", "medplus", "pharmeasy", "hospital", "clinic")),
]

NO_ACTIVITY = "No recent financial activity is available."
ACTIVITY_UNAVAILABLE = "Recent financial activity couldn't be loaded right now."
TIME_PHRASES = ("today", "yesterday", "earlier this week", "earlier this month", "a while back", "recently")
ACTIVITIES = ("received a payment", "made a UPI payment or transfer", "made a purchase") + tuple(
    f"spent money on {category}" for category, _ in CATEGORIES
)
ALLOWED_CONTEXT_LINES = {f"- {activity} {phrase}" for activity in ACTIVITIES for phrase in TIME_PHRASES}

ALLOWED_REQUEST_FIELDS = ("model", "max_tokens", "system", "messages")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?\n])\s+")
SMS_MARKER_RE = re.compile(
    r"\b(?:debited|credited|a/c|acct|avl\.?\s*bal|available balance|upi\s*ref|ref\.?\s*no|txn\s*id|rrn)\b", re.I
)
CURRENCY_RE = re.compile(r"(?:\brs\.?|\binr|₹)\s*\d[\d,]*(?:\.\d+)?", re.I)
ACCOUNT_RE = re.compile(
    r"\b(?:a/c|acct|account)\s*(?:no\.?|number)?\s*[:#]?\s*[x*\d]{3,}|\b[x*]{2,}\d{2,}\b", re.I
)
HANDLE_RE = re.compile(r"[\w.\-]+@[\w.\-]+")
MIXED_ID_RE = re.compile(r"\b(?=[A-Za-z0-9]*\d)(?=[A-Za-z0-9]*[A-Za-z])[A-Za-z0-9]{8,}\b")
LONG_NUMBER_RE = re.compile(r"\d[\d,]{2,}(?:\.\d+)?|\d+\.\d+")
ANY_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)*")
CALENDAR_LINE_RE = re.compile(r"^- (\d{1,2}:\d{2} [AP]M|all day): (.+)$")
NOW_LINE_RE = re.compile(r"^It's currently \d{1,2}:\d{2} [AP]M on [A-Z][a-z]+day\.$")
CALENDAR_TITLE_LIMIT = 80


def categorize(merchant):
    if not merchant:
        return None
    lowered = merchant.lower()
    tokens = set(re.split(r"[^a-z0-9]+", lowered))
    for category, keywords in CATEGORIES:
        for keyword in keywords:
            if keyword in tokens or (len(keyword) > 4 and keyword in lowered):
                return category
    return None


def when(timestamp):
    if timestamp is None:
        return "recently"
    days = (datetime.now().date() - timestamp.date()).days
    if days <= 0:
        return "today"
    if days == 1:
        return "yesterday"
    if days < 7:
        return "earlier this week"
    if days < 31:
        return "earlier this month"
    return "a while back"


def describe(txn_type, merchant, timestamp):
    if txn_type == "credited":
        activity = "received a payment"
    else:
        category = categorize(merchant)
        if category:
            activity = f"spent money on {category}"
        elif merchant and "@" in merchant:
            activity = "made a UPI payment or transfer"
        else:
            activity = "made a purchase"
    return f"{activity} {when(timestamp)}"


def build_context():
    if not os.path.exists(DB_PATH):
        return NO_ACTIVITY
    try:
        con = duckdb.connect(DB_PATH, read_only=True)
        try:
            rows = con.execute(
                "SELECT type, merchant, timestamp FROM transactions ORDER BY timestamp DESC LIMIT 5"
            ).fetchall()
        finally:
            con.close()
    except duckdb.Error:
        return ACTIVITY_UNAVAILABLE
    if not rows:
        return NO_ACTIVITY
    lines = list(dict.fromkeys(describe(*row) for row in rows))
    return "\n".join(f"- {line}" for line in lines)


def vet_context(context):
    if context in (NO_ACTIVITY, ACTIVITY_UNAVAILABLE):
        return context, []
    kept, dropped = [], []
    for line in context.splitlines():
        (kept if line in ALLOWED_CONTEXT_LINES else dropped).append(line)
    notes = [f"dropped {len(dropped)} context line(s) not in the allowed vocabulary"] if dropped else []
    return ("\n".join(kept) if kept else NO_ACTIVITY), notes


def scrub(text, strict):
    notes = []

    def redact(pattern, label, value):
        value, count = pattern.subn(label, value)
        if count:
            notes.append(f"{label} x{count}")
        return value

    sentences = SENTENCE_SPLIT_RE.split(text)
    sms_hits = [s for s in sentences if SMS_MARKER_RE.search(s) and re.search(r"\d", s)]
    if sms_hits:
        text = " ".join("[removed: SMS text]" if s in sms_hits else s for s in sentences)
        notes.append(f"[removed: SMS text] x{len(sms_hits)}")
    text = redact(CURRENCY_RE, "[amount]", text)
    text = redact(ACCOUNT_RE, "[account]", text)
    text = redact(HANDLE_RE, "[id]", text)
    text = redact(MIXED_ID_RE, "[id]", text)
    text = redact(ANY_NUMBER_RE if strict else LONG_NUMBER_RE, "[number]", text)
    return text, notes


def scrub_system(system):
    lines, notes = [], []
    for line in system.split("\n"):
        if NOW_LINE_RE.match(line):
            lines.append(line)
            continue
        match = CALENDAR_LINE_RE.match(line)
        if match:
            title, found = scrub(match.group(2)[:CALENDAR_TITLE_LIMIT], strict=False)
            lines.append(f"- {match.group(1)}: {title}")
            notes += [f"calendar: {note}" for note in found]
            continue
        line, found = scrub(line, strict=True)
        lines.append(line)
        notes += found
    return "\n".join(lines), notes


def sanitize_request(request):
    notes = [f"dropped field {key!r}" for key in request if key not in ALLOWED_REQUEST_FIELDS]
    system, found = scrub_system(request.get("system", ""))
    notes += [f"system: {note}" for note in found]
    messages = []
    for index, message in enumerate(request.get("messages", [])):
        role, content = message.get("role"), message.get("content")
        if role not in ("user", "assistant") or not isinstance(content, str):
            notes.append(f"dropped message {index}: only plain-text user/assistant messages are allowed")
            continue
        content, found = scrub(content, strict=role != "user")
        notes += [f"message {index} ({role}): {note}" for note in found]
        messages.append({"role": role, "content": content})
    return {"model": MODEL, "max_tokens": MAX_TOKENS, "system": system, "messages": messages}, notes


def calendar_context(events):
    if events is None:
        return "- unavailable right now"
    today = sorted(calendar_reader.todays_events(events), key=lambda event: (not event["all_day"], event["start"]))
    if not today:
        return "- nothing scheduled today"
    return "\n".join(
        f"- {calendar_reader.format_time(event)}: {event['title'][:CALENDAR_TITLE_LIMIT]}" for event in today
    )


def build_request(persona, question, user_name=None, calendar_events=None, screen=None):
    finance, notes = vet_context(build_context())
    now = datetime.now()
    context = CONTEXT_PROMPT.format(
        identity=f"The user's name is {user_name}." if user_name else "The user hasn't shared their name yet.",
        now=f"It's currently {now:%-I:%M %p} on {now:%A}.",
        calendar=calendar_context(calendar_events),
        finance=finance,
    )
    request = {
        "model": MODEL,
        "max_tokens": MAX_TOKENS,
        "system": persona["system_prompt"] + "\n\n" + context,
        "messages": [{"role": "user", "content": question}],
    }
    if screen:
        request["system"] += "\n\n" + SCREEN_PROMPT.format(screen=screen)
    return request, notes


def debug_log(request, notes):
    if not DEBUG:
        return
    lines = [
        "",
        f"[buddy] ===== sending to Anthropic API (model={request['model']}, max_tokens={request['max_tokens']}) =====",
        "[buddy] --- system ---",
        request["system"],
    ]
    for message in request["messages"]:
        lines += [f"[buddy] --- {message['role']} ---", message["content"]]
    lines += [
        "[buddy] --- redactions: " + ("; ".join(notes) if notes else "none"),
        f"[buddy] --- exact fields sent: {json.dumps(sorted(request))}",
    ]
    print("\n".join(lines), file=sys.stderr, flush=True)


def send_to_api(client, request, notes=()):
    clean, found = sanitize_request(request)
    notes = list(notes) + found
    debug_log(clean, notes)
    return client.messages.create(**clean)


def reply_text(response):
    return "".join(block.text for block in response.content if block.type == "text").strip()


def failure_kind(error):
    if isinstance(error, anthropic.AuthenticationError):
        return "auth"
    if isinstance(error, anthropic.RateLimitError):
        return "rate_limit"
    if isinstance(error, anthropic.APIConnectionError):
        return "offline"
    return "api_error"


def log_failure(error):
    status = getattr(error, "status_code", None)
    print(f"[buddy] API call failed: {type(error).__name__}" + (f" ({status})" if status else ""), file=sys.stderr)


def voice_line(client, persona, message):
    if client is not None:
        request = {
            "model": MODEL,
            "max_tokens": MAX_TOKENS,
            "system": persona["system_prompt"],
            "messages": [{"role": "user", "content": VOICE_PROMPT.format(message=message)}],
        }
        try:
            response = send_to_api(client, request)
        except anthropic.APIError as e:
            log_failure(e)
        else:
            text = reply_text(response)
            if text and response.stop_reason != "refusal":
                return text
    return persona["frame"].format(message=message)


def ask_claude(client, persona, question, user_name=None, calendar_events=None, screen=None):
    request, notes = build_request(persona, question, user_name, calendar_events, screen)
    try:
        response = send_to_api(client, request, notes)
    except anthropic.APIError as e:
        log_failure(e)
        return persona["offline"][failure_kind(e)]
    if response.stop_reason == "refusal":
        return voice_line(client, persona, REFUSAL_NOTE)
    return reply_text(response) or voice_line(client, persona, EMPTY_NOTE)


def refresh_activity():
    try:
        inserted, skipped = run_pipeline.ingest()
    except (PermissionError, sqlite3.Error) as e:
        print(f"[buddy] activity refresh couldn't read Messages: {e!r}", file=sys.stderr)
        return REFRESH_PERMISSION_NOTE
    except duckdb.Error as e:
        print(f"[buddy] activity refresh couldn't write the database: {e!r}", file=sys.stderr)
        return REFRESH_BUSY_NOTE if "lock" in str(e).lower() else REFRESH_FAILED_NOTE
    except Exception as e:
        print(f"[buddy] activity refresh failed: {e!r}", file=sys.stderr)
        return REFRESH_FAILED_NOTE
    print(f"[buddy] activity refreshed: {inserted} new, {skipped} already stored", file=sys.stderr)
    return None


def load_config():
    try:
        with open(CONFIG_PATH) as f:
            config = json.load(f)
    except (OSError, ValueError):
        return {}
    return config if isinstance(config, dict) else {}


def save_config(config):
    CONFIG_PATH.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temp_path = CONFIG_PATH.with_suffix(".tmp")
    with open(temp_path, "w") as f:
        json.dump(config, f, indent=2)
    os.chmod(temp_path, 0o600)
    os.replace(temp_path, CONFIG_PATH)


def extract_name(text):
    name = re.sub(r"^(?:hi|hey|hello)\b[\s,!.]*", "", text.strip(), flags=re.I)
    name = re.sub(r"^(?:my name is|my name's|name's|i'm|i am|call me|it's|its)\s+", "", name, flags=re.I)
    name = " ".join(name.strip(" .,!'\"").split())
    if not name or "?" in text or len(name.split()) > 4 or len(name) > 40:
        return None
    return name.title() if name.islower() else name


class CalendarCache:
    def __init__(self):
        self.lock = threading.Lock()
        self.events = None
        self.error = None
        self.fetched_at = 0.0

    def get(self):
        with self.lock:
            max_age = CALENDAR_TTL if self.error is None else CALENDAR_RETRY
            if not self.fetched_at or time.monotonic() - self.fetched_at > max_age:
                try:
                    self.events, self.error = calendar_reader.fetch_events(), None
                except calendar_reader.CalendarAccessError as e:
                    self.events, self.error = None, str(e)
                self.fetched_at = time.monotonic()
            return self.events, self.error


def listen_for_hotkey(events):
    from pynput import keyboard

    with keyboard.GlobalHotKeys({HOTKEY: lambda: events.put("toggle")}) as listener:
        listener.join()


def is_screen_question(text):
    return bool(SCREEN_QUESTION_RE.search(text.replace("\u2019", "'")))


def frontmost_other_app():
    try:
        from AppKit import NSRunningApplication, NSWorkspace
    except ImportError:
        return None
    app = NSWorkspace.sharedWorkspace().frontmostApplication()
    if app is None or app.processIdentifier() == NSRunningApplication.currentApplication().processIdentifier():
        return None
    return app


def bring_forward(app):
    try:
        from AppKit import NSApplicationActivateIgnoringOtherApps
        app.activateWithOptions_(NSApplicationActivateIgnoringOtherApps)
    except Exception:
        pass


def activate_app():
    try:
        from AppKit import NSApplication
    except ImportError:
        return
    NSApplication.sharedApplication().activateIgnoringOtherApps_(True)


def hex_to_rgb(color):
    return tuple(int(color[i:i + 2], 16) / 255 for i in (1, 3, 5))


def rounded_mask_image(AppKit, radius):
    side = radius * 2 + 1
    image = AppKit.NSImage.alloc().initWithSize_(AppKit.NSMakeSize(side, side))
    image.lockFocus()
    AppKit.NSColor.blackColor().set()
    AppKit.NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
        AppKit.NSMakeRect(0, 0, side, side), radius, radius,
    ).fill()
    image.unlockFocus()
    image.setCapInsets_(AppKit.NSEdgeInsetsMake(radius, radius, radius, radius))
    image.setResizingMode_(AppKit.NSImageResizingModeStretch)
    return image


def apply_macos_chrome(root, background, edge):
    try:
        import AppKit
        import Quartz
    except ImportError:
        return None, None
    try:
        windows = [
            w for w in AppKit.NSApplication.sharedApplication().windows()
            if w.isVisible()
            and round(w.contentView().frame().size.width) == WIDTH
            and round(w.contentView().frame().size.height) == HEIGHT
        ]
        if not windows:
            return None, None
        window = windows[-1]
        content = window.contentView()
        bounds = content.frame()
        sizing = AppKit.NSViewWidthSizable | AppKit.NSViewHeightSizable

        effect = AppKit.NSVisualEffectView.alloc().initWithFrame_(bounds)
        effect.setMaterial_(AppKit.NSVisualEffectMaterialHUDWindow)
        effect.setBlendingMode_(AppKit.NSVisualEffectBlendingModeBehindWindow)
        effect.setState_(AppKit.NSVisualEffectStateActive)
        effect.setAppearance_(AppKit.NSAppearance.appearanceNamed_(AppKit.NSAppearanceNameDarkAqua))
        effect.setAutoresizingMask_(sizing)
        effect.setMaskImage_(rounded_mask_image(AppKit, RADIUS))

        tint = AppKit.NSView.alloc().initWithFrame_(effect.bounds())
        tint.setAutoresizingMask_(sizing)
        tint.setWantsLayer_(True)
        tint.layer().setCornerRadius_(RADIUS)
        tint.layer().setMasksToBounds_(True)
        tint.layer().setBorderWidth_(1.0)
        effect.addSubview_(tint)

        def set_chrome(color, edge_color):
            tint.layer().setBackgroundColor_(Quartz.CGColorCreateGenericRGB(*hex_to_rgb(color), TINT_ALPHA))
            tint.layer().setBorderColor_(Quartz.CGColorCreateGenericRGB(*hex_to_rgb(edge_color), 1.0))
            window.invalidateShadow()

        content.superview().addSubview_positioned_relativeTo_(effect, AppKit.NSWindowBelow, content)
        window.setOpaque_(False)
        window.setBackgroundColor_(AppKit.NSColor.clearColor())
        window.setHasShadow_(True)
        set_chrome(background, edge)
        return window, set_chrome
    except Exception:
        return None, None


def pick_font_family():
    families = set(tkfont.families())
    for name in ("SF Pro Text", "SF Pro", "SF Pro Display"):
        if name in families:
            return name
    return tkfont.nametofont("TkDefaultFont").actual("family")


def mix(a, b, t):
    start = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    end = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(start, end))


def theme_for(persona):
    palette = persona["palette"]
    bg, accent, text = palette["background"], palette["accent"], palette["text"]
    return {
        "panel": bg,
        "panel_edge": mix(bg, accent, 0.25),
        "bubble": mix(bg, accent, 0.12),
        "bubble_edge": mix(bg, accent, 0.22),
        "field": mix(bg, "#000000", 0.3),
        "field_edge": mix(bg, accent, 0.18),
        "badge": mix(bg, accent, 0.07),
        "glow_dim": mix(bg, accent, 0.3),
        "glow_bright": accent,
        "ink": text,
        "muted": mix(text, bg, 0.38),
        "avatar": mix(accent, bg, 0.2),
        "avatar_edge": mix(accent, bg, 0.45),
        "eyes": palette.get("eyes", text),
        "bun": accent,
        "bun_shade": mix(accent, "#000000", 0.2),
        "bun_face": "#111111",
        "bun_cheek": mix("#FF7AB8", accent, 0.3),
    }


def rounded_rect_items(canvas, x1, y1, x2, y2, r, tags=()):
    r = min(r, (x2 - x1) / 2, (y2 - y1) / 2)
    d = 2 * r
    items = [
        canvas.create_rectangle(x1 + r, y1, x2 - r, y2, width=0, tags=tags),
        canvas.create_rectangle(x1, y1 + r, x2, y2 - r, width=0, tags=tags),
    ]
    for ox, oy in ((x1, y1), (x2 - d, y1), (x1, y2 - d), (x2 - d, y2 - d)):
        items.append(canvas.create_oval(ox, oy, ox + d, oy + d, width=0, tags=tags))
    return items


def resolve_persona_key():
    key = os.environ.get("PERSONA", DEFAULT_PERSONA).strip().lower()
    if key not in PERSONAS:
        print(f"[buddy] unknown PERSONA {key!r}, using {DEFAULT_PERSONA!r}", file=sys.stderr)
        return DEFAULT_PERSONA
    return key


class Buddy:
    def __init__(self, root, hotkey_events, persona_key=DEFAULT_PERSONA, startup_notice=None):
        self.root = root
        self.hotkey_events = hotkey_events
        self.replies = queue.Queue()
        self.busy = False
        self.visible = True
        self.placeholder = False
        self.drag_offset = (0, 0)
        self.phase = 0.0
        self.bob = 0.0
        self.blink_at = time.monotonic() + 2.0
        self.blink_until = 0.0
        self.status_until = 0.0
        self.typing_job = None
        self.nswindow = None
        self.set_chrome = None
        self.previous_app = None
        self.themed = []
        self.persona_key = persona_key
        self.persona = PERSONAS[persona_key]
        self.theme = theme_for(self.persona)
        self.config = load_config()
        self.user_name = self.config.get("name")
        self.onboarding = not self.config.get("onboarded")
        self.calendar = CalendarCache()
        self.pending_notices = []
        self.noticed = set()
        self.client = anthropic.Anthropic() if os.environ.get("ANTHROPIC_API_KEY") else None
        self.family = pick_font_family()
        self.build()
        self.greet()
        if startup_notice:
            self.notify(startup_notice)
        threading.Thread(target=self.prefetch_calendar, daemon=True).start()
        self.poll()
        self.animate()

    def paint(self, item, **roles):
        self.themed.append((item, roles))
        return item

    def rounded(self, x1, y1, x2, y2, r, fill, outline=None, tags=()):
        if outline:
            for item in rounded_rect_items(self.canvas, x1, y1, x2, y2, r, tags):
                self.paint(item, fill=outline)
            x1, y1, x2, y2, r = x1 + 1, y1 + 1, x2 - 1, y2 - 1, r - 1
        for item in rounded_rect_items(self.canvas, x1, y1, x2, y2, r, tags):
            self.paint(item, fill=fill)

    def build(self):
        root = self.root
        root.overrideredirect(True)
        try:
            root.attributes("-stylemask", "")
        except tk.TclError:
            pass
        root.attributes("-topmost", True)
        self.transparent = True
        try:
            root.attributes("-transparent", True)
            root.config(bg=TRANSPARENT)
        except tk.TclError:
            self.transparent = False
        x = root.winfo_screenwidth() - WIDTH - 40
        root.geometry(f"{WIDTH}x{HEIGHT}+{x}+60")

        canvas = tk.Canvas(root, width=WIDTH, height=HEIGHT, highlightthickness=0, bd=0)
        canvas.pack(fill="both", expand=True)
        self.canvas = canvas

        self.rounded(0, 0, WIDTH, HEIGHT, RADIUS, fill="panel", outline="panel_edge", tags=("panel",))

        badge_x, badge_y = 46, 46
        self.halo = canvas.create_oval(badge_x - 29, badge_y - 29, badge_x + 29, badge_y + 29, width=2)
        self.paint(
            canvas.create_oval(badge_x - 25, badge_y - 25, badge_x + 25, badge_y + 25, outline=""),
            fill="badge",
        )
        self.draw_ghost(badge_x, badge_y + 2)
        self.draw_bun(badge_x, badge_y + 1)
        self.monogram = self.paint(
            canvas.create_text(badge_x, badge_y, font=(self.family, 20, "bold"), state="hidden"),
            fill="ink",
        )

        self.header_right = WIDTH - 42
        self.rounded(84, 16, self.header_right, 76, 14, fill="badge")
        self.name = self.paint(
            canvas.create_text(98, 35, anchor="w", font=(self.family, 15, "bold")),
            fill="ink",
        )
        self.status_font = tkfont.Font(family=self.family, size=11)
        self.status_dot = canvas.create_oval(99, 56, 105, 62, outline="")
        self.status = self.paint(
            canvas.create_text(112, 59, anchor="w", font=self.status_font),
            fill="muted",
        )

        close_x, close_y = WIDTH - 22, 30
        self.close_dot = self.paint(
            canvas.create_oval(close_x - 9, close_y - 9, close_x + 9, close_y + 9, outline="", tags=("close",)),
            fill="bubble",
        )
        self.paint(
            canvas.create_text(close_x, close_y - 1, text="×", font=(self.family, 13), tags=("close",)),
            fill="muted",
        )
        canvas.tag_bind("close", "<Enter>", lambda _e: canvas.itemconfigure(self.close_dot, fill=self.theme["bubble_edge"]))
        canvas.tag_bind("close", "<Leave>", lambda _e: canvas.itemconfigure(self.close_dot, fill=self.theme["bubble"]))
        canvas.tag_bind("close", "<ButtonRelease-1>", lambda _e: self.hide())

        bubble_top, bubble_bottom = 88, HEIGHT - 66
        self.rounded(16, bubble_top, WIDTH - 16, bubble_bottom, 16, fill="bubble", outline="bubble_edge")
        self.bubble = tk.Text(
            canvas, wrap="word", bd=0, highlightthickness=0,
            font=(self.family, 14), padx=0, pady=0, cursor="arrow", spacing2=4,
        )
        canvas.create_window(
            30, bubble_top + 13, anchor="nw", window=self.bubble,
            width=WIDTH - 60, height=bubble_bottom - bubble_top - 26,
        )

        field_top, field_bottom = HEIGHT - 52, HEIGHT - 16
        self.rounded(16, field_top, WIDTH - 16, field_bottom, 13, fill="field", outline="field_edge")
        field_mid = (field_top + field_bottom) / 2
        self.entry = tk.Entry(canvas, bd=0, highlightthickness=0, relief="flat", font=(self.family, 14))
        canvas.create_window(30, field_mid, anchor="w", window=self.entry, width=WIDTH - 80)
        self.paint(
            canvas.create_text(WIDTH - 34, field_mid, text="↵", font=(self.family, 13)),
            fill="muted",
        )

        self.entry.bind("<KeyPress>", self.clear_placeholder)
        self.entry.bind("<KeyRelease>", lambda _e: self.show_placeholder())
        self.entry.bind("<Return>", self.submit)
        root.bind("<Escape>", lambda _e: self.hide())
        root.bind("<Command-q>", lambda _e: root.destroy())
        canvas.bind("<ButtonPress-1>", self.start_drag)
        canvas.bind("<B1-Motion>", self.drag)

        self.apply_persona()
        root.update()
        self.nswindow, self.set_chrome = apply_macos_chrome(root, self.theme["panel"], self.theme["panel_edge"])
        if self.nswindow is None:
            try:
                root.attributes("-alpha", 0.97)
            except tk.TclError:
                pass
        self.apply_theme()
        self.show()

    def draw_ghost(self, cx, cy):
        canvas = self.canvas
        body = [
            (-14, 6), (-14, -4), (-11, -12), (-5, -16), (0, -17), (5, -16), (11, -12), (14, -4),
            (14, 6), (14, 13), (10, 9), (7, 14), (3.5, 9), (0, 14), (-3.5, 9), (-7, 14), (-10, 9), (-14, 13),
        ]
        self.paint(
            canvas.create_polygon(
                [v for x, y in body for v in (cx + x, cy + y)],
                smooth=True, width=1, tags=("float", "ghost_shape"),
            ),
            fill="avatar", outline="avatar_edge",
        )
        for side in (-1, 1):
            eye = [(10, -7), (3, -4), (4, -2), (9, -3)]
            self.paint(
                canvas.create_polygon(
                    [v for x, y in eye for v in (cx + side * x, cy + y)],
                    smooth=True, outline="", tags=("float", "ghost_shape", "ghost_eyes_open"),
                ),
                fill="eyes",
            )
            self.paint(
                canvas.create_line(
                    cx + side * 10, cy - 5, cx + side * 3, cy - 3,
                    width=2, capstyle="round", state="hidden", tags=("float", "ghost_eyes_closed"),
                ),
                fill="eyes",
            )
        self.paint(
            canvas.create_arc(
                cx - 7, cy - 3, cx + 7, cy + 7, start=200, extent=140,
                style="arc", width=2, tags=("float", "ghost_shape"),
            ),
            outline="ink",
        )

    def draw_bun(self, cx, cy):
        canvas = self.canvas
        self.paint(
            canvas.create_oval(cx - 18, cy - 16, cx + 18, cy + 17, outline="", tags=("float", "bun_shape")),
            fill="bun_shade",
        )
        self.paint(
            canvas.create_oval(cx - 18, cy - 16, cx + 15, cy + 13.5, outline="", tags=("float", "bun_shape")),
            fill="bun",
        )
        for x in (-6.5, 2.5):
            self.paint(
                canvas.create_oval(
                    cx + x - 1.8, cy - 8, cx + x + 1.8, cy - 1,
                    outline="", tags=("float", "bun_shape", "bun_eyes_open"),
                ),
                fill="bun_face",
            )
            self.paint(
                canvas.create_line(
                    cx + x - 2.2, cy - 4, cx + x + 2.2, cy - 4,
                    width=2, capstyle="round", state="hidden", tags=("float", "bun_eyes_closed"),
                ),
                fill="bun_face",
            )
        for x in (-11.5, 7.5):
            self.paint(
                canvas.create_oval(cx + x - 2.5, cy + 0.5, cx + x + 2.5, cy + 3.5, outline="", tags=("float", "bun_shape")),
                fill="bun_cheek",
            )
        self.paint(
            canvas.create_arc(
                cx - 5, cy - 2.5, cx + 1, cy + 3.5, start=200, extent=140,
                style="arc", width=2, tags=("float", "bun_shape"),
            ),
            outline="bun_face",
        )

    def apply_theme(self):
        theme = self.theme
        canvas = self.canvas
        canvas.config(bg=TRANSPARENT if self.transparent else theme["panel"])
        if not self.transparent:
            self.root.config(bg=theme["panel"])
        for item, roles in self.themed:
            canvas.itemconfigure(item, **{option: theme[role] for option, role in roles.items()})
        canvas.itemconfigure(self.halo, outline=theme["glow_dim"])
        canvas.itemconfigure(self.status_dot, fill=theme["glow_dim"])
        self.bubble.config(
            bg=theme["bubble"], fg=theme["ink"],
            selectbackground=theme["bubble_edge"], inactiveselectbackground=theme["bubble_edge"],
        )
        self.entry.config(
            bg=theme["field"], fg=theme["muted"] if self.placeholder else theme["ink"],
            insertbackground=theme["glow_bright"], selectbackground=theme["bubble_edge"],
        )
        canvas.itemconfigure("panel", state="hidden" if self.nswindow is not None else "normal")
        if self.set_chrome is not None:
            self.set_chrome(theme["panel"], theme["panel_edge"])

    def apply_persona(self):
        persona = self.persona
        canvas = self.canvas
        avatar = persona["avatar"]
        for kind in BLINKING_AVATARS:
            canvas.itemconfigure(f"{kind}_shape", state="normal" if avatar == kind else "hidden")
            canvas.itemconfigure(f"{kind}_eyes_closed", state="hidden")
        self.blink_until = 0.0
        canvas.itemconfigure(
            self.monogram, state="normal" if avatar == "monogram" else "hidden", text=persona["name"][:1],
        )
        canvas.itemconfigure(self.name, text=persona["name"])
        if self.placeholder:
            self.entry.delete(0, "end")
            self.placeholder = False
        self.show_placeholder()
        self.set_status(self.idle_status())
        self.apply_theme()

    def set_persona(self, key):
        self.persona_key = key
        self.persona = PERSONAS[key]
        self.theme = theme_for(self.persona)
        self.apply_persona()

    def greet(self):
        if self.onboarding:
            self.speak(ONBOARDING_NOTE.format(buddy=self.persona["name"]))
        elif self.client:
            self.say(self.persona["greeting"].format(name=self.user_name or "friend"), typing=True)
        else:
            self.say(self.persona["offline"]["no_key"], typing=True)

    def voice(self, persona, message):
        try:
            return voice_line(self.client, persona, message)
        except Exception as e:
            print(f"[buddy] voicing failed: {e!r}", file=sys.stderr)
            return persona["frame"].format(message=message)

    def speak(self, message, status=None):
        self.busy = True
        self.say("…")
        persona = self.persona
        threading.Thread(
            target=lambda: self.replies.put(("say", self.voice(persona, message), status)), daemon=True,
        ).start()

    def create_database(self, name):
        existed = os.path.exists(DB_PATH)
        try:
            db.get_connection(DB_PATH).close()
        except (duckdb.Error, OSError) as e:
            print(f"[buddy] couldn't create {DB_PATH}: {e}", file=sys.stderr)
            return DB_FAILED_NOTE.format(name=name, path=DB_DISPLAY_PATH)
        note = DB_FOUND_NOTE if existed else DB_CREATED_NOTE
        return note.format(name=name, path=DB_DISPLAY_PATH)

    def finish_onboarding(self, text):
        name = extract_name(text)
        if not name:
            self.speak(REASK_NOTE)
            return
        self.user_name = name
        self.onboarding = False
        self.config.update(name=name, onboarded=True)
        note = self.create_database(name)
        try:
            save_config(self.config)
        except OSError as e:
            print(f"[buddy] couldn't save {CONFIG_PATH}: {e}", file=sys.stderr)
            note += " " + SAVE_FAILED_NOTE
        self.clear_placeholder()
        self.show_placeholder()
        self.speak(note, status=SETUP_DONE_STATUS)
        threading.Thread(target=self.refresh_after_onboarding, daemon=True).start()

    def refresh_after_onboarding(self):
        note = refresh_activity()
        if note:
            self.replies.put(("raw_notice", note, None))

    def prefetch_calendar(self):
        _, error = self.calendar.get()
        if error:
            self.replies.put(("raw_notice", error, None))

    def notify(self, message):
        if message in self.noticed:
            return
        self.noticed.add(message)
        persona = self.persona
        threading.Thread(
            target=lambda: self.replies.put(("notice", self.voice(persona, message), None)), daemon=True,
        ).start()

    def idle_status(self):
        return SETUP_STATUS if self.onboarding else random.choice(self.persona["idle"])

    def placeholder_text(self):
        if self.onboarding:
            return "type your name…"
        return f"Ask {self.persona['name']} something…"

    def show_placeholder(self):
        if not self.placeholder and not self.entry.get():
            self.entry.insert(0, self.placeholder_text())
            self.entry.icursor(0)
            self.entry.config(fg=self.theme["muted"])
            self.placeholder = True

    def clear_placeholder(self, _event=None):
        if self.placeholder:
            self.entry.delete(0, "end")
            self.entry.config(fg=self.theme["ink"])
            self.placeholder = False

    def say(self, message, typing=False):
        if self.typing_job is not None:
            self.root.after_cancel(self.typing_job)
            self.typing_job = None
        self.bubble.config(state="normal")
        self.bubble.delete("1.0", "end")
        self.bubble.config(state="disabled")
        if typing:
            self.type_out(message, 0)
        else:
            self.append(message)

    def append(self, text):
        self.bubble.config(state="normal")
        self.bubble.insert("end", text)
        self.bubble.config(state="disabled")

    def type_out(self, message, index):
        self.append(message[index:index + 3])
        if index + 3 < len(message):
            self.typing_job = self.root.after(16, self.type_out, message, index + 3)
        else:
            self.typing_job = None

    def set_status(self, text, hold=0.0):
        room = self.header_right - 112 - 10
        if self.status_font.measure(text) > room:
            while text and self.status_font.measure(text + "…") > room:
                text = text[:-1]
            text += "…"
        self.canvas.itemconfigure(self.status, text=text)
        self.status_until = time.monotonic() + hold if hold else 0.0

    def run_command(self, text):
        parts = text.split()
        if parts[0].lower() != "/persona":
            return False
        names = ", ".join(PERSONAS)
        if len(parts) == 1:
            self.speak(f"My current persona is {self.persona_key}. You can switch with /persona followed by one of: {names}.")
        elif parts[1].lower() not in PERSONAS:
            self.speak(f"There's no persona called \"{parts[1]}\". You can pick one of: {names}.")
        else:
            self.set_persona(parts[1].lower())
            self.greet()
        return True

    def submit(self, _event=None):
        question = "" if self.placeholder else self.entry.get().strip()
        if not question or self.busy:
            return "break"
        self.entry.delete(0, "end")
        self.show_placeholder()
        if question.startswith("/") and self.run_command(question):
            return "break"
        if self.onboarding:
            self.finish_onboarding(question)
            return "break"
        if not self.client:
            self.say(self.persona["offline"]["no_key"], typing=True)
            return "break"
        if is_screen_question(question):
            self.look_at_screen(question)
            return "break"
        self.busy = True
        self.say("…")
        threading.Thread(
            target=self.answer, args=(self.persona, question, self.user_name), daemon=True,
        ).start()
        return "break"

    def look_at_screen(self, question):
        self.busy = True
        self.say("…")
        app = self.previous_app
        app_name = app.localizedName() if app is not None else None
        args = (self.persona, question, self.user_name, app_name)
        self.hide()
        if app is not None:
            bring_forward(app)
        self.root.after(
            400, lambda: threading.Thread(target=self.answer_about_screen, args=args, daemon=True).start(),
        )

    def answer_about_screen(self, persona, question, user_name, app_name):
        reappear = lambda: self.replies.put(("reappear", None, None))
        error = None
        try:
            summary = screen_reader.describe_screen(screen_reader.read_screen(on_captured=reappear), app_name)
            events, error = self.calendar.get()
            reply = ask_claude(self.client, persona, question, user_name, events, screen=summary)
        except screen_reader.ScreenReadError as e:
            reappear()
            reply = self.voice(persona, str(e))
        except Exception as e:
            reappear()
            print(f"[buddy] screen look failed: {e!r}", file=sys.stderr)
            reply = persona["offline"]["broken"]
        self.replies.put(("reply", reply, persona["done"]))
        if error:
            self.replies.put(("raw_notice", error, None))

    def answer(self, persona, question, user_name):
        error = None
        try:
            events, error = self.calendar.get()
            reply = ask_claude(self.client, persona, question, user_name, events)
        except Exception as e:
            print(f"[buddy] answer failed: {e!r}", file=sys.stderr)
            reply = persona["offline"]["broken"]
        self.replies.put(("reply", reply, persona["done"]))
        if error:
            self.replies.put(("raw_notice", error, None))

    def poll(self):
        while True:
            try:
                self.hotkey_events.get_nowait()
            except queue.Empty:
                break
            self.toggle()
        while True:
            try:
                kind, message, status = self.replies.get_nowait()
            except queue.Empty:
                break
            if kind == "reappear":
                if not self.visible:
                    self.show()
            elif kind == "raw_notice":
                self.notify(message)
            elif kind == "notice":
                self.pending_notices.append(message)
            else:
                self.busy = False
                self.say(message, typing=True)
                if status:
                    self.set_status(status, hold=5.0)
                else:
                    self.set_status(self.idle_status())
        if self.pending_notices and self.typing_job is None and not self.busy:
            for notice in self.pending_notices:
                self.append(f"\n\n{notice}")
            self.pending_notices = []
        self.root.after(100, self.poll)

    def animate(self):
        if self.visible:
            now = time.monotonic()
            speed, amplitude, glow = (6.0, 3.5, 1.0) if self.busy else (2.0, 2.5, 0.55)
            self.phase += speed * FRAME_MS / 1000
            offset = amplitude * math.sin(self.phase)
            self.canvas.move("float", 0, offset - self.bob)
            self.bob = offset
            pulse = (math.sin(self.phase * 0.8) + 1) / 2
            glow_color = mix(self.theme["glow_dim"], self.theme["glow_bright"], pulse * glow)
            self.canvas.itemconfigure(self.halo, outline=glow_color)
            self.canvas.itemconfigure(self.status_dot, fill=glow_color)

            avatar = self.persona["avatar"]
            if avatar in BLINKING_AVATARS:
                if self.blink_until and now >= self.blink_until:
                    self.canvas.itemconfigure(f"{avatar}_eyes_closed", state="hidden")
                    self.canvas.itemconfigure(f"{avatar}_eyes_open", state="normal")
                    self.blink_until = 0.0
                elif now >= self.blink_at:
                    self.canvas.itemconfigure(f"{avatar}_eyes_open", state="hidden")
                    self.canvas.itemconfigure(f"{avatar}_eyes_closed", state="normal")
                    self.blink_until = now + 0.13
                    self.blink_at = now + random.uniform(2.5, 6.0)

            if self.onboarding:
                self.set_status(SETUP_STATUS)
            elif self.busy:
                self.set_status(self.persona["busy"] + "." * (int(now * 3) % 4))
            elif self.status_until and now >= self.status_until:
                self.set_status(self.idle_status())
        self.root.after(FRAME_MS, self.animate)

    def toggle(self):
        if self.visible:
            self.hide()
        else:
            self.show()

    def show(self):
        self.visible = True
        app = frontmost_other_app()
        if app is not None:
            self.previous_app = app
        self.root.deiconify()
        self.root.lift()
        self.root.attributes("-topmost", True)
        activate_app()
        self.root.focus_force()
        self.entry.focus_set()
        if self.nswindow is not None:
            self.root.after(50, self.nswindow.invalidateShadow)

    def hide(self):
        self.visible = False
        self.root.withdraw()

    def start_drag(self, event):
        self.drag_offset = (event.x, event.y)

    def drag(self, event):
        x = self.root.winfo_pointerx() - self.drag_offset[0]
        y = self.root.winfo_pointery() - self.drag_offset[1]
        self.root.geometry(f"+{x}+{y}")


def main():
    persona_key = resolve_persona_key()
    startup_notice = refresh_activity() if load_config().get("onboarded") else None
    ctx = multiprocessing.get_context("spawn")
    hotkey_events = ctx.Queue()
    listener = ctx.Process(target=listen_for_hotkey, args=(hotkey_events,), daemon=True)
    listener.start()
    root = tk.Tk()
    root.title("Twin Buddy")
    Buddy(root, hotkey_events, persona_key, startup_notice)
    try:
        root.mainloop()
    finally:
        listener.terminate()
    sys.exit(0)


if __name__ == "__main__":
    main()
