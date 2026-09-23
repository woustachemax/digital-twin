import multiprocessing
import os
import queue
import re
import sys
import threading
import tkinter as tk
from datetime import datetime

import anthropic
import duckdb
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("TWIN_DB_PATH", os.path.join(BASE_DIR, "twin.duckdb"))
MODEL = "claude-sonnet-4-6"
HOTKEY = "<cmd>+<shift>+<space>"

WIDTH = 340
HEIGHT = 260
TRANSPARENT = "systemTransparent"
BUBBLE = "#FFF8E7"
BUBBLE_EDGE = "#E8D9B5"
INK = "#3B3226"
MUTED = "#9A8B70"
FIELD = "#FFFFFF"
FIELD_EDGE = "#D9CFBC"

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

SYSTEM_PROMPT = """You are a friendly personal assistant who lives in a small floating speech bubble on the user's desktop. You have a general sense of the user's recent financial activity, described below in vague terms only.

Use that context when it's relevant to what the user asks, and ignore it when it isn't. Never state or guess exact amounts, balances, account numbers, reference numbers, or who the user paid, and don't imply you know more than the general picture below. If the user asks for specifics, tell them you only have a rough sense of their recent activity.

Your replies appear in a small bubble, so keep them to a few warm, conversational sentences in plain text without markdown.

Recent activity:
{context}"""


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
        return "No recent financial activity is available."
    try:
        con = duckdb.connect(DB_PATH, read_only=True)
        try:
            rows = con.execute(
                "SELECT type, merchant, timestamp FROM transactions ORDER BY timestamp DESC LIMIT 5"
            ).fetchall()
        finally:
            con.close()
    except duckdb.Error:
        return "Recent financial activity couldn't be loaded right now."
    if not rows:
        return "No recent financial activity is available."
    lines = list(dict.fromkeys(describe(*row) for row in rows))
    return "\n".join(f"- {line}" for line in lines)


def ask_claude(client, question):
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT.format(context=build_context()),
            messages=[{"role": "user", "content": question}],
        )
    except anthropic.AuthenticationError:
        return "My API key doesn't seem to work. Check ANTHROPIC_API_KEY?"
    except anthropic.RateLimitError:
        return "I'm being rate limited. Give me a moment and ask again."
    except anthropic.APIConnectionError:
        return "I couldn't reach the internet just now."
    except anthropic.APIStatusError as e:
        return f"Something went wrong on the API side ({e.status_code})."
    if response.stop_reason == "refusal":
        return "Sorry, I can't help with that one."
    text = "".join(block.text for block in response.content if block.type == "text").strip()
    return text or "Hmm, I've got nothing for that."


def listen_for_hotkey(events):
    from pynput import keyboard

    with keyboard.GlobalHotKeys({HOTKEY: lambda: events.put("toggle")}) as listener:
        listener.join()


def activate_app():
    try:
        from AppKit import NSApplication
    except ImportError:
        return
    NSApplication.sharedApplication().activateIgnoringOtherApps_(True)


def rounded_rect(canvas, x1, y1, x2, y2, r, **kwargs):
    points = [
        x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
        x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
        x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, **kwargs)


class Buddy:
    def __init__(self, root, hotkey_events):
        self.root = root
        self.hotkey_events = hotkey_events
        self.replies = queue.Queue()
        self.busy = False
        self.visible = True
        self.drag_offset = (0, 0)
        self.client = anthropic.Anthropic() if os.environ.get("ANTHROPIC_API_KEY") else None
        self.build()
        if self.client:
            self.say("Hi! Ask me anything. Cmd+Shift+Space hides me.")
        else:
            self.say("I need ANTHROPIC_API_KEY set in my environment before I can chat.")
        self.poll()

    def build(self):
        root = self.root
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        background = TRANSPARENT
        try:
            root.attributes("-transparent", True)
            root.config(bg=TRANSPARENT)
        except tk.TclError:
            background = BUBBLE
            root.config(bg=background)
        x = root.winfo_screenwidth() - WIDTH - 40
        root.geometry(f"{WIDTH}x{HEIGHT}+{x}+60")

        canvas = tk.Canvas(root, width=WIDTH, height=HEIGHT, bg=background, highlightthickness=0, bd=0)
        canvas.pack(fill="both", expand=True)

        bubble_bottom = HEIGHT - 66
        rounded_rect(canvas, 6, 6, WIDTH - 6, bubble_bottom, 22, fill=BUBBLE, outline=BUBBLE_EDGE, width=1.5)
        canvas.create_polygon(
            40, bubble_bottom - 1, 62, bubble_bottom - 1, 36, bubble_bottom + 16,
            fill=BUBBLE, outline=BUBBLE_EDGE, width=1.5,
        )
        canvas.create_line(41, bubble_bottom - 1, 61, bubble_bottom - 1, fill=BUBBLE, width=3)

        close = canvas.create_text(WIDTH - 24, 22, text="×", fill=MUTED, font=("Helvetica", 16))
        canvas.tag_bind(close, "<Button-1>", lambda _e: self.hide())

        self.bubble = tk.Text(
            canvas, wrap="word", bd=0, highlightthickness=0, bg=BUBBLE, fg=INK,
            font=("Helvetica", 14), padx=0, pady=0, cursor="arrow", spacing2=3,
        )
        canvas.create_window(24, 36, anchor="nw", window=self.bubble, width=WIDTH - 48, height=bubble_bottom - 54)

        field_top = HEIGHT - 44
        rounded_rect(canvas, 6, field_top, WIDTH - 6, HEIGHT - 6, 16, fill=FIELD, outline=FIELD_EDGE, width=1.5)
        self.entry = tk.Entry(
            canvas, bd=0, highlightthickness=0, relief="flat", bg=FIELD, fg=INK,
            insertbackground=INK, font=("Helvetica", 14),
        )
        canvas.create_window(20, field_top + 19, anchor="w", window=self.entry, width=WIDTH - 40)

        self.entry.bind("<Return>", self.submit)
        root.bind("<Escape>", lambda _e: self.hide())
        root.bind("<Command-q>", lambda _e: root.destroy())
        canvas.bind("<ButtonPress-1>", self.start_drag)
        canvas.bind("<B1-Motion>", self.drag)

        self.show()

    def say(self, message):
        self.bubble.config(state="normal")
        self.bubble.delete("1.0", "end")
        self.bubble.insert("1.0", message)
        self.bubble.config(state="disabled")
        self.bubble.yview_moveto(0)

    def submit(self, _event=None):
        question = self.entry.get().strip()
        if not question or self.busy:
            return
        if not self.client:
            self.say("I need ANTHROPIC_API_KEY set in my environment before I can chat.")
            return
        self.entry.delete(0, "end")
        self.busy = True
        self.say("Thinking…")
        threading.Thread(target=self.answer, args=(question,), daemon=True).start()

    def answer(self, question):
        try:
            reply = ask_claude(self.client, question)
        except Exception:
            reply = "Oops, something broke while I was thinking. Try again?"
        self.replies.put(reply)

    def poll(self):
        while True:
            try:
                self.hotkey_events.get_nowait()
            except queue.Empty:
                break
            self.toggle()
        while True:
            try:
                reply = self.replies.get_nowait()
            except queue.Empty:
                break
            self.busy = False
            self.say(reply)
        self.root.after(100, self.poll)

    def toggle(self):
        if self.visible:
            self.hide()
        else:
            self.show()

    def show(self):
        self.visible = True
        self.root.deiconify()
        self.root.lift()
        self.root.attributes("-topmost", True)
        activate_app()
        self.root.focus_force()
        self.entry.focus_set()

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
    ctx = multiprocessing.get_context("spawn")
    hotkey_events = ctx.Queue()
    listener = ctx.Process(target=listen_for_hotkey, args=(hotkey_events,), daemon=True)
    listener.start()
    root = tk.Tk()
    root.title("Twin Buddy")
    Buddy(root, hotkey_events)
    try:
        root.mainloop()
    finally:
        listener.terminate()
    sys.exit(0)


if __name__ == "__main__":
    main()
