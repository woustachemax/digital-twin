import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
for sibling in ("twin-ingest", "twin-parse", "twin-db"):
    sys.path.insert(0, os.path.join(BASE_DIR, "..", sibling))

from imessage_export import fetch_last_messages
from sms_parser import parse_messages
from db import get_connection, insert_transaction, transaction_exists


def main():
    messages = fetch_last_messages()
    con = get_connection()
    inserted = 0
    skipped = 0
    try:
        for message in messages:
            for txn in parse_messages([message]):
                if transaction_exists(con, message["text"]):
                    skipped += 1
                    continue
                insert_transaction(
                    con,
                    type=txn["type"],
                    amount=txn["amount"],
                    merchant=txn["merchant"],
                    ref_number=txn["reference"],
                    raw_text=message["text"],
                    source="imessage_pipeline",
                    timestamp=txn["timestamp"],
                )
                inserted += 1
    finally:
        con.close()
    print(f"Inserted {inserted} transactions ({skipped} duplicates skipped)")


if __name__ == "__main__":
    main()
