"""HTTP client for the Daylee backend."""

from __future__ import annotations

import httpx


class ApiError(Exception):
    pass


class CodeExpired(ApiError):
    pass


def _client(server_url: str) -> httpx.Client:
    return httpx.Client(base_url=server_url.rstrip("/"), timeout=30.0)


def request_device_code(server_url: str, device_label: str | None = None) -> dict:
    with _client(server_url) as client:
        resp = client.post(
            "/claude-code/devices/code",
            json={"device_label": device_label} if device_label else {},
        )
    if resp.status_code == 503:
        raise ApiError("Daylee backend has not enabled the integration.")
    resp.raise_for_status()
    return resp.json()


def poll_device_code(server_url: str, polling_token: str) -> dict:
    with _client(server_url) as client:
        resp = client.get(f"/claude-code/devices/code/{polling_token}")
    if resp.status_code == 404:
        raise CodeExpired("Code expired or invalid. Run `daylee login` again.")
    resp.raise_for_status()
    return resp.json()
