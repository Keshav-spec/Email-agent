"""
Tests for EmailConnector utility methods and MIME decoders.
"""

import unittest
from src.config import AgentConfig
from src.connector import EmailConnector


class TestEmailConnector(unittest.TestCase):
    def setUp(self):
        self.config = AgentConfig()
        self.connector = EmailConnector(self.config)

    def test_decode_header_plain(self):
        subject = "Regular Meeting Notice"
        decoded = EmailConnector.decode_header_value(subject)
        self.assertEqual(decoded, "Regular Meeting Notice")

    def test_decode_header_rfc2047(self):
        # RFC 2047 encoded =?utf-8?B?4pyoIFJlZ2lzdHJhdGlvbiBPcGVu?=
        encoded = "=?utf-8?B?4pyoIFJlZ2lzdHJhdGlvbiBPcGVu?="
        decoded = EmailConnector.decode_header_value(encoded)
        self.assertIn("Registration Open", decoded)

    def test_html_cleaning_and_link_extraction(self):
        html = """
        <html>
            <body>
                <p>Please register before Friday!</p>
                <a href="https://example.com/register">Click Here To Register</a>
                <script>console.log("ignore me");</script>
            </body>
        </html>
        """
        text, links = EmailConnector._clean_html(html)
        self.assertIn("Please register before Friday!", text)
        self.assertNotIn("console.log", text)
        self.assertTrue(any("https://example.com/register" in l for l in links))

    def test_has_deadline_indicators(self):
        text_with_deadline = "Reminder: Your project due date is tomorrow at 5 PM."
        text_without_deadline = "Thank you for your grocery store receipt. Have a nice day."

        self.assertTrue(EmailConnector.has_deadline_indicators(text_with_deadline))
        self.assertFalse(EmailConnector.has_deadline_indicators(text_without_deadline))


if __name__ == "__main__":
    unittest.main()
