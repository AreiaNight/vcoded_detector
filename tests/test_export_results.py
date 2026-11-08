import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import requests
import crawler
import database_scan
from export_results import build_report, export_results

OK = {"url": "https://a.example/", "status": 200, "source": "view-source:https://a.example/",
      "total": 3, "results": [{"word": "signal", "count": 2}, {"word": "✨", "count": 1}]}
BAD = {"url": "https://b.example/", "error": "boom"}


class ExportTests(unittest.TestCase):
    def test_report_structure_and_summary(self):
        report = build_report("web", [OK, BAD], {"url": "x"})
        self.assertEqual(report["scan_type"], "web")
        self.assertEqual(report["summary"], {"urls": 2, "fetched": 1, "failed": 1,
                                             "total_matches": 3, "urls_with_matches": 1,
                                             "signals": {"signal": 2, "✨": 1}})
        self.assertEqual(report["results"][0]["matches"], OK["results"])
        self.assertEqual(report["errors"], [{"url": "https://b.example/", "error": "boom"}])

    def test_writes_utf8_json_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = export_results(Path(d) / "out" / "r.json", "web", [OK])
            text = path.read_text(encoding="utf-8")
            self.assertIn("✨", text)
            self.assertEqual(json.loads(text)["summary"]["fetched"], 1)

    def test_crawler_export_flag_keeps_stdout_contract(self):
        data = {k: v for k, v in OK.items() if k != "url"}
        with tempfile.TemporaryDirectory() as d, \
                patch("crawler.analyze", return_value=data), \
                contextlib.redirect_stdout(io.StringIO()) as out, \
                contextlib.redirect_stderr(io.StringIO()):
            status = crawler.main(["https://a.example/", "--export", f"{d}/r.json"])
            report = json.loads(Path(d, "r.json").read_text(encoding="utf-8"))
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(out.getvalue()), data)
        self.assertEqual(report["results"][0]["url"], "https://a.example/")
        self.assertEqual(report["parameters"], {"url": "https://a.example/"})

    def test_database_export(self):
        connection = MagicMock()
        connection.cursor.return_value.__enter__.return_value.fetchone.return_value = ("Wire",)
        def export(conn, output, method_id, limit):
            output.write("https://a.example/\nhttps://b.example/\n")
            return 2, 2
        data = {k: v for k, v in OK.items() if k != "url"}
        with tempfile.TemporaryDirectory() as d, \
                patch("database_scan.export_urls", side_effect=export), \
                patch("database_scan.analyze", side_effect=[data, requests.Timeout("t")]), \
                contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()):
            database_scan.scan_database(connection, 7, 5, f"{d}/db.json")
            report = json.loads(Path(d, "db.json").read_text(encoding="utf-8"))
        self.assertEqual(report["scan_type"], "database")
        self.assertEqual(report["parameters"]["cashout_method"], "Wire")
        self.assertEqual(report["summary"]["failed"], 1)


if __name__ == "__main__":
    unittest.main()
