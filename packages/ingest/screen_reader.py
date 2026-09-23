import os
import re
import shutil
import subprocess
import tempfile

SHORTCUT_NAME = os.environ.get("TWIN_OCR_SHORTCUT", "Twin Extract Text")

PERMISSION_MESSAGE = (
    "I can't see your screen yet. Give your terminal Screen Recording access in System Settings → "
    "Privacy & Security → Screen & System Audio Recording, then ask me again."
)
NOTHING_READ_MESSAGE = (
    "I couldn't make out anything on your screen. If your terminal doesn't have Screen Recording access yet, "
    "allow it in System Settings → Privacy & Security → Screen & System Audio Recording."
)
OCR_UNAVAILABLE_MESSAGE = (
    "On-device text recognition isn't set up yet. Install it with pip install pyobjc-framework-Vision, "
    f"or create a Shortcut named \"{SHORTCUT_NAME}\" that extracts text from an image."
)

APP_KINDS = [
    (("terminal", "iterm", "iterm2", "warp", "ghostty", "alacritty", "kitty", "hyper"), "a terminal session"),
    (("code", "cursor", "xcode", "pycharm", "intellij", "sublime", "zed", "nova", "webstorm", "android studio"), "some code"),
    (("mail", "outlook", "spark", "airmail", "mimestream", "superhuman"), "an email inbox"),
    (("messages", "slack", "whatsapp", "telegram", "discord", "signal", "teams", "messenger"), "a chat conversation"),
    (("calendar", "fantastical", "busycal"), "a calendar"),
    (("notes", "obsidian", "notion", "bear", "pages", "word", "craft", "ulysses"), "some notes or writing"),
    (("numbers", "excel"), "a spreadsheet"),
    (("keynote", "powerpoint"), "a slide deck"),
    (("finder",), "some files and folders"),
    (("spotify", "music", "podcasts"), "a music or podcast player"),
    (("zoom", "facetime", "webex"), "a video call"),
    (("figma", "sketch", "photoshop", "illustrator", "affinity", "pixelmator"), "a design file"),
    (("preview", "acrobat", "skim"), "a document"),
    (("tv", "netflix", "vlc", "iina", "quicktime"), "a video"),
]

CONTENT_KINDS = [
    ("some code", ("def ", "import ", "return ", "function", "const ", "class ", "=>", "});", "self.", "print(")),
    ("a terminal session", ("command not found", "zsh", "bash", "$ git", "% git", "pip install", "npm ", "last login")),
    ("an email inbox", ("inbox", "compose", "unread", "subject", "forward", "archive", "drafts")),
    ("a chat conversation", ("delivered", "is typing", "direct messages", "channels", "threads", "imessage", "new message")),
    ("a video", ("subscribe", "views", "watch later", "up next", "episode", "playlist")),
    ("a shopping page", ("add to cart", "buy now", "checkout", "in stock", "free delivery", "your cart")),
    ("a social feed", ("retweet", "repost", "followers", "following", "trending", "for you")),
    ("a code repository", ("pull request", "commits", "branches", "issues", "merged", "readme")),
    ("a spreadsheet", ("=sum", "sheet1", "sheet 1", "column", "pivot")),
    ("a calendar", ("all-day", "today", "week", "month", "mon", "tue", "wed", "thu", "fri")),
    ("a search results page", ("people also ask", "search results", "all images videos", "sponsored")),
    ("an article", ("min read", "published", "related articles", "share this", "newsletter")),
    ("a document", ("page 1", "table of contents", "chapter", "introduction", "references")),
]


class ScreenReadError(Exception):
    pass


def capture(path):
    try:
        result = subprocess.run(
            ["screencapture", "-x", "-m", "-t", "png", path], capture_output=True, text=True, timeout=15,
        )
    except FileNotFoundError:
        raise ScreenReadError("Reading the screen needs macOS (screencapture wasn't found).")
    except subprocess.TimeoutExpired:
        raise ScreenReadError("Taking a screenshot timed out. Try asking again?")
    if result.returncode != 0 or not os.path.exists(path) or os.path.getsize(path) == 0:
        raise ScreenReadError(PERMISSION_MESSAGE)


def ocr_with_vision(path):
    import Vision
    from Foundation import NSURL

    handler = Vision.VNImageRequestHandler.alloc().initWithURL_options_(NSURL.fileURLWithPath_(path), None)
    request = Vision.VNRecognizeTextRequest.alloc().init()
    request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    request.setUsesLanguageCorrection_(True)
    ok, _ = handler.performRequests_error_([request], None)
    if not ok:
        raise ScreenReadError("On-device text recognition failed. Try asking again?")
    observations = sorted(
        request.results() or [],
        key=lambda o: (-round(o.boundingBox().origin.y, 2), o.boundingBox().origin.x),
    )
    lines = []
    for observation in observations:
        candidates = observation.topCandidates_(1)
        if candidates:
            lines.append(candidates[0].string())
    return "\n".join(lines)


def ocr_with_shortcut(path, workdir):
    output = os.path.join(workdir, "text.txt")
    try:
        result = subprocess.run(
            ["shortcuts", "run", SHORTCUT_NAME, "--input-path", path, "--output-path", output],
            capture_output=True, text=True, timeout=60,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        raise ScreenReadError(OCR_UNAVAILABLE_MESSAGE)
    if result.returncode != 0 or not os.path.exists(output):
        raise ScreenReadError(OCR_UNAVAILABLE_MESSAGE)
    with open(output, encoding="utf-8", errors="replace") as f:
        return f.read()


def vision_available():
    try:
        import Vision
    except ImportError:
        return False
    return hasattr(Vision, "VNRecognizeTextRequest")


def read_screen(on_captured=None):
    workdir = tempfile.mkdtemp(prefix="twin-screen-")
    path = os.path.join(workdir, "screen.png")
    try:
        try:
            capture(path)
        finally:
            if on_captured is not None:
                on_captured()
        text = ocr_with_vision(path) if vision_available() else ocr_with_shortcut(path, workdir)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    if len(text.split()) < 3:
        raise ScreenReadError(NOTHING_READ_MESSAGE)
    return text


def clean_app_name(name):
    if not name:
        return None
    cleaned = re.sub(r"[^A-Za-z0-9 .&+\-]", "", name).strip()
    return cleaned[:40] or None


def app_kind(app_name):
    if not app_name:
        return None
    lowered = app_name.lower()
    words = set(re.split(r"[^a-z0-9]+", lowered))
    for names, kind in APP_KINDS:
        for name in names:
            if (" " in name and name in lowered) or name in words:
                return kind
    return None


def content_kind(text):
    lowered = " ".join(text.lower().split())
    best, best_score = None, 1
    for kind, keywords in CONTENT_KINDS:
        score = sum(1 for keyword in keywords if keyword in lowered)
        if score > best_score:
            best, best_score = kind, score
    return best


def describe_screen(text, app_name=None):
    app = clean_app_name(app_name)
    content = content_kind(text) or app_kind(app)
    if app and content:
        return f"They're in {app}, looking at what seems to be {content}."
    if app:
        return f"They're in {app}, but it's hard to tell what exactly is on screen."
    if content:
        return f"Their screen seems to show {content}."
    return "Their screen has some text on it, but it's hard to tell what it is."


if __name__ == "__main__":
    try:
        screen_text = read_screen()
    except ScreenReadError as e:
        print(e)
        raise SystemExit(1)
    print(describe_screen(screen_text))
    print(f"(read {len(screen_text.split())} words; the screenshot has already been deleted)")
