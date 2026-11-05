"""Network transport policy shared by collectors.

Codex Cloud supplies outbound access through HTTP(S)_PROXY. Collectors that
silently disable environment proxy discovery fail there, while local runs keep
their existing direct-connection behaviour.
"""

from __future__ import annotations

import os


_TRUE_VALUES = {"1", "true", "yes", "on"}


def is_cloud_runtime() -> bool:
    return os.environ.get("DAILY_BRIEFING_CLOUD", "").strip().lower() in _TRUE_VALUES


def trust_env_proxy() -> bool:
    """Whether HTTP libraries should read proxy settings from the environment."""
    return is_cloud_runtime()


def create_requests_session():
    import requests

    session = requests.Session()
    session.trust_env = trust_env_proxy()
    return session


def httpx_client_kwargs(**kwargs) -> dict:
    kwargs.setdefault("trust_env", trust_env_proxy())
    return kwargs


def playwright_proxy_settings() -> dict | None:
    if not trust_env_proxy():
        return None
    server = (
        os.environ.get("HTTPS_PROXY")
        or os.environ.get("https_proxy")
        or os.environ.get("HTTP_PROXY")
        or os.environ.get("http_proxy")
        or ""
    ).strip()
    if not server:
        return None
    settings = {"server": server}
    bypass = (
        os.environ.get("NO_PROXY")
        or os.environ.get("no_proxy")
        or ""
    ).strip()
    if bypass:
        settings["bypass"] = bypass
    return settings


def playwright_launch_options(**kwargs) -> dict:
    options = dict(kwargs)
    if "proxy" not in options:
        proxy = playwright_proxy_settings()
        if proxy:
            options["proxy"] = proxy
    return options


def curl_proxy_args() -> list[str]:
    """Keep the historical local bypass while allowing the Cloud proxy."""
    return [] if trust_env_proxy() else ["--noproxy", "*"]
