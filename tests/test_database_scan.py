import contextlib
import io
import json
import unittest
from unittest.mock import MagicMock, patch

import requests
import database_scan
from extract_urls import export_urls


class DatabaseScanTests(unittest.TestCase):
    def connection(self):
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = ("Wire transfer",)
        return connection

    def test_method_names_and_ids_from_database(self):
        connection = self.connection()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.__iter__.return_value = iter([(4, "Wire transfer"), (7, "Gift card")])
        self.assertEqual(database_scan.list_methods(connection), [
            {"id": 4, "method": "Wire transfer"}, {"id": 7, "method": "Gift card"}])

    def test_scan_streams_success_and_failure_and_selected_limit(self):
        connection = self.connection()
        def export(conn, output, method_id, limit):
            self.assertIs(conn, connection)
            self.assertEqual((method_id, limit), (7, 50))
            output.write("https://good.example/\nhttps://bad.example/\n")
            return 2, 2
        data = {"status": 200, "source": "view-source:https://good.example/", "total": 3, "results": []}
        with patch("database_scan.export_urls", side_effect=export), \
                patch("database_scan.analyze", side_effect=[data, requests.Timeout("timed out")]), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            database_scan.scan_database(connection, 7, 50)
        events = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual([e["event"] for e in events], ["started", "result", "result", "completed"])
        self.assertEqual(events[1]["data"]["total"], 3)
        self.assertIn("Timeout", events[2]["data"]["error"])
        self.assertEqual(events[-1]["failed"], 1)
        self.assertEqual(events[-1]["fetched"], 1)
        connection.rollback.assert_called_once()

    def test_empty_selection_completes(self):
        with patch("database_scan.export_urls", return_value=(0, 0)), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            database_scan.scan_database(self.connection(), 4, 15)
        events = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(events[-1]["urls"], 0)
        self.assertEqual(events[-1]["event"], "completed")

    def test_invalid_limit_and_unknown_method_do_not_scan(self):
        connection = self.connection()
        for limit in [0, -1, 1001]:
            with self.assertRaises(ValueError):
                database_scan.scan_database(connection, 4, limit)
        connection.cursor.return_value.__enter__.return_value.fetchone.return_value = None
        with self.assertRaises(ValueError):
            database_scan.scan_database(connection, 99, 10)

    def test_extractor_binds_limit_and_method(self):
        connection = self.connection()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.__iter__.return_value = iter([])
        export_urls(connection, io.StringIO(), cashout_method_id=7, limit=50)
        query, params = cursor.execute.call_args.args
        self.assertEqual(params, (7, 50))
        self.assertIn("LIMIT %s", query)

    def test_database_error_does_not_expose_connection_secrets(self):
        with patch("database_scan.connect_database", side_effect=Exception("password=secret")), \
                contextlib.redirect_stderr(io.StringIO()) as error:
            self.assertEqual(database_scan.main(["--list-methods"]), 1)
        self.assertNotIn("secret", error.getvalue())


if __name__ == "__main__":
    unittest.main()
