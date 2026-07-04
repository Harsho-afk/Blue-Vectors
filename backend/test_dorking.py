import unittest

from dorking import score_result


class ScoreDorkingResultTests(unittest.TestCase):
    def test_exact_email_in_snippet_is_high_confidence(self):
        result = score_result(
            {
                "title": "Team contact page",
                "snippet": "Questions can be sent to Person@Example.com.",
                "url": "https://example.org/contact",
            },
            "person@example.com",
            "email",
        )

        self.assertEqual(result["lead_score"], 60)
        self.assertEqual(result["lead_band"], "high")
        self.assertIn("exact_email_match", result["signals"])
        self.assertIn("exact_match_in_snippet", result["signals"])

    def test_exact_email_in_title_is_high_confidence(self):
        result = score_result(
            {"title": "person@example.com", "snippet": "", "url": "https://example.org"},
            "person@example.com",
            "email",
        )

        self.assertEqual(result["lead_score"], 65)
        self.assertEqual(result["lead_band"], "high")

    def test_percent_encoded_email_in_url_is_detected(self):
        result = score_result(
            {
                "title": "Directory",
                "snippet": "",
                "url": "https://example.org/user/person%40example.com",
            },
            "person@example.com",
            "email",
        )

        self.assertGreaterEqual(result["lead_score"], 70)
        self.assertEqual(result["lead_band"], "high")
        self.assertIn("identifier_in_url", result["signals"])

    def test_email_local_part_without_exact_email_remains_weak(self):
        result = score_result(
            {
                "title": "Person profile",
                "snippet": "A profile for person",
                "url": "https://example.org/person",
            },
            "person@example.com",
            "email",
        )

        self.assertEqual(result["lead_score"], 5)
        self.assertEqual(result["lead_band"], "low")


if __name__ == "__main__":
    unittest.main()
