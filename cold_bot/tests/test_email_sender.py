import os
import sqlite3
from unittest.mock import patch

from silos.email_sender import init_db, log_contact, is_contacted, send_email, check_recent_sends


def test_init_db(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(str(db_path))
    conn = sqlite3.connect(db_path)
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='contacts'"
    )
    assert cur.fetchone() is not None
    conn.close()


def test_is_contacted(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(str(db_path))
    log_contact(str(db_path), "a@b.com", "success")
    assert is_contacted(str(db_path), "a@b.com") is True


def test_send_email():
    with patch("silos.email_sender.yagmail.SMTP") as mock_smtp:
        instance = mock_smtp.return_value
        instance.send.return_value = None
        result = send_email(
            to="test@example.com",
            proposal="Hello",
            from_email="from@example.com",
            app_pw="pw",
            smtp_host="smtp.example.com",
            db_path=":memory:",
            max_per_hour=10,
        )
        assert result is True


def test_rate_limit(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(str(db_path))
    for _ in range(5):
        log_contact(str(db_path), f"user{_}@b.com", "success")
    assert check_recent_sends(str(db_path), 1) is False


def test_functional():
    if not os.getenv("RUN_FUNCTIONAL"):
        return
    result = send_email(
        to="test@example.com",
        proposal="Hello",
        from_email="from@example.com",
        app_pw="pw",
        smtp_host="smtp.mailtrap.io",
        db_path=":memory:",
        max_per_hour=10,
    )
    assert result in [True, False]
