import duckdb
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

DB_PATH = os.environ.get("TWIN_DB_PATH") or os.path.expanduser("~/.twin/twin.duckdb")


def get_connection(db_path: str = DB_PATH) -> duckdb.DuckDBPyConnection:
    parent = os.path.dirname(os.path.abspath(db_path))
    os.makedirs(parent, mode=0o700, exist_ok=True)
    con = duckdb.connect(db_path)
    con.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id VARCHAR PRIMARY KEY,
            timestamp TIMESTAMP,
            type VARCHAR,
            amount DOUBLE,
            merchant VARCHAR,
            ref_number VARCHAR,
            raw_text VARCHAR
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS access_log (
            id VARCHAR PRIMARY KEY,
            timestamp TIMESTAMP,
            source VARCHAR,
            action VARCHAR,
            data_touched VARCHAR
        )
    """)
    return con


def insert_access_log(con, source: str, action: str, data_touched: str) -> str:
    log_id = str(uuid.uuid4())
    con.execute(
        "INSERT INTO access_log (id, timestamp, source, action, data_touched) VALUES (?, ?, ?, ?, ?)",
        [log_id, datetime.now(timezone.utc), source, action, data_touched],
    )
    return log_id


def transaction_exists(con, raw_text: str) -> bool:
    return con.execute(
        "SELECT 1 FROM transactions WHERE raw_text = ? LIMIT 1",
        [raw_text],
    ).fetchone() is not None


def insert_transaction(
    con,
    type: str,
    amount: float,
    merchant: str,
    ref_number: str,
    raw_text: str,
    source: str = "transaction_import",
    timestamp: Optional[datetime] = None,
) -> str:
    txn_id = str(uuid.uuid4())
    con.execute(
        """
        INSERT INTO transactions (id, timestamp, type, amount, merchant, ref_number, raw_text)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [txn_id, timestamp or datetime.now(timezone.utc), type, amount, merchant, ref_number, raw_text],
    )
    insert_access_log(
        con,
        source=source,
        action="insert_transaction",
        data_touched=f"transaction {txn_id}: extracted {type} of {amount} from {merchant} (ref {ref_number})",
    )
    return txn_id


def get_recent_access_log(con, limit: int = 50):
    return con.execute(
        "SELECT id, timestamp, source, action, data_touched FROM access_log ORDER BY timestamp DESC LIMIT ?",
        [limit],
    ).fetchall()
