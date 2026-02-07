import json
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

import openpyxl

# Default DB name; callers should pass config["database"] for a single app DB.


def _ensure_data_dir() -> Path:
    data_dir = Path("data")
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def seen_listing_hash(db_path: str, listing_hash: str) -> bool:
    """Return True if listing_hash already exists in lead_logs."""
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.execute(
            "SELECT 1 FROM lead_logs WHERE listing_hash = ? LIMIT 1",
            (listing_hash,),
        )
        return cur.fetchone() is not None
    except Exception:
        return False
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def init_leads_db(db_path: str = "leads.db") -> None:
    """Create or ensure lead and agent log tables exist."""
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS lead_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                listing_hash TEXT,
                contact_email TEXT,
                contact_phone TEXT,
                source_url TEXT,
                is_private INTEGER,
                confidence INTEGER,
                reason TEXT,
                status TEXT,
                message_subject TEXT,
                message_body TEXT,
                channel TEXT,
                timestamp INTEGER
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agency_name TEXT,
                listing_title TEXT,
                price TEXT,
                location TEXT,
                url TEXT,
                contact TEXT,
                reason TEXT,
                timestamp INTEGER
            )
            """
        )
        conn.commit()
    except Exception:
        # Keep runtime resilient; logging failures should not crash the bot.
        pass
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def log_lead(
    listing_hash: str,
    contacts: Dict[str, Any],
    source_url: str,
    detection: Dict[str, Any],
    status: str,
    message: Dict[str, Any] | None = None,
    channel: str | None = None,
    db_path: str = "leads.db",
) -> None:
    """Log private lead action to DB."""
    email = contacts.get("email")
    phone = contacts.get("phone")
    subject = (message or {}).get("subject")
    body = (message or {}).get("body")

    conn = None
    try:
        conn = sqlite3.connect(db_path)
        conn.execute(
            """
            INSERT INTO lead_logs (
                listing_hash, contact_email, contact_phone, source_url,
                is_private, confidence, reason, status,
                message_subject, message_body, channel, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            ,
            (
                listing_hash,
                email,
                phone,
                source_url,
                1 if detection.get("is_private") else 0,
                int(detection.get("confidence", 0) or 0),
                detection.get("reason", ""),
                status,
                subject,
                body,
                channel,
                int(time.time()),
            ),
        )
        conn.commit()
    except Exception:
        # Swallow logging errors; main flow should continue.
        pass
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def log_agent_listing(details: Dict[str, Any], db_path: str = "leads.db") -> None:
    """Log agent listing to DB + text file + XLS export."""
    timestamp = int(time.time())
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        conn.execute(
            """
            INSERT INTO agent_logs (
                agency_name, listing_title, price, location, url, contact, reason, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """
            ,
            (
                details.get("agency_name"),
                details.get("title"),
                details.get("price"),
                details.get("location"),
                details.get("url"),
                details.get("contact"),
                details.get("reason"),
                timestamp,
            ),
        )
        conn.commit()
    except Exception:
        # Do not fail the main flow on logging issues.
        pass
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    data_dir = _ensure_data_dir()

    # Text log
    try:
        with (data_dir / "agents.txt").open("a", encoding="utf-8") as f:
            f.write(json.dumps({**details, "timestamp": timestamp}) + "\n")
    except Exception:
        pass

    # XLSX export (append or create)
    try:
        xlsx_path = data_dir / "agents.xlsx"
        if xlsx_path.exists():
            wb = openpyxl.load_workbook(xlsx_path)
            ws = wb.active
        else:
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.append(
                [
                    "agency_name",
                    "title",
                    "price",
                    "location",
                    "url",
                    "contact",
                    "reason",
                    "timestamp",
                ]
            )
        ws.append(
            [
                details.get("agency_name", ""),
                details.get("title", ""),
                details.get("price", ""),
                details.get("location", ""),
                details.get("url", ""),
                details.get("contact", ""),
                details.get("reason", ""),
                datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S"),
            ]
        )
        wb.save(xlsx_path)
    except Exception:
        # Ignore XLSX errors silently to avoid crashing the bot.
        pass

