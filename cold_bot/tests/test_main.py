from unittest.mock import patch

import main


def test_e2e_mock():
    with patch("main.ConfigLoader.load_config") as mock_config, patch(
        "main.init_browser"
    ) as mock_init, patch(
        "main.scroll_and_navigate"
    ) as mock_scroll, patch(
        "main.extract_listings"
    ) as mock_extract, patch(
        "main.classify_eligible"
    ) as mock_classify, patch(
        "main.extract_contact"
    ) as mock_contact, patch(
        "main.is_airbnb_viable"
    ) as mock_viable, patch(
        "main.send_email"
    ) as mock_send, patch(
        "main.log_contact"
    ) as mock_log, patch(
        "main.upsert_lead"
    ) as mock_upsert:
        mock_config.return_value = {
            "headless": True,
            "start_urls": ["http://example.com"],
            "limits": {"scroll_depth": 1, "delay_min": 1, "delay_max": 1, "cooldown_min": 1, "cooldown_max": 1},
            "selectors": {"listing": ".listing"},
            "criteria": "FSBO",
            "ollama_model": "model",
            "email": {"from": "a@b.com", "app_password": "pw", "smtp_host": "smtp"},
            "database": "test.db",
        }
        mock_init.return_value = (None, None, None)
        mock_extract.return_value = [{"text": "Listing"}]
        mock_classify.return_value = {"eligible": True}
        mock_contact.return_value = {"email": "test@example.com"}
        mock_viable.return_value = {"viable": True, "rating": 8}
        mock_send.return_value = True
        mock_scroll.side_effect = Exception("stop")

        # Run one iteration by breaking after first loop using exception
        try:
            main.main("config.yaml")
        except Exception:
            pass
