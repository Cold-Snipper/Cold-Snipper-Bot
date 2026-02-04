import time
from typing import Optional

import yagmail


def send_email(
    to_email: str,
    subject: str,
    body: str,
    from_email: str,
    app_password: str,
    oauth2_file: Optional[str] = None,
    retries: int = 2,
) -> None:
    last_error = None
    for attempt in range(retries + 1):
        try:
            if oauth2_file:
                yag = yagmail.SMTP(from_email, oauth2_file=oauth2_file)
            else:
                yag = yagmail.SMTP(from_email, app_password)
            yag.send(to=to_email, subject=subject, contents=body)
            yag.close()
            return
        except Exception as exc:
            last_error = exc
            time.sleep(1 + attempt)
    raise RuntimeError(f"Email send failed: {last_error}")
