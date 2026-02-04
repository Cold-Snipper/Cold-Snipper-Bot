import sqlite3
import pytest

pytest.importorskip("tkinter")

from gui import fetch_viable_leads


def test_fetch_viable_leads(tmp_path):
    db_path = tmp_path / "leads.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE leads (
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
    conn.execute(
        """
        INSERT INTO leads (
            title, price, location, contact, listing_url, description, airbnb_viable,
            viability_reason, rating, qualification_factors, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "Test Listing",
            "$300,000",
            "Test City",
            "test@example.com",
            "http://example.com/listing",
            "Description",
            1,
            "Good",
            9,
            "['amenity']",
            "New",
        ),
    )
    conn.commit()
    conn.close()

    leads = fetch_viable_leads(str(db_path))
    assert len(leads) == 1
    assert leads[0]["title"] == "Test Listing"
