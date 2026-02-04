from unittest.mock import MagicMock

from silos.data_scraper import extract_listings


def test_extract_listings():
    page = MagicMock()
    page.url = "http://example.com"
    el1 = MagicMock()
    el2 = MagicMock()
    el3 = MagicMock()
    el1.inner_text.return_value = "Listing 1"
    el2.inner_text.return_value = "Listing 2"
    el3.inner_text.return_value = "Listing 3"
    el1.get_attribute.return_value = None
    el2.get_attribute.return_value = None
    el3.get_attribute.return_value = None
    page.query_selector_all.return_value = [el1, el2, el3]
    results = extract_listings(page, ".listing")
    assert len(results) == 3


def test_dedup():
    page = MagicMock()
    page.url = "http://example.com"
    el1 = MagicMock()
    el2 = MagicMock()
    el1.inner_text.return_value = "Listing"
    el2.inner_text.return_value = "Listing"
    el1.get_attribute.return_value = None
    el2.get_attribute.return_value = None
    page.query_selector_all.return_value = [el1, el2]
    results = extract_listings(page, ".listing")
    assert len(results) == 1


def test_functional():
    page = MagicMock()
    page.url = "http://example.com"
    el1 = MagicMock()
    el1.inner_text.return_value = "Listing A"
    el1.get_attribute.return_value = None
    page.query_selector_all.return_value = [el1]
    results = extract_listings(page, ".listing")
    assert results[0]["text"] == "Listing A"


def test_fallback():
    page = MagicMock()
    page.url = "http://example.com"
    page.query_selector_all.return_value = []
    page.content.return_value = "<div class='listing'>Fallback</div>"
    results = extract_listings(page, ".listing")
    assert results[0]["text"] == "Fallback"


def test_no_listings():
    page = MagicMock()
    page.url = "http://example.com"
    page.query_selector_all.return_value = []
    page.content.return_value = ""
    results = extract_listings(page, ".listing")
    assert results == []
