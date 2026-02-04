import os
from unittest.mock import patch

from silos.llm_integration import classify_eligible, extract_contact, generate_proposal, is_airbnb_viable


def test_classify():
    fake = {"message": {"content": '{"eligible": true}'}}
    with patch("silos.llm_integration.ollama.chat", return_value=fake):
        result = classify_eligible("text", "criteria", "model")
        assert result["eligible"] is True


def test_extract():
    fake = {"message": {"content": '{"email": "a@b.com"}'}}
    with patch("silos.llm_integration.ollama.chat", return_value=fake):
        result = extract_contact("email a@b.com", "model")
        assert result["email"] == "a@b.com"


def test_proposal():
    fake = {"message": {"content": '{"subject": "Subject:", "body": "Body"}'}}
    with patch("silos.llm_integration.ollama.chat", return_value=fake):
        result = generate_proposal("summary", "contact", "model", "from@example.com")
        assert "Subject:" in result["subject"]


def test_retry():
    bad = {"message": {"content": "not json"}}
    good = {"message": {"content": '{"eligible": true}'}}
    with patch("silos.llm_integration.ollama.chat", side_effect=[bad, good]):
        result = classify_eligible("text", "criteria", "model")
        assert result["eligible"] is True


def test_bad_contact():
    bad = {"message": {"content": "not json"}}
    good = {"message": {"content": '{"email": null, "phone": null}'}}
    with patch("silos.llm_integration.ollama.chat", side_effect=[bad, good]):
        result = extract_contact("no contact here", "model")
        assert result["email"] is None


def test_airbnb_viable():
    fake = {"message": {"content": '{"viable": true, "rating": 8}'}}
    with patch("silos.llm_integration.ollama.chat", return_value=fake):
        result = is_airbnb_viable("nice listing", "criteria", "model")
        assert result["viable"] is True


def test_functional():
    if not os.getenv("RUN_FUNCTIONAL"):
        return
    result = classify_eligible("Owner selling home FSBO", "FSBO", "llama3")
    assert "eligible" in result
