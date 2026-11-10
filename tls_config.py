"""Configure system certificate trust once at application startup.

Call from CLI entry points, not on import, so importing crawler.analyze does
not change TLS behavior in other applications. Verification remains enabled.
"""
_configured = False


def configure_https():
    global _configured
    if not _configured:
        import truststore
        truststore.inject_into_ssl()
        _configured = True
