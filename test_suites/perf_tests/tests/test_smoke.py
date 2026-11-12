from __future__ import annotations

from typing import Any

import httpx

from polyfile_perf.client import PolyfileClient
from polyfile_perf.config import TargetConfig
from polyfile_perf.smoke import run_smoke_flow

SHARE_ID = "33333333-3333-3333-3333-333333333333"
JOB_ID = "44444444-4444-4444-4444-444444444444"


def make_handler(calls: list[tuple[str, str]], *, fail_upload: bool = False) -> Any:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        method = request.method
        calls.append((method, path))

        if path == "/dashboard-context/":
            return httpx.Response(200, json={"sidebar_urls": []})
        if path == "/api/v1/fs-node/":
            if method == "DELETE":
                return httpx.Response(202, json={"job_id": JOB_ID, "status": "pending"})
            if request.url.params.get("path") == "/":
                return httpx.Response(200, json={"current": {}, "children": []})
            return httpx.Response(
                200,
                json={
                    "current": {"name": "perf-smoke"},
                    "children": [{"name": "payload.bin"}],
                },
            )
        if path == "/api/v1/fs-node/mkdir":
            return httpx.Response(200, json={"name": "perf-smoke", "type": "directory"})
        if path == "/api/v1/fs-node/touch":
            return httpx.Response(
                200,
                json={"name": "payload.bin", "type": "file", "upload_url": "/upload/token/"},
            )
        if path == "/upload/token/":
            if fail_upload:
                return httpx.Response(500, json={"detail": "upload failed"})
            return httpx.Response(200, json={"size": len(request.content)})
        if path.startswith("/api/shares/create"):
            return httpx.Response(200, json={"id": SHARE_ID})
        if path == f"/api/shares/detail/{SHARE_ID}/":
            return httpx.Response(200, json={"current": {"name": "perf-smoke"}, "children": []})
        if path == f"/api/shares/{SHARE_ID}/revoke":
            return httpx.Response(204)
        if path == f"/api/v1/fs-node/deletion-jobs/{JOB_ID}/":
            return httpx.Response(200, json={"status": "done"})
        return httpx.Response(404, json={"detail": f"unexpected {method} {path}"})

    return handler


def make_client(handler: Any) -> PolyfileClient:
    target = TargetConfig(base_url="http://polyfile.test", api_key="pf_test_key")
    return PolyfileClient(target, transport=httpx.MockTransport(handler))


def test_smoke_flow_completes_and_cleans_up() -> None:
    calls: list[tuple[str, str]] = []

    with make_client(make_handler(calls)) as client:
        result = run_smoke_flow(client, payload_size=512, delete_timeout=1.0)

    assert result.ok, [step for step in result.steps if not step.ok]
    assert [step.name for step in result.steps] == [
        "dashboard-context",
        "list-root",
        "mkdir",
        "touch",
        "upload",
        "list-directory",
        "share-create",
        "share-detail",
        "share-revoke",
        "delete-directory",
        "wait-deletion",
    ]
    assert ("DELETE", "/api/v1/fs-node/") in calls
    assert ("POST", f"/api/shares/{SHARE_ID}/revoke") in calls
    assert any(method == "POST" and path.startswith("/api/shares/create/") for method, path in calls)


def test_smoke_flow_records_failure_and_still_cleans_up() -> None:
    calls: list[tuple[str, str]] = []

    with make_client(make_handler(calls, fail_upload=True)) as client:
        result = run_smoke_flow(client, payload_size=16, delete_timeout=1.0)

    assert not result.ok
    assert [step.name for step in result.failures] == ["upload"]
    assert ("DELETE", "/api/v1/fs-node/") in calls
