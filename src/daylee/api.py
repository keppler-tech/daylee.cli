"""HTTP client for the Daylee backend."""

from __future__ import annotations

import hashlib
import hmac
import json

import httpx


class ApiError(Exception):
    pass


class CodeExpired(ApiError):
    pass


class DeviceUnknown(ApiError):
    pass


class WorkspaceRemoved(ApiError):
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
        raise ApiError("Daylee backend has not enabled the Claude Code integration.")
    resp.raise_for_status()
    return resp.json()


def poll_device_code(server_url: str, polling_token: str) -> dict:
    with _client(server_url) as client:
        resp = client.get(f"/claude-code/devices/code/{polling_token}")
    if resp.status_code == 404:
        raise CodeExpired("Code expired or invalid. Run `daylee login` again.")
    resp.raise_for_status()
    return resp.json()


def post_events(
    server_url: str,
    device_token: str,
    device_id: str,
    events: list[dict],
) -> dict:
    body = json.dumps({"device_id": device_id, "events": events}, separators=(",", ":")).encode("utf-8")
    signature = "sha256=" + hmac.new(device_token.encode(), body, hashlib.sha256).hexdigest()
    headers = {
        "Authorization": f"Bearer {device_token}",
        "X-Daylee-Signature": signature,
        "Content-Type": "application/json",
    }
    with _client(server_url) as client:
        resp = client.post("/claude-code/events", content=body, headers=headers)
    if resp.status_code == 401:
        raise ApiError("Authentication failed. Try `daylee login` again.")
    if resp.status_code == 403:
        raise DeviceUnknown("This device is not recognized by the Daylee backend.")
    if resp.status_code == 410:
        raise WorkspaceRemoved("This workspace's Claude Code install has been removed.")
    if resp.status_code == 503:
        raise ApiError("Daylee backend has not enabled the Claude Code integration.")
    resp.raise_for_status()
    return resp.json()
