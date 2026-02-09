import sqlite3
from typing import Optional, List, Dict

import yagmail


def init_db(db_path: str) -> None:
    """Description.

    Args:
        db_path (type): desc.

    Returns:
        type: desc.

    Raises:
        exc: when.
    """
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS contacts (contact TEXT PRIMARY KEY, status TEXT, timestamp DATETIME)"
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            price TEXT,
            location TEXT,
            contact TEXT,
            listing_url TEXT,
            description TEXT,
            airbnb_viable INTEGER,
            viability_reason TEXT,
            rating INTEGER,
            qualification_factors TEXT,
            status TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    try:
        conn.execute("ALTER TABLE leads ADD COLUMN listing_url TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE leads ADD COLUMN priority_score INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    conn.commit()
    conn.close()


def is_contacted(db_path: str, contact: str) -> bool:
    """Description.

    Args:
        db_path (type): desc.
        contact (type): desc.

    Returns:
        type: desc.

    Raises:
        exc: when.
    """
    conn = sqlite3.connect(db_path)
    cur = conn.execute("SELECT 1 FROM contacts WHERE contact = ?", (contact,))
    result = cur.fetchone() is not None
    conn.close()
    return result


def log_contact(db_path: str, contact: str, status: str) -> None:
    """Description.

    Args:
        db_path (type): desc.
        contact (type): desc.
        status (type): desc.

    Returns:
        type: desc.

    Raises:
        exc: when.
    """
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT OR REPLACE INTO contacts (contact, status, timestamp) VALUES (?, ?, datetime('now'))",
        (contact, status),
    )
    conn.commit()
    conn.close()


def send_email(
    to: str,
    proposal: str,
    from_email: str,
    app_pw: str,
    smtp_host: str,
    db_path: str,
    max_per_hour: int,
    subject: str | None = None,
) -> bool:
    """Send one email. Uses subject if provided, else default."""
    if not check_recent_sends(db_path, max_per_hour):
        return False
    subj = subject or "Real Estate Partnership Proposal"
    try:
        yag = yagmail.SMTP(from_email, app_pw, host=smtp_host)
        yag.send(to=to, subject=subj, contents=proposal)
        yag.close()
        return True
    except Exception:
        return False


def check_recent_sends(db_path: str, max_per_hour: int) -> bool:
    """Description.

    Args:
        db_path (type): desc.
        max_per_hour (type): desc.

    Returns:
        type: desc.

    Raises:
        exc: when.
    """
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS contacts (contact TEXT PRIMARY KEY, status TEXT, timestamp DATETIME)"
    )
    cur = conn.execute(
        "SELECT COUNT(*) FROM contacts WHERE timestamp >= datetime('now', '-1 hour')"
    )
    count = cur.fetchone()[0]
    conn.close()
    return count < max_per_hour


def upsert_lead(
    db_path: str,
    title: str,
    price: str,
    location: str,
    contact: str,
    listing_url: str,
    description: str,
    airbnb_viable: bool,
    viability_reason: str,
    rating: int,
    qualification_factors: str,
    status: str = "New",
    priority_score: Optional[int] = None,
) -> None:
    conn = sqlite3.connect(db_path)
    if priority_score is None:
        priority_score = 0
    conn.execute(
        """
        INSERT INTO leads (
            title, price, location, contact, listing_url, description, airbnb_viable,
            viability_reason, rating, qualification_factors, status, priority_score
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            title,
            price,
            location,
            contact,
            listing_url,
            description,
            1 if airbnb_viable else 0,
            viability_reason,
            rating,
            qualification_factors,
            status,
            priority_score,
        ),
    )
    conn.commit()
    conn.close()


def get_viable_leads(db_path: str) -> List[Dict[str, object]]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.execute(
        """
        SELECT id, title, price, location, contact, listing_url, viability_reason, rating, status, description, qualification_factors, priority_score
        FROM leads
        WHERE airbnb_viable = 1
        ORDER BY priority_score DESC, rating DESC
        """
    )
    rows = [dict(row) for row in cur.fetchall()]
    conn.close()
    return rows


def update_lead_status(db_path: str, lead_id: int, status: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE leads SET status = ? WHERE id = ?", (status, lead_id))
    conn.commit()
    conn.close()


def reset_db(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute("DELETE FROM contacts")
    conn.execute("DELETE FROM leads")
    conn.commit()
    conn.close()
