from __future__ import annotations

from typing import Any, Dict, List

from silos.email_sender import send_email


def send_all(
    contacts: Dict[str, Any],
    message: Dict[str, Any] | str,
    source: str,
    config: Dict[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    """
    Dispatch outreach across available channels.

    This is a stub implementation focused on email so we can
    unit-test the branching logic before wiring in Playwright
    and Facebook automation.
    """
    results: List[Dict[str, Any]] = []

    if isinstance(message, str):
        msg_email_body = message
        msg_subject = ""
    else:
        msg_email_body = message.get("email_body") or message.get("body") or ""
        msg_subject = message.get("subject") or ""

    emails = contacts.get("emails") or []
    if not emails and contacts.get("email"):
        emails = [contacts["email"]]
    if isinstance(emails, str):
        emails = [emails]

    dry_run = config.get("dry_run", True) if config else True
    if emails and config:
        email_cfg = config.get("email", {})
        db_path = config.get("database", "leads.db")
        max_per_hour = config.get("limits", {}).get("max_contacts_per_hour", 5)

        for addr in emails:
            if dry_run:
                print(f"[DRY RUN] Would send email to {addr}")
                results.append({"channel": "email", "to": addr, "source": source, "success": False, "reason": "dry_run"})
                continue
            ok = send_email(
                addr,
                msg_email_body,
                email_cfg.get("from", ""),
                email_cfg.get("app_password", ""),
                email_cfg.get("smtp_host", "smtp.gmail.com"),
                db_path,
                max_per_hour,
                subject=msg_subject or None,
            )
            results.append({"channel": "email", "to": addr, "source": source, "success": ok})
            if ok:
                from silos.email_sender import log_contact
                log_contact(db_path, addr, "success")

    # Stubs for other channels (WhatsApp, forms, FB)
    phones = contacts.get("phones") or contacts.get("phone") or []
    if isinstance(phones, str):
        phones = [phones]
    for ph in phones:
        results.append(
            {
                "channel": "whatsapp",
                "to": ph,
                "source": source,
                "success": False,
                "reason": "Not implemented yet",
            }
        )

    forms = contacts.get("forms") or []
    for form_url in forms:
        results.append(
            {
                "channel": "form",
                "to": form_url,
                "source": source,
                "success": False,
                "reason": "Not implemented yet",
            }
        )

    return results

