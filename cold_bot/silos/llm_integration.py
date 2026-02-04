from typing import Dict, Optional

import os

import ollama
import httpx

from utils import parse_json_with_retry

def load_prompt(file: str) -> str:
    """Description.

    Args:
        file (type): desc.

    Returns:
        type: desc.

    Raises:
        exc: when.
    """
    prompts_dir = os.path.join(os.path.dirname(__file__), "..", "prompts")
    path = os.path.join(prompts_dir, file)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _call_xai(prompt: str, model: str) -> str:
    api_key = os.getenv("XAI_API_KEY")
    if not api_key:
        raise RuntimeError("XAI_API_KEY is not set")
    response = httpx.post(
        "https://api.x.ai/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "stream": False,
            "temperature": 0,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=30.0,
    )
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]["content"]


def _call_ollama(prompt: str, model: str, json_format: bool = True) -> str:
    response = ollama.chat(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        format="json" if json_format else None,
    )
    return response["message"]["content"]


def _call_json_with_retry(prompt: str, model: str, provider: str) -> Dict:
    if provider == "xai":
        raw = _call_xai(prompt, model)
        try:
            return parse_json_with_retry(raw, raw)
        except Exception:
            retry_prompt = prompt + "\nStrict JSON only."
            retry_raw = _call_xai(retry_prompt, model)
            return parse_json_with_retry(retry_raw, retry_raw)
    raw = _call_ollama(prompt, model, json_format=True)
    try:
        return parse_json_with_retry(raw, raw)
    except Exception:
        retry_prompt = prompt + "\nStrict JSON only."
        retry_raw = _call_ollama(retry_prompt, model, json_format=True)
        return parse_json_with_retry(retry_raw, retry_raw)


def classify_eligible(
    text: str,
    criteria: str,
    model: str,
    provider: str = "ollama",
) -> Dict:
    """Description.

    Args:
        text (type): desc.
        criteria (type): desc.
        model (type): desc.

    Returns:
        type: desc.

    Raises:
        exc: when.
    """
    if not model:
        model = "llama3"
    prompt = load_prompt("eligibility.txt").format(text=text, criteria=criteria)
    return _call_json_with_retry(prompt, model, provider)


def extract_contact(text: str, model: str, provider: str = "ollama") -> Dict:
    """Description.

    Args:
        text (type): desc.
        model (type): desc.

    Returns:
        type: desc.

    Raises:
        exc: when.
    """
    if not model:
        model = "llama3"
    prompt = load_prompt("extract_contact.txt").format(text=text)
    return _call_json_with_retry(prompt, model, provider)


def generate_proposal(
    summary: str,
    contact: str,
    model: str,
    from_email: str,
    provider: str = "ollama",
) -> Dict:
    """Description.

    Args:
        summary (type): desc.
        contact (type): desc.
        model (type): desc.
        from_email (type): desc.

    Returns:
        type: desc.

    Raises:
        exc: when.
    """
    if not model:
        model = "llama3"
    prompt = load_prompt("generate_proposal.txt").format(
        **{"from": from_email, "summary": summary, "contact": contact}
    )
    return _call_json_with_retry(prompt, model, provider)


def is_airbnb_viable(
    text: str,
    criteria: str,
    model: str,
    provider: str = "ollama",
) -> Dict:
    """Description.

    Args:
        text (type): desc.
        model (type): desc.

    Returns:
        type: desc.

    Raises:
        exc: when.
    """
    if not model:
        model = "llama3"
    prompt = load_prompt("airbnb_viability.txt").format(text=text, criteria=criteria)
    return _call_json_with_retry(prompt, model, provider)
