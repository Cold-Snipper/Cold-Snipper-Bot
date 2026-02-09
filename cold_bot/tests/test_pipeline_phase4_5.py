"""Tests for Phase 4 (Rightmove scraper, parallel) and Phase 5 (structured_log, priority_score).
Run from project root with venv: python -m unittest tests.test_pipeline_phase4_5 -v
"""
import logging
import unittest

try:
    from silos.pipeline import RateLimiter, structured_log, validate_url
    HAS_PIPELINE = True
except ImportError:
    HAS_PIPELINE = False

try:
    from silos.scraper import _infer_source_from_url, get_scraper_for_source
    HAS_SCRAPER = True
except ImportError:
    HAS_SCRAPER = False

try:
    from silos.analysis import compute_priority_score
    HAS_ANALYSIS = True
except ImportError:
    HAS_ANALYSIS = False


@unittest.skipUnless(HAS_SCRAPER and HAS_PIPELINE, "silos.scraper / pipeline not available")
class TestRightmoveScraper(unittest.TestCase):
    def test_infer_source_rightmove(self):
        self.assertEqual(_infer_source_from_url("https://www.rightmove.co.uk/property/123"), "rightmove")
        self.assertEqual(_infer_source_from_url("https://rightmove.co.uk/search"), "rightmove")

    def test_get_scraper_rightmove(self):
        config = {"database": "leads.db", "limits": {}}
        scraper = get_scraper_for_source(config, "rightmove")
        self.assertEqual(scraper.site_name, "rightmove")

    def test_validate_url_rightmove(self):
        self.assertTrue(validate_url("https://www.rightmove.co.uk/property/123"))


@unittest.skipUnless(HAS_ANALYSIS, "silos.analysis (ollama) not available")
class TestPriorityScore(unittest.TestCase):
    def test_score_range(self):
        s = compute_priority_score(viability_rating=10, is_private=True, has_contact=True, private_confidence=8)
        self.assertGreaterEqual(s, 0)
        self.assertLessEqual(s, 100)

    def test_score_components(self):
        s0 = compute_priority_score(0, False, False, 0)
        s1 = compute_priority_score(8, True, True, 7)
        self.assertGreater(s1, s0)


@unittest.skipUnless(HAS_PIPELINE, "silos.pipeline not available")
class TestStructuredLog(unittest.TestCase):
    def test_structured_log_no_raise(self):
        structured_log(logging.DEBUG, "test", listing_id="abc", url="http://example.com", duration_sec=1.2)


@unittest.skipUnless(HAS_PIPELINE, "silos.pipeline not available")
class TestRateLimiterThreadSafe(unittest.TestCase):
    def test_wait_if_needed(self):
        r = RateLimiter(requests_per_minute=60)
        r.wait_if_needed("example.com")
        r.wait_if_needed("example.com")


if __name__ == "__main__":
    unittest.main()
