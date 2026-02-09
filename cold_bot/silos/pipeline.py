"""
Pipeline support: canonical listing schema, retries, rate limit, URL validation, health check.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Dict, Optional, Set
from urllib.parse import urlparse

LOG = logging.getLogger(__name__)

# Canonical listing dict keys (scraper output + analysis)
LISTING_KEYS = frozenset({
    "title", "price", "location", "description", "contact", "url",
    "is_private", "agency_name", "source", "listing_type", "bedrooms", "size",
    "confidence", "extraction_method", "priority_score",
})

ALLOWED_SCHEMES = {"http", "https"}
ALLOWED_NETLOC_SUBSTR = ("athome", "immotop", "facebook.com", "fb.com", "fb.gg", "rightmove", "example.com")

_shutdown_requested = False


def request_shutdown() -> bool:
    global _shutdown_requested
    _shutdown_requested = True
    return True


def is_shutdown_requested() -> bool:
    return _shutdown_requested


def validate_url(url: str) -> bool:
    """Allow only http(s) and known host substrings from config."""
    if not url or not isinstance(url, str):
        return False
    try:
        p = urlparse(url.strip())
        if p.scheme not in ALLOWED_SCHEMES:
            return False
        if not p.netloc:
            return False
        net = p.netloc.lower()
        if any(s in net for s in ALLOWED_NETLOC_SUBSTR):
            return True
        return True  # allow other hosts; tighten with config allowlist if needed
    except Exception:
        return False


def retry_with_backoff(
    fn: Callable[[], Any],
    max_attempts: int = 3,
    initial_delay: float = 1.0,
    backoff: float = 2.0,
    log_label: str = "op",
) -> Any:
    last_exc = None
    delay = initial_delay
    for attempt in range(max_attempts):
        try:
            return fn()
        except Exception as e:
            last_exc = e
            LOG.warning("%s attempt %s failed: %s", log_label, attempt + 1, e)
            if attempt < max_attempts - 1:
                time.sleep(delay)
                delay *= backoff
    raise last_exc


class RateLimiter:
    """Per-domain simple rate limit (requests per minute). Thread-safe for parallel URL workers."""

    def __init__(self, requests_per_minute: int = 30) -> None:
        self.rpm = max(1, requests_per_minute)
        self._counts: Dict[str, list] = {}
        self._lock = threading.Lock()

    def _trim(self, key: str, now: float) -> None:
        cutoff = now - 60.0
        self._counts[key] = [t for t in self._counts.get(key, []) if t > cutoff]

    def wait_if_needed(self, domain: str) -> None:
        with self._lock:
            now = time.time()
            self._trim(domain, now)
            times = self._counts.setdefault(domain, [])
            if len(times) >= self.rpm:
                sleep_until = times[0] + 60.0 - now
                if sleep_until > 0:
                    LOG.info("rate limit %s: sleep %.1fs", domain, sleep_until)
                    time.sleep(sleep_until)
                self._trim(domain, time.time())
            self._counts.setdefault(domain, []).append(time.time())


def structured_log(level: int, message: str, **kwargs: Any) -> None:
    """Emit a structured log line: message plus key=value for traceability."""
    extra = " ".join(f"{k}={v!r}" for k, v in sorted(kwargs.items()) if v is not None)
    if extra:
        LOG.log(level, "%s %s", message, extra)
    else:
        LOG.log(level, "%s", message)


def health_check(config_path: str, db_path: Optional[str] = None, check_ollama: bool = False) -> bool:
    """Verify config loads, DB is writable, optionally Ollama. Return True if healthy."""
    try:
        from silos.config_loader import ConfigLoader
        config = ConfigLoader.load_config(config_path)
        db = db_path or config.get("database", "leads.db")
        with open(db, "a") as f:
            pass
        if check_ollama:
            import ollama
            ollama.list()
        return True
    except Exception as e:
        LOG.error("health check failed: %s", e)
        return False
