from __future__ import annotations

import hashlib
import re
import time
from typing import Any, Dict, Set

import ollama

from silos import logging as logging_silo
from utils import parse_json_with_retry


def deduplicated(text: str, db_path: str, session_set: Set[str]) -> bool:
    """Return True if this listing was already seen (in session or in DB)."""
    h = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if h in session_set:
        return True
    if logging_silo.seen_listing_hash(db_path, h):
        return True
    session_set.add(h)
    return False


def agent_private_check(text: str, config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Lightweight agent/private classifier.

    1. Fast keyword pre-filter.
    2. Fallback to a small local LLM via Ollama when ambiguous.
    """
    private_keywords = config.get(
        "private_keywords",
        ["private seller", "owner direct", "for sale by owner", "no agency", "no agent"],
    )
    agent_keywords = config.get(
        "agent_keywords",
        ["agency", "broker", "realtor", "estate agent", "fees included", "commission"],
    )

    text_lower = text.lower()

    if any(kw in text_lower for kw in private_keywords) and not any(
        kw in text_lower for kw in agent_keywords
    ):
        return {
            "is_private": True,
            "confidence": 9,
            "reason": "Matched private-seller keywords only",
        }

    if any(kw in text_lower for kw in agent_keywords):
        return {
            "is_private": False,
            "confidence": 9,
            "reason": "Matched agent/agency keywords",
        }

    # LLM fallback for ambiguous cases
    model = config.get("ollama_model") or "llama3.2"
    prompt = (
        "You are classifying real estate listings as PRIVATE SELLER or AGENT.\n"
        "Return strict JSON only.\n"
        'Fields: is_private (bool), confidence (0-10), reason (string).\n\n'
        f"Listing text:\n{text}\n"
    )

    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            resp = ollama.chat(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                format="json",
            )
            raw = resp["message"]["content"]
            parsed = parse_json_with_retry(raw, raw)
            # Normalise keys
            return {
                "is_private": bool(parsed.get("is_private", False)),
                "confidence": int(parsed.get("confidence", 0) or 0),
                "reason": parsed.get("reason", "LLM classification"),
            }
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            # simple exponential backoff: 1s, 2s, 4s
            time.sleep(2**attempt)

    return {
        "is_private": False,
        "confidence": 0,
        "reason": f"LLM classification failed: {last_exc}",
    }


def verify_qualifies(text: str) -> bool:
    """Re-check that listing still qualifies as private (keyword stub)."""
    text_lower = text.lower()
    if any(kw in text_lower for kw in ["private seller", "owner", "fsbo", "no agent"]):
        return True
    return True  # default allow


def extract_agent_details(text: str, config: Dict[str, Any]) -> Dict[str, Any]:
    """Extract agency name and related fields from listing text (regex + optional LLM)."""
    import re
    agency_name = "Extracted from text"
    title = (text.splitlines()[0][:80] if text else "").strip()
    price_match = re.search(r"[\$€]?\s*[\d,]+(?:\s*k|\s*K)?", text)
    price = price_match.group(0).strip() if price_match else ""
    location_match = re.search(r"\b(?:in|near|at)\s+([A-Za-z\s\-]+?)(?:\s*[\.\d]|\n|$)", text, re.IGNORECASE)
    location = location_match.group(1).strip() if location_match else ""
    url = ""
    contact_match = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
    contact = contact_match.group(0) if contact_match else ""
    if not contact:
        phone = re.search(r"\+?[\d\s\-\.]{10,}", text)
        contact = phone.group(0).strip() if phone else ""
    for kw in ["agency", "realty", "real estate", "broker"]:
        if kw in text.lower():
            m = re.search(rf"(?:{kw}[:\s]+)?([A-Za-z0-9\s&\.]+(?:{kw})?)", text, re.IGNORECASE)
            if m:
                agency_name = m.group(1).strip()[:80]
            break
    return {
        "agency_name": agency_name,
        "title": title,
        "price": price,
        "location": location,
        "url": url,
        "contact": contact,
        "reason": "Agent listing",
    }

