"""Extract unique web URLs from Corobomail messages for crawler.py."""

import argparse
import email
from email import policy
from html.parser import HTMLParser
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit


QUERY = """
    SELECT DISTINCT m.id, m.raw_message_text
    FROM target_accounts ta
    JOIN messages m ON m.id = ta.message_id
    WHERE ta.cashout_method_id = %s
    ORDER BY m.id
    LIMIT %s
"""
URL_PATTERN = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)


def clean_url(value):
    """Keep absolute HTTP(S) links with a valid host and port."""
    value = value.strip()
    if any(char.isspace() or ord(char) < 32 for char in value):
        return None
    try:
        parsed = urlsplit(value)
        if parsed.scheme.lower() in {"http", "https"} and parsed.hostname:
            # Accessing port also validates malformed port numbers.
            parsed.port
            return value
    except ValueError:
        pass
    return None


def text_urls(text):
    for match in URL_PATTERN.finditer(text):
        value = match.group().rstrip(".,;:!?")
        for opening, closing in [("(", ")"), ("[", "]"), ("{", "}")]:
            while value.endswith(closing) and value.count(closing) > value.count(opening):
                value = value[:-1]
        url = clean_url(value)
        if url:
            yield url


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.urls = []
        self.hidden_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden_depth += 1
        if tag in {"a", "area"}:
            for name, value in attrs:
                if name == "href" and value:
                    url = clean_url(value)
                    if url:
                        self.urls.append(url)

    def handle_endtag(self, tag):
        if tag in {"script", "style"} and self.hidden_depth:
            self.hidden_depth -= 1

    def handle_data(self, data):
        if not self.hidden_depth:
            self.urls.extend(text_urls(data))


def extract_urls(raw_message):
    """Decode MIME bodies and extract links, preserving first-seen order."""
    if isinstance(raw_message, str):
        message = email.message_from_string(raw_message, policy=policy.default)
    elif isinstance(raw_message, bytes):
        message = email.message_from_bytes(raw_message, policy=policy.default)
    else:
        return []
    urls = []

    def body_parts(part):
        if part.get_content_disposition() == "attachment":
            return
        if part.is_multipart():
            for child in part.iter_parts():
                yield from body_parts(child)
        elif part.get_content_type() in {"text/plain", "text/html"}:
            yield part

    for part in body_parts(message):
        payload = part.get_payload(decode=True)
        if payload is None:
            continue
        charset = part.get_content_charset() or "utf-8"
        try:
            text = payload.decode(charset, errors="replace")
        except LookupError:
            text = payload.decode("utf-8", errors="replace")
        if part.get_content_type() == "text/html":
            parser = LinkParser()
            parser.feed(text)
            urls.extend(parser.urls)
        else:
            urls.extend(text_urls(text))
    return list(dict.fromkeys(urls))


def export_urls(connection, output, cashout_method_id=4, limit=15):
    """Stream query results rather than loading all messages into memory."""
    if limit < 1:
        raise ValueError("Message limit must be positive")
    seen = set()
    message_count = 0
    with connection.cursor(name="message_url_export") as cursor:
        cursor.itersize = 1000
        cursor.execute(QUERY, (cashout_method_id, limit))
        for message_id, raw_message in cursor:
            message_count += 1
            for url in extract_urls(raw_message):
                if url not in seen:
                    output.write(url + "\n")
                    seen.add(url)
    return message_count, len(seen)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("urls.txt"))
    parser.add_argument("--cashout-method-id", type=int, default=4)
    parser.add_argument("--limit", type=int, default=15, help="Maximum messages to select")
    args = parser.parse_args(argv)
    if args.limit < 1:
        parser.error("--limit must be positive")
    dsn = os.environ.get("COROBOMAIL_DSN")
    if not dsn:
        parser.error("Set the COROBOMAIL_DSN environment variable")
    try:
        import psycopg2
    except ImportError:
        parser.exit(1, "Install dependencies with: pip install -r requirements.txt\n")
    try:
        connection = psycopg2.connect(dsn=dsn)
        try:
            connection.set_session(readonly=True)
            with connection, args.output.open("w", encoding="utf-8") as output:
                messages, urls = export_urls(connection, output, args.cashout_method_id, args.limit)
        finally:
            connection.close()
    except psycopg2.Error:
        parser.exit(1, "Database operation failed; check connectivity and query permissions.\n")
    except OSError as exc:
        parser.exit(1, f"Could not write URL file: {exc}\n")
    print(f"Extracted {urls} unique URLs from {messages} messages into {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
