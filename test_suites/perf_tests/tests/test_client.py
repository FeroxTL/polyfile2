from __future__ import annotations

from typing import Any

import httpx
import pytest

from polyfile_perf.client import PolyfileApiError, PolyfileClient
from polyfile_perf.config import TargetConfig
from polyfile_perf.metrics import RequestRecorder


def make_client(handler: Any, **kwargs: Any) -> PolyfileClient:
    target = TargetConfig(base_url="http://polyfile.test", api_key="pf_test_key")
    return PolyfileClient(target, transport=httpx.MockTransport(handler), **kwargs)


def test_requests_include_bearer_token() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"current": {"name": "root"}, "children": []})

    with make_client(handler) as client:
        client.list_nodes("/")

    assert seen[0].headers["Authorization"] == "Bearer pf_test_key"
    assert seen[0].url.params["path"] == "/"


def test_json_error_raises_polyfile_api_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "Invalid API key"})

    with make_client(handler) as client, pytest.raises(PolyfileApiError) as exc_info:
        client.dashboard_context()

    assert exc_info.value.status_code == 401
    assert "Invalid API key" in exc_info.value.body


def test_mkdir_and_touch_use_path_query_params() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"name": "node", "upload_url": "/upload/token/"})

    with make_client(handler) as client:
        client.mkdir("/folder")
        client.touch("/folder/file.txt")

    assert seen[0].method == "POST"
    assert seen[0].url.path == "/api/v1/fs-node/mkdir"
    assert seen[0].url.params["path"] == "/folder"
    assert seen[1].url.path == "/api/v1/fs-node/touch"
    assert seen[1].url.params["path"] == "/folder/file.txt"


def test_delete_node_uses_path_query_param() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(202, json={"job_id": "job-id", "status": "pending"})

    with make_client(handler) as client:
        result = client.delete_node("/folder")

    assert seen[0].method == "DELETE"
    assert seen[0].url.path == "/api/v1/fs-node/"
    assert seen[0].url.params["path"] == "/folder"
    assert result["job_id"] == "job-id"


def test_create_share_posts_to_path_url() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"id": "share-id"})

    with make_client(handler) as client:
        client.create_share("/folder", expires_at="2026-01-01T00:00:00Z")

    assert seen[0].method == "POST"
    assert seen[0].url.path == "/api/shares/create/folder"
    assert seen[0].url.params["expires_at"] == "2026-01-01T00:00:00Z"


def test_upload_posts_raw_body() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"size": len(request.content)})

    with make_client(handler) as client:
        result = client.upload("/upload/token/", b"hello")

    assert result["size"] == 5
    assert seen[0].headers["Content-Type"] == "application/octet-stream"


def test_wait_for_deletion_returns_terminal_state() -> None:
    statuses = iter(["pending", "running", "done"])

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": next(statuses)})

    with make_client(handler) as client:
        result = client.wait_for_deletion("job-id", timeout=5.0, interval=0.0)

    assert result["status"] == "done"


def test_wait_for_deletion_times_out() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "running"})

    with make_client(handler) as client, pytest.raises(TimeoutError):
        client.wait_for_deletion("job-id", timeout=0.0, interval=0.0)


def test_request_recorder_collects_samples() -> None:
    recorder = RequestRecorder()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True})

    with make_client(handler, on_request=recorder.record) as client:
        client.dashboard_context()

    samples = recorder.samples
    assert len(samples) == 1
    assert samples[0].method == "GET"
    assert samples[0].status_code == 200
    assert samples[0].ok is True

    summary = recorder.summary(duration_seconds=1.0)
    assert summary["requests"] == 1
    assert summary["errors"] == 0
    assert summary["requests_per_second"] == 1.0


def test_revoke_share_accepts_empty_204() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        return httpx.Response(204)

    with make_client(handler) as client:
        client.revoke_share("share-token")
