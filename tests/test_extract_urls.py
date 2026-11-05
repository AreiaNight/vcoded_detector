from email.message import EmailMessage
import io
import unittest
from unittest.mock import MagicMock

from extract_urls import export_urls, extract_urls


class ExtractUrlsTests(unittest.TestCase):
    def test_multipart_decoding_links_entities_and_duplicates(self):
        message = EmailMessage()
        message.set_content(
            "Visit (https://example.com/path). https://example.com/wiki/Thing_(name)",
            cte="base64",
        )
        message.add_alternative(
            '<a href="https://example.com/path">Visit</a>'
            '<a href="https://other.example/?a=1&amp;b=2">Link</a>'
            '<u>https://visible.example/</u>'
            '<a href="mailto:person@example.com">Email</a>'
            '<a href="/relative">Relative</a>'
            '<style>https://style.example/</style>'
            '<script>https://script.example/</script>',
            subtype="html", charset="iso-8859-1", cte="quoted-printable",
        )
        message.add_attachment(
            "https://attachment.example/", subtype="plain", filename="note.txt"
        )
        self.assertEqual(extract_urls(message.as_bytes()), [
            "https://example.com/path",
            "https://example.com/wiki/Thing_(name)",
            "https://other.example/?a=1&b=2",
            "https://visible.example/",
        ])

    def test_unknown_charset_invalid_urls_and_missing_body(self):
        raw = (
            "Content-Type: text/plain; charset=unknown-charset\n\n"
            "https://valid.example/ https:// https://example.com:bad/ https://[bad/"
        )
        self.assertEqual(extract_urls(raw), ["https://valid.example/"])
        self.assertEqual(extract_urls(None), [])
        self.assertEqual(extract_urls("Subject: empty\n\n"), [])

    def test_attached_email_is_skipped(self):
        message = EmailMessage()
        message.set_content("https://body.example/")
        attached = EmailMessage()
        attached.set_content("https://attached.example/")
        message.add_attachment(attached)
        self.assertEqual(extract_urls(message.as_bytes()), ["https://body.example/"])

    def test_export_streams_rows_and_deduplicates_across_messages(self):
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.__iter__.return_value = iter([
            (1, "\nhttps://example.com/"),
            (2, "\nhttps://example.com/ https://other.example/"),
        ])
        output = io.StringIO()
        self.assertEqual(export_urls(connection, output, 7), (2, 2))
        self.assertEqual(output.getvalue(), "https://example.com/\nhttps://other.example/\n")
        self.assertEqual(cursor.execute.call_args.args[1], (7, 15))
        connection.cursor.assert_called_once_with(name="message_url_export")


if __name__ == "__main__":
    unittest.main()
