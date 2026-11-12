"""Thin HTTP client for Polyfile's JSON API.

The client is deliberately small and synchronous: locust scenarios use their own
session, while the smoke runner uses this client. Both authenticate with the
same ``pf_...`` API key.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any, Self
from urllib.parse import quote

import httpx

from polyfile_perf.config import TargetConfig
from polyfile_perf.metrics import RequestSample

REQUEST_HOOK = Callable[[RequestSample], None]


class PolyfileApiError(RuntimeError):
    """Raised when Polyfile returns an HTTP error or an unexpected payload."""

    def __init__(
        self,
        method: str,
        url: str,
        status_code: int,
        body: str = "",
    ) -> None:
        self.method = method
        self.url = url
        self.status_code = status_code
        self.body = body
        snippet = body[:500].replace("\n", " ")
        super().__init__(f"{method} {url} -> {status_code}: {snippet}")


class PolyfileClient:
    """Synchronous Polyfile API client with optional request recording."""

    def __init__(
        self,
        target: TargetConfig,
        *,
        transport: httpx.BaseTransport | None = None,
        on_request: REQUEST_HOOK | None = None,
    ) -> None:
        self._target = target
        self._on_request = on_request
        self._client = httpx.Client(
            base_url=target.normalized_base_url(),
            headers=self._default_headers(target.resolve_api_key()),
            timeout=target.timeout,
            verify=target.verify_tls,
            transport=transport,
            follow_redirects=False,
        )

    @staticmethod
    def _default_headers(api_key: str | None) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

    def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        self._client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # -- low-level helpers -------------------------------------------------

    def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        started = time.monotonic()
        status_code = 0
        try:
            response = self._client.request(method, url, **kwargs)
            status_code = response.status_code
        except httpx.HTTPError:
            self._record(method, url, 0, started)
            raise
        self._record(method, url, status_code, started)
        if status_code >= 400:
            raise PolyfileApiError(method, str(response.request.url), status_code, response.text)
        return response

    def _record(self, method: str, url: str, status_code: int, started: float) -> None:
        if self._on_request is None:
            return
        self._on_request(
            RequestSample(
                timestamp=time.time(),
                method=method,
                path=url,
                status_code=status_code,
                elapsed_ms=(time.monotonic() - started) * 1000.0,
            )
        )

    def _json(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        response = self._request(method, url, **kwargs)
        try:
            payload = response.json()
        except ValueError as exc:
            raise PolyfileApiError(
                method,
                str(response.request.url),
                response.status_code,
                "Response is not valid JSON",
            ) from exc
        if not isinstance(payload, dict):
            raise PolyfileApiError(
                method,
                str(response.request.url),
                response.status_code,
                "Expected a JSON object",
            )
        return payload

    # -- reads -------------------------------------------------------------

    def dashboard_context(self) -> dict[str, Any]:
        """Return the dashboard context, useful as an auth/health probe."""
        return self._json("GET", "/dashboard-context/")

    def list_nodes(self, path: str = "/") -> dict[str, Any]:
        """List a node and its children by logical path."""
        return self._json("GET", "/api/v1/fs-node/", params={"path": path})

    def deletion_job(self, job_id: str) -> dict[str, Any]:
        """Return the status of an asynchronous deletion job."""
        return self._json("GET", f"/api/v1/fs-node/deletion-jobs/{job_id}/")

    def wait_for_deletion(
        self,
        job_id: str,
        *,
        timeout: float = 60.0,
        interval: float = 0.5,
    ) -> dict[str, Any]:
        """Poll a deletion job until it reaches a terminal state."""
        deadline = time.monotonic() + timeout
        while True:
            payload = self.deletion_job(job_id)
            status = payload.get("status")
            if status in {"done", "failed", "cancelled", "timeout"}:
                return payload
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Deletion job {job_id} did not finish within {timeout}s")
            time.sleep(interval)

    def list_shares(self, *, status: str = "all", page: int = 1) -> dict[str, Any]:
        """List the current user's shares."""
        return self._json("GET", "/api/shares/", params={"status": status, "page": page})

    def share_detail(self, token: str, path: str = "") -> dict[str, Any]:
        """Read a public share by token and optional relative path."""
        suffix = quote(path, safe="/")
        url = f"/api/shares/detail/{token}/"
        if suffix:
            url = f"{url}{suffix}/"
        return self._json("GET", url)

    # -- writes ------------------------------------------------------------

    def mkdir(self, path: str) -> dict[str, Any]:
        """Create a directory at ``path`` and return its node data."""
        return self._json("POST", "/api/v1/fs-node/mkdir", params={"path": path})

    def touch(self, path: str) -> dict[str, Any]:
        """Create a file node at ``path`` and return its data plus ``upload_url``."""
        return self._json("POST", "/api/v1/fs-node/touch", params={"path": path})

    def upload(
        self,
        upload_url: str,
        content: bytes,
        *,
        content_type: str = "application/octet-stream",
    ) -> dict[str, Any]:
        """Upload raw content to a temporary upload URL."""
        return self._json(
            "POST",
            upload_url,
            content=content,
            headers={"Content-Type": content_type},
        )

    def delete_node(self, path: str) -> dict[str, Any]:
        """Start asynchronous deletion of the node at ``path`` and its subtree."""
        return self._json("DELETE", "/api/v1/fs-node/", params={"path": path})

    def create_share(self, path: str, expires_at: str | None = None) -> dict[str, Any]:
        """Create or reactivate a public share for the node at ``path``."""
        params: dict[str, str] = {}
        if expires_at is not None:
            params["expires_at"] = expires_at
        url = "/api/shares/create" + quote(path, safe="/")
        return self._json("POST", url, params=params or None)

    def revoke_share(self, token: str) -> None:
        """Revoke a public share."""
        self._request("POST", f"/api/shares/{token}/revoke")

    def delete_share(self, token: str) -> None:
        """Permanently delete a public share."""
        self._request("DELETE", f"/api/shares/{token}/delete")

    # -- downloads ---------------------------------------------------------

    def download_file(self, node_id: str) -> bytes:
        """Download a file node's content."""
        response = self._request("GET", f"/download/{node_id}/")
        if response.status_code != 200:
            raise PolyfileApiError(
                "GET",
                str(response.request.url),
                response.status_code,
                "Expected a file response",
            )
        return response.content
