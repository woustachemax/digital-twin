import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
from datetime import datetime, timedelta

CHAT_DB_DIR = os.path.expanduser("~/Library/Messages")
CHAT_DB_PATH = os.path.join(CHAT_DB_DIR, "chat.db")
APPLE_EPOCH = datetime(2001, 1, 1)


def stage_db_copy():
    tmp_dir = tempfile.mkdtemp(prefix="imessage_export_")
    tmp_db = os.path.join(tmp_dir, "chat.db")
    for suffix in ("", "-wal", "-shm"):
        src = CHAT_DB_PATH + suffix
        if os.path.exists(src):
            shutil.copy2(src, tmp_db + suffix)
    return tmp_db


def convert_apple_timestamp(raw_value):
    if raw_value is None:
        return None
    seconds = raw_value / 1_000_000_000 if raw_value > 10 ** 12 else raw_value
    try:
        return APPLE_EPOCH + timedelta(seconds=seconds)
    except OverflowError:
        return None


def extract_text_from_attributed_body(blob):
    if not blob:
        return None
    text = extract_via_streamtyped(blob)
    if text:
        return text
    return extract_via_plutil(blob)


def extract_via_streamtyped(blob):
    try:
        marker = b"NSString"
        idx = blob.find(marker)
        if idx == -1:
            return None
        chunk = blob[idx + len(marker):]
        chunk = chunk[6:]
        if not chunk:
            return None
        first = chunk[0]
        if first == 0x81:
            length = int.from_bytes(chunk[1:3], "little")
            payload = chunk[3:3 + length]
        else:
            length = first
            payload = chunk[1:1 + length]
        decoded = payload.decode("utf-8", errors="replace").strip()
        return decoded or None
    except Exception:
        return None


def extract_via_plutil(blob):
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as f:
            f.write(blob)
            tmp_path = f.name
        result = subprocess.run(
            ["plutil", "-convert", "xml1", "-o", "-", tmp_path],
            capture_output=True,
            timeout=5,
        )
        if result.returncode != 0:
            return None
        xml = result.stdout.decode("utf-8", errors="replace")
        matches = re.findall(r"<string>(.*?)</string>", xml, re.DOTALL)
        for candidate in matches:
            cleaned = candidate.strip()
            if cleaned and cleaned not in ("NSString", "NSMutableString", "NSAttributedString", "NSObject", "NSDictionary"):
                return cleaned
        return None
    except Exception:
        return None
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)


def fetch_last_messages(limit=200):
    tmp_db = stage_db_copy()
    conn = sqlite3.connect(f"file:{tmp_db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            message.ROWID as message_id,
            message.text as text,
            message.attributedBody as attributed_body,
            message.date as date,
            message.is_from_me as is_from_me,
            handle.id as handle_id
        FROM message
        LEFT JOIN handle ON message.handle_id = handle.ROWID
        ORDER BY message.date DESC
        LIMIT ?
        """,
        (limit,),
    )
    rows = cursor.fetchall()
    conn.close()
    shutil.rmtree(os.path.dirname(tmp_db), ignore_errors=True)

    results = []
    for row in reversed(rows):
        text = row["text"]
        if not text:
            text = extract_text_from_attributed_body(row["attributed_body"])
        if not text:
            continue
        sender = "Me" if row["is_from_me"] else (row["handle_id"] or "Unknown")
        results.append({
            "text": text,
            "timestamp": convert_apple_timestamp(row["date"]),
            "sender": sender,
        })
    return results


if __name__ == "__main__":
    messages = fetch_last_messages(200)
    print(f"Total messages recovered: {len(messages)}")
    for msg in messages[-5:]:
        print(msg)
