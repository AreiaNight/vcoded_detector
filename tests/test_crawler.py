import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import requests
import crawler


class CrawlerTests(unittest.TestCase):
    def test_dashboard_json_contract_and_emoji_counts(self):
        response = Mock(text="SIGNAL signal ✨", status_code=200, headers={})
        with patch("crawler.requests.get", return_value=response) as get, \
                patch("crawler.load_signals", return_value=["signal", "✨", "absent"]), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            status = crawler.main(["https://example.com"])
        self.assertEqual(status, 0)
        result = json.loads(output.getvalue())
        self.assertEqual(result.pop("assessment")["score"], 1)
        self.assertEqual(result, {
            "status": 200, "source": "view-source:https://example.com", "total": 3,
            "results": [{"word": "signal", "count": 2}, {"word": "✨", "count": 1}],
        })
        self.assertEqual(response.encoding, "utf-8")
        get.assert_called_once_with("https://example.com", timeout=10)

    def test_wordlist_deduplicates_signals(self):
        with patch.object(Path, "read_text", return_value="Signal\nsignal\n\n✨\n"):
            self.assertEqual(crawler.load_signals(), ["signal", "✨"])

    def test_batch_continues_after_failure_and_skips_duplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            urls = Path(directory) / "urls.txt"
            urls.write_text("https://bad.example/\n\nhttps://good.example/\nhttps://good.example/\n")
            data = {"status": 200, "source": "view-source:https://good.example/",
                    "total": 1, "results": [{"word": "signal", "count": 1}]}
            with patch("crawler.analyze", side_effect=[requests.Timeout(), data]) as analyze, \
                    contextlib.redirect_stdout(io.StringIO()) as output, \
                    contextlib.redirect_stderr(io.StringIO()) as errors:
                status = crawler.main(["--urls-file", str(urls)])
            self.assertEqual(status, 1)
            self.assertEqual(analyze.call_count, 2)
            records = json.loads(output.getvalue())
            self.assertEqual(records[0], {"url": "https://bad.example/",
                                          "error": "The page took too long to respond"})
            self.assertEqual(records[1], {"url": "https://good.example/", **data})
            self.assertIn("Failed to scan https://bad.example/", errors.getvalue())

    def test_single_failure_goes_to_stderr_without_invalid_json(self):
        with patch("crawler.analyze", side_effect=requests.ConnectionError()), \
                contextlib.redirect_stdout(io.StringIO()) as output, \
                contextlib.redirect_stderr(io.StringIO()) as errors:
            status = crawler.main(["--url", "https://bad.example/"])
        self.assertEqual(status, 1)
        self.assertEqual(output.getvalue(), "")
        self.assertIn("Could not connect", errors.getvalue())

    def test_http_error_status_preserved_for_dashboard(self):
        response = Mock(text="not found", status_code=404,
                        headers={"content-type": "text/html; charset=utf-8"})
        with patch("crawler.requests.get", return_value=response), \
                patch("crawler.load_signals", return_value=["signal"]):
            self.assertEqual(crawler.analyze("https://example.com/missing")["status"], 404)

    def test_ssl_and_connection_errors_keep_diagnostic_details(self):
        cases = [
            (requests.exceptions.SSLError("certificate verify failed"),
             "TLS/SSL error: certificate verify failed"),
            (requests.ConnectionError("Name resolution failed"),
             "Could not connect to the page: Name resolution failed"),
        ]
        for exception, expected in cases:
            with self.subTest(error=expected), \
                    patch("crawler.analyze", side_effect=exception), \
                    contextlib.redirect_stdout(io.StringIO()) as output, \
                    contextlib.redirect_stderr(io.StringIO()) as errors:
                status = crawler.main(["--url", "https://bad.example/"])
            self.assertEqual(status, 1)
            self.assertEqual(output.getvalue(), "")
            self.assertIn(expected, errors.getvalue())

    def test_missing_input_returns_usage_error(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            crawler.main([])
        self.assertEqual(error.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
