import re
import time
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup


DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def fetch_html(url: str, timeout: int = 25) -> str:
    resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=timeout)
    resp.raise_for_status()
    return resp.text


def extract_listing_links(html: str, base_url: str) -> List[str]:
    soup = BeautifulSoup(html, "lxml")
    links = []
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        if "athome.lu" not in href and href.startswith("/"):
            href = base_url.rstrip("/") + href
        if is_listing_url(href):
            links.append(href.split("?")[0])
    unique = sorted(set(links))
    return unique


def is_listing_url(url: str) -> bool:
    return bool(re.search(r"/(buy|rent)/.+/id-\d+\.html$", url))


def parse_listing(html: str, url: str) -> Dict[str, Optional[str]]:
    soup = BeautifulSoup(html, "lxml")
    title = text_or_none(soup.find("h1")) or text_or_none(soup.find("title"))
    description = extract_description(soup)
    price = extract_price(soup)
    location = extract_location(soup)

    contact_email, contact_phone = extract_contacts(soup.get_text(" ", strip=True))
    contact_name = extract_contact_name(soup)

    return {
        "source": "athome",
        "url": url,
        "title": title,
        "price": price,
        "location": location,
        "description": description,
        "contact_name": contact_name,
        "contact_email": contact_email,
        "contact_phone": contact_phone,
        "scraped_at": int(time.time()),
    }


def extract_description(soup: BeautifulSoup) -> Optional[str]:
    meta = soup.find("meta", attrs={"name": "description"})
    if meta and meta.get("content"):
        return meta["content"].strip()
    for selector in ["section", "article", "div"]:
        block = soup.find(selector)
        if block:
            text = block.get_text(" ", strip=True)
            if len(text) > 120:
                return text[:2000]
    return None


def extract_price(soup: BeautifulSoup) -> Optional[str]:
    text = soup.get_text(" ", strip=True)
    match = re.search(r"(€\s?[\d\s,.]+)", text)
    if match:
        return match.group(1).replace(" ", "")
    return None


def extract_location(soup: BeautifulSoup) -> Optional[str]:
    breadcrumbs = soup.find("nav")
    if breadcrumbs:
        text = breadcrumbs.get_text(" ", strip=True)
        if text:
            return text[:140]
    return None


def extract_contact_name(soup: BeautifulSoup) -> Optional[str]:
    for label in soup.find_all(["h2", "h3", "span"], string=True):
        value = label.get_text(strip=True)
        if value and len(value) < 60 and "contact" in value.lower():
            return value
    return None


def extract_contacts(text: str) -> tuple[Optional[str], Optional[str]]:
    email_match = re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", text, re.I)
    phone_match = re.search(r"(\+?\d[\d\s().-]{7,}\d)", text)
    email = email_match.group(0) if email_match else None
    phone = phone_match.group(0) if phone_match else None
    return email, phone


def text_or_none(tag) -> Optional[str]:
    if not tag:
        return None
    text = tag.get_text(" ", strip=True)
    return text or None
