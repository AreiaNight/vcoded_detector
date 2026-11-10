import unittest
from unittest.mock import patch
import tls_config


class TLSConfigTests(unittest.TestCase):
    def test_application_configures_native_trust_only_once(self):
        with patch.object(tls_config, "_configured", False), \
                patch("truststore.inject_into_ssl") as inject:
            tls_config.configure_https()
            tls_config.configure_https()
            inject.assert_called_once_with()
            self.assertTrue(tls_config._configured)
