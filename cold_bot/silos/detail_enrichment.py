"""
Visit a listing detail page and extract contact (name, email, phone), agency vs private, location.
Focused on private (non-agent) sellers; aggressive email/phone extraction including click-to-reveal.
"""
from __future__ import annotations

import re
import time
from typing import Any, Dict, List

try:
    from playwright.sync_api import Page
except Exception:
    Page = None

# Private seller indicators (non-agent) – prioritize these
PRIVATE_PATTERNS = [
    r"contact\s+(?:the\s+)?owner",
    r"private\s+seller",
    r"particulier(?:\s+only)?",
    r"owner\s+direct",
    r"for\s+sale\s+by\s+owner",
    r"no\s+agent",
    r"vend\s+particulier",
    r"propriétaire",
    r"vendeur\s+particulier",
    r"between\s+private\s+parties",
    r"no\s+agency",
    r"sans\s+intermédiaire",
    r"direct\s+from\s+owner",
    r"fsbo",
]
# Agency indicators – treat as agent listing
AGENCY_PATTERNS = [
    r"contact\s+(?:the\s+)?(?:agency|agent)",
    r"real\s+estate\s+agency",
    r"agence\s+immobilière",
    r"listing\s+agent",
    r"broker",
    r"référence\s+agent",
    r"agency\s+name",
    r"agence\s*:",
    r"contact\s+agent",
    r"agent\s+commercial",
]

# --- Per-site contact reveal (Luxembourg). See docs/CONTACT_REVEAL_BY_COUNTRY.md for discovery process. ---
# atHome: "Voir les coordonnées" → contact card with Tél. +352. Immotop: "Afficher le téléphone" → phone pops up.
# Nextimmo / Bingo / PropertyWeb / Wortimmo: try common FR/EN reveal texts below.

# Site-specific reveal texts (try in order when source/url matches)
REVEAL_BY_SOURCE: Dict[str, List[str]] = {
    "athome": [
        "Voir les coordonnées", "Voir les coordonnées de l'annonceur", "Afficher les coordonnées",
        "Voir le numéro", "Voir le téléphone",
    ],
    "immotop": [
        "Afficher le téléphone", "Afficher le numéro", "Voir le téléphone",
    ],
    "nextimmo": [
        "Show contact", "Contact", "Voir le numéro", "Display phone",
        "Contact agent", "Contacter",
    ],
    "bingo": [
        "Contact", "Contacter", "Show phone", "Voir le numéro",
        "Contact agency", "Contact agent",
    ],
    "propertyweb": [
        "Contact", "Contact agent", "Contacter", "Show contact",
    ],
    "wortimmo": [
        "Contacter", "Email", "Voir détails", "Contact",
        "Voir le numéro", "Afficher le téléphone",
    ],
}

REVEAL_COORDONNEES = [
    "Afficher le téléphone", "Voir les coordonnées", "Voir les coordonnées de l'annonceur",
    "Afficher les coordonnées", "Voir le numéro", "Voir le téléphone",
    "Contacter", "Show contact", "Contact",
]
REVEAL_CONTACT_BUTTONS = [
    "Afficher le téléphone", "Voir les coordonnées", "Afficher les coordonnées",
    "Voir le numéro", "Show phone", "Voir le téléphone", "Display contact",
    "Contacter", "Contact", "Voir contact", "Afficher le numéro",
]
CONTACT_OVERLAY_SELECTORS = [
    "[role='dialog']", "[class*='modal']", "[class*='overlay']", "[class*='drawer']",
    "[class*='popup']", "[class*='contact-card']", "[class*='agency-card']",
    "[class*='coord']", ".contact-info", "[data-testid*='contact']",
]


def _get_text(page: Page, selector: str, max_len: int = 2000) -> str:
    try:
        el = page.query_selector(selector)
        if el:
            return (el.inner_text() or "").strip()[:max_len]
    except Exception:
        pass
    return ""


def _get_full_body_text(page: Page) -> str:
    """Full body text for email/phone regex (no 500-char truncation)."""
    try:
        return (page.evaluate("() => document.body ? document.body.innerText : ''") or "")[:15000]
    except Exception:
        pass
    return _get_text(page, "body", 15000)


def _get_attr(page: Page, selector: str, attr: str) -> str:
    try:
        el = page.query_selector(selector)
        if el:
            return (el.get_attribute(attr) or "").strip()
    except Exception:
        pass
    return ""


def _first_match(text: str, patterns: list) -> bool:
    if not text:
        return False
    lower = text.lower()
    for pat in patterns:
        if re.search(pat, lower, re.IGNORECASE):
            return True
    return False


def enrich_listing_detail(
    page: Page,
    url: str,
    source: str,
    *,
    timeout_ms: int = 15_000,
    accept_consent_fn=None,
) -> Dict[str, Any]:
    """
    Navigate to listing URL and extract contact_name, contact_email, contact_phone,
    description (if long), is_private, agency_name. Returns dict to merge into lead.
    """
    out = {
        "contact_name": "",
        "contact_email": "",
        "contact_phone": "",
        "description": "",
        "is_private": None,
        "agency_name": "",
        "location": "",
    }
    if not page or not url:
        return out
    try:
        page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
        time.sleep(0.4)
        if accept_consent_fn:
            try:
                accept_consent_fn(page)
            except Exception:
                pass
        time.sleep(0.3)
        # atHome: "Voir les coordonnées". Immotop: "Afficher le téléphone". Click so phone/contact pops up.
        def _click_reveal(text: str, wait_after: float = 1.2) -> bool:
            try:
                loc = page.locator(
                    f"a:has-text('{text}'), button:has-text('{text}'), [role='button']:has-text('{text}'), "
                    f"[class*='contact']:has-text('{text}'), [class*='coord']:has-text('{text}'), "
                    f"[class*='phone']:has-text('{text}'), [class*='tel']:has-text('{text}')"
                ).first
                if loc.count() > 0:
                    loc.scroll_into_view_if_needed(timeout=2000)
                    if loc.is_visible():
                        loc.click()
                        time.sleep(wait_after)
                        return True
            except Exception:
                pass
            return False

        # Per-site: try this source's reveal texts first (see REVEAL_BY_SOURCE and docs/CONTACT_REVEAL_BY_COUNTRY.md)
        source_clicked = False
        site_sources = [s for s in REVEAL_BY_SOURCE.keys() if s in (source or "") or s in url.lower()]
        for site in site_sources:
            for t in REVEAL_BY_SOURCE.get(site, []):
                if _click_reveal(t, wait_after=1.5 if site in ("immotop", "athome") else 1.2):
                    source_clicked = True
                    break
            if source_clicked:
                break
        # Fallback: generic LU reveal texts
        if not source_clicked:
            for btn_text in REVEAL_COORDONNEES:
                if _click_reveal(btn_text, wait_after=1.2):
                    break
        # If still no tel link visible, try other reveal buttons
        try:
            has_tel = len(page.query_selector_all('a[href^="tel:"]')) > 0
        except Exception:
            has_tel = False
        if not has_tel:
            pre = _get_full_body_text(page)[:8000]
            if "Tél." not in pre and "+352" not in pre:
                for btn_text in REVEAL_CONTACT_BUTTONS:
                    if btn_text in REVEAL_COORDONNEES or btn_text in ("Afficher le téléphone", "Afficher le numéro", "Voir le téléphone"):
                        continue
                    if _click_reveal(btn_text, wait_after=0.8):
                        break
        # Wait for possible async reveal (tel: link or "Tél." text)
        try:
            page.wait_for_selector('a[href^="tel:"]', timeout=2500)
        except Exception:
            pass
        time.sleep(0.4)

        body_text = _get_full_body_text(page)
        # Also get text from overlay/modal (contact card that popped out)
        overlay_text = ""
        for sel in CONTACT_OVERLAY_SELECTORS:
            overlay_text += _get_text(page, sel, 4000) + " "
        if overlay_text:
            body_text = overlay_text + " " + body_text
        body_lower = body_text.lower()

        # Email: mailto: links first, then regex over full page and contact sections
        try:
            for a in page.query_selector_all('a[href^="mailto:"]'):
                href = (a.get_attribute("href") or "").strip()
                if href.startswith("mailto:"):
                    email = href.replace("mailto:", "").split("?")[0].strip()
                    if "@" in email and len(email) < 120 and "example" not in email.lower():
                        out["contact_email"] = email
                        break
        except Exception:
            pass
        if not out["contact_email"]:
            for blob in [body_text, _get_text(page, "[class*='contact']", 3000), _get_text(page, "footer", 2000), _get_text(page, "[class*='sidebar']", 3000)]:
                if not blob:
                    continue
                emails = re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", blob)
                for e in emails:
                    if "example" in e.lower() or "domain" in e.lower() or len(e) > 80:
                        continue
                    out["contact_email"] = e
                    break
                if out["contact_email"]:
                    break

        # Phone: tel: links first, then regex (Luxembourg +352, French 06/07, international +)
        try:
            for a in page.query_selector_all('a[href^="tel:"]'):
                href = (a.get_attribute("href") or "").strip()
                if href.startswith("tel:"):
                    raw = href.replace("tel:", "").strip()
                    digits = re.sub(r"\D", "", raw)
                    if len(digits) >= 8:
                        out["contact_phone"] = raw[:30]
                        break
        except Exception:
            pass
        if not out["contact_phone"]:
            # Luxembourg atHome-style: "Tél. +35227869616" (label then number)
            tel_label = re.search(r"Tél\.?\s*[:\s]*(\+?\d[\d\s.-]{7,})", body_text, re.IGNORECASE)
            if tel_label:
                out["contact_phone"] = tel_label.group(1).strip()[:30]
            # Match +352..., 00352..., 06/07 (FR), 0x xx xx xx (LU/FR style)
            phone_pats = [
                r"\+\d{2,3}[\s.-]?\d{2,4}[\s.-]?\d{2,4}[\s.-]?\d{2,4}",
                r"00\d{2,3}[\s.-]?\d{2,4}[\s.-]?\d{2,4}[\s.-]?\d{2,4}",
                r"0[67][\s.-]?\d{2}[\s.-]?\d{2}[\s.-]?\d{2}[\s.-]?\d{2}",
                r"\(\d{2,3}\)[\s.-]?\d{2,4}[\s.-]?\d{2,4}",
                r"\d{3}[\s.-]\d{2}[\s.-]\d{2}[\s.-]\d{2}[\s.-]\d{2}",
            ]
            if not out["contact_phone"]:
                for blob in [body_text, _get_text(page, "[class*='contact']", 3000), _get_text(page, "footer", 2000)]:
                    if not blob:
                        continue
                    for pat in phone_pats:
                        m = re.search(pat, blob)
                        if m:
                            cand = m.group(0).strip()
                            if len(re.sub(r"\D", "", cand)) >= 8:
                                out["contact_phone"] = cand[:30]
                                break
                    if out["contact_phone"]:
                        break

        # Contact name / agency: common selectors
        for sel in [
            "[class*='contact-name']",
            "[class*='agent-name']",
            "[class*='agency-name']",
            "[class*='owner-name']",
            "[data-testid*='contact']",
            ".contact h2", ".contact h3",
            "[class*='contact'] h2", "[class*='contact'] h3",
            "[class*='agent'] h2", "[class*='agent'] h3",
            ".listing-agent", ".agent-name",
        ]:
            t = _get_text(page, sel)
            if t and len(t) > 1 and len(t) < 100 and not t.startswith("http"):
                if "agency" in sel or "agent" in sel:
                    if not out["agency_name"]:
                        out["agency_name"] = t
                elif not out["contact_name"]:
                    out["contact_name"] = t
                if out["contact_name"] and out["agency_name"]:
                    break

        # Agency vs private from page text
        if _first_match(body_text, PRIVATE_PATTERNS) and not _first_match(body_text, AGENCY_PATTERNS):
            out["is_private"] = True
        elif _first_match(body_text, AGENCY_PATTERNS):
            out["is_private"] = False
            if not out["agency_name"]:
                for pat in [r"(?:agency|agence)\s*[:\s]+([A-Za-z0-9\s&'-]{2,60})", r"([A-Za-z0-9\s&'-]+(?:immobilier|real estate|agency))"]:
                    m = re.search(pat, body_text, re.IGNORECASE)
                    if m:
                        out["agency_name"] = m.group(1).strip()[:80]
                        break

        # Location: often in breadcrumb or address block
        for sel in ["[class*='breadcrumb']", "[class*='address']", "[class*='location']", "[itemprop='address']", "address"]:
            t = _get_text(page, sel)
            if t and len(t) > 3 and len(t) < 200:
                out["location"] = t
                break

        # Description: meta or first long paragraph
        desc = _get_attr(page, 'meta[name="description"]', "content")
        if desc and len(desc) > 50:
            out["description"] = desc[:2000]
        if not out["description"]:
            t = _get_text(page, "article, [class*='description'], [class*='content']")
            if len(t) > 100:
                out["description"] = t[:2000]

    except Exception:
        pass
    return out
