import sqlite3
import time
from typing import Optional, Dict, Any


def init_db(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contact TEXT,
            listing_hash TEXT,
            created_at INTEGER
        )
        """
    )
    conn.commit()
    return conn


def already_contacted(conn: sqlite3.Connection, contact: str) -> bool:
    cur = conn.execute("SELECT 1 FROM leads WHERE contact = ? LIMIT 1", (contact,))
    return cur.fetchone() is not None


def log_contacted(conn: sqlite3.Connection, contact: str, listing_hash: str, created_at: int) -> None:
    conn.execute(
        "INSERT INTO leads (contact, listing_hash, created_at) VALUES (?, ?, ?)",
        (contact, listing_hash, created_at),
    )
    conn.commit()


def count_contacts_since(conn: sqlite3.Connection, since_ts: int) -> int:
    cur = conn.execute("SELECT COUNT(*) FROM leads WHERE created_at >= ?", (since_ts,))
    row = cur.fetchone()
    return int(row[0]) if row else 0


def init_listings_db(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT,
            url TEXT UNIQUE,
            title TEXT,
            price TEXT,
            location TEXT,
            description TEXT,
            contact_name TEXT,
            contact_email TEXT,
            contact_phone TEXT,
            scraped_at INTEGER
        )
        """
    )
    conn.commit()
    conn.close()


def upsert_listing(db_path: str, listing: Dict[str, Any]) -> bool:
    conn = sqlite3.connect(db_path)
    cur = conn.execute("SELECT 1 FROM listings WHERE url = ? LIMIT 1", (listing.get("url"),))
    if cur.fetchone() is not None:
        conn.close()
        return False
    conn.execute(
        """
        INSERT INTO listings (
            source,
            url,
            title,
            price,
            location,
            description,
            contact_name,
            contact_email,
            contact_phone,
            scraped_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            listing.get("source"),
            listing.get("url"),
            listing.get("title"),
            listing.get("price"),
            listing.get("location"),
            listing.get("description"),
            listing.get("contact_name"),
            listing.get("contact_email"),
            listing.get("contact_phone"),
            listing.get("scraped_at", int(time.time())),
        ),
    )
    conn.commit()
    conn.close()
    return True
