"""Read-only database selection and streamed crawler results for the dashboard."""
import argparse
import io
import json
import os
import sys

import requests

from crawler import analyze
from export_results import export_results
from extract_urls import export_urls
from tls_config import configure_https

MAX_MESSAGES = 1000


def connect_database():
    import psycopg2
    dsn = os.environ.get("COROBOMAIL_DSN")
    if not dsn:
        raise ValueError("Set COROBOMAIL_DSN in the terminal before starting the dashboard.")
    connection = psycopg2.connect(dsn, connect_timeout=10)
    connection.set_session(readonly=True)
    with connection.cursor() as cursor:
        cursor.execute("SET LOCAL statement_timeout = '30s'")
    return connection


def list_methods(connection):
    with connection.cursor() as cursor:
        cursor.execute("SELECT id, method FROM cashout_methods ORDER BY method, id")
        return [{"id": row[0], "method": row[1]} for row in cursor]


def emit(event):
    print(json.dumps(event), flush=True)


def scan_database(connection, method_id, limit, export_path=None):
    if not 1 <= limit <= MAX_MESSAGES:
        raise ValueError(f"Message limit must be between 1 and {MAX_MESSAGES}.")
    with connection.cursor() as cursor:
        cursor.execute("SELECT method FROM cashout_methods WHERE id = %s", (method_id,))
        row = cursor.fetchone()
        if row is None:
            raise ValueError("The selected cashout method no longer exists. Reload the list.")
    output = io.StringIO()
    messages, total = export_urls(connection, output, method_id, limit)
    # Release the read transaction before making any web requests.
    connection.rollback()
    emit({"event": "started", "messages": messages, "urls": total, "method": row[0]})
    failures = 0
    records = []
    for index, url in enumerate(output.getvalue().splitlines(), start=1):
        try:
            data = {"url": url, **analyze(url)}
        except (requests.RequestException, OSError, UnicodeError) as exc:
            failures += 1
            data = {"url": url, "error": f"{type(exc).__name__}: {exc}"}
        records.append(data)
        emit({"event": "result", "completed": index, "urls": total, "data": data})
    emit({"event": "completed", "messages": messages, "urls": total,
          "fetched": total - failures, "failed": failures})
    if export_path:
        params = {"cashout_method_id": method_id, "cashout_method": row[0],
                  "limit": limit, "messages": messages}
        try:
            path = export_results(export_path, "database", records, params)
            print(f"Report exported to {path}", file=sys.stderr)
        except OSError as exc:
            print(f"Could not write export file: {exc}", file=sys.stderr)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list-methods", action="store_true")
    parser.add_argument("--cashout-method-id", type=int)
    parser.add_argument("--limit", type=int, default=15)
    parser.add_argument("--export", metavar="PATH",
                        help="Also write a structured JSON report to PATH")
    args = parser.parse_args(argv)
    if not args.list_methods and (args.cashout_method_id is None or not 1 <= args.limit <= MAX_MESSAGES):
        parser.error(f"Provide --cashout-method-id and --limit between 1 and {MAX_MESSAGES}")
    connection = None
    try:
        configure_https()
        connection = connect_database()
        if args.list_methods:
            print(json.dumps(list_methods(connection)))
        else:
            scan_database(connection, args.cashout_method_id, args.limit, args.export)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except ImportError:
        print("Install requirements.txt in the Python environment used by the dashboard.", file=sys.stderr)
        return 1
    except Exception:
        # Database exceptions can include connection secrets or message content.
        print("Database operation failed. Check connectivity, credentials, and read access to cashout_methods, target_accounts, and messages.", file=sys.stderr)
        return 1
    finally:
        if connection is not None:
            connection.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
