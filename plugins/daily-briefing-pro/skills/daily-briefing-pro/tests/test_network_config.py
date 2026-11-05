import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import network_config


class NetworkConfigTests(unittest.TestCase):
    def test_cloud_runtime_uses_environment_proxy(self):
        with patch.dict(os.environ, {"DAILY_BRIEFING_CLOUD": "1"}, clear=True):
            self.assertTrue(network_config.trust_env_proxy())
            self.assertEqual(network_config.curl_proxy_args(), [])

    def test_local_runtime_keeps_direct_connections(self):
        with patch.dict(
            os.environ,
            {
                "HTTP_PROXY": "http://127.0.0.1:7890",
                "HTTPS_PROXY": "http://127.0.0.1:7890",
            },
            clear=True,
        ):
            self.assertFalse(network_config.trust_env_proxy())
            self.assertEqual(network_config.curl_proxy_args(), ["--noproxy", "*"])

    def test_playwright_proxy_is_cloud_only(self):
        with patch.dict(
            os.environ,
            {
                "HTTP_PROXY": "http://proxy:8080",
                "NO_PROXY": "localhost,127.0.0.1",
            },
            clear=True,
        ):
            self.assertIsNone(network_config.playwright_proxy_settings())

        with patch.dict(
            os.environ,
            {
                "DAILY_BRIEFING_CLOUD": "1",
                "HTTP_PROXY": "http://proxy:8080",
                "HTTPS_PROXY": "http://secure-proxy:8080",
                "NO_PROXY": "localhost,127.0.0.1",
            },
            clear=True,
        ):
            self.assertEqual(
                network_config.playwright_proxy_settings(),
                {
                    "server": "http://secure-proxy:8080",
                    "bypass": "localhost,127.0.0.1",
                },
            )

    def test_playwright_launch_options_preserve_explicit_proxy(self):
        with patch.dict(
            os.environ,
            {
                "DAILY_BRIEFING_CLOUD": "1",
                "HTTP_PROXY": "http://proxy:8080",
            },
            clear=True,
        ):
            explicit = {"server": "http://explicit:9000"}
            options = network_config.playwright_launch_options(
                headless=True,
                proxy=explicit,
            )
            self.assertTrue(options["headless"])
            self.assertIs(options["proxy"], explicit)

    def test_httpx_kwargs_follow_network_policy(self):
        with patch.dict(os.environ, {"DAILY_BRIEFING_CLOUD": "1"}, clear=True):
            self.assertTrue(network_config.httpx_client_kwargs(timeout=10)["trust_env"])
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(network_config.httpx_client_kwargs(timeout=10)["trust_env"])


if __name__ == "__main__":
    unittest.main()
